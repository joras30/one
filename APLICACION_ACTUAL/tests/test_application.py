"""Behavioral HTTP and migration checks; every database and account is synthetic."""
from __future__ import annotations

import base64
import concurrent.futures
import contextlib
import csv
import datetime as datetime_module
import hashlib
import http.cookiejar
import io
import json
import queue
import re
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))
import app  # noqa: E402


class Client:
    def __init__(self, base: str, cookiejar=None):
        self.base = base
        self.csrf = None
        self.cookies = cookiejar if cookiejar is not None else http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(self.cookies),
        )

    def request(self, path: str, payload=None, *, csrf=True):
        headers = {}
        raw = None
        if payload is not None:
            raw = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
            if csrf and self.csrf:
                headers["X-CSRF-Token"] = self.csrf
        req = urllib.request.Request(self.base + path, data=raw, headers=headers)
        try:
            response = self.opener.open(req, timeout=15)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            body = response.read()
            if "application/json" in response.headers.get("Content-Type", ""):
                body = json.loads(body)
            return response.status, body, dict(response.headers)

    def login(self, username: str, password: str):
        status, result, _ = self.request(
            "/api/login", {"username": username, "password": password}, csrf=False
        )
        if status == 200:
            me_status, me, _ = self.request("/api/me")
            if me_status != 200 or not me.get("logged"):
                raise AssertionError("Successful login did not establish a session")
            self.csrf = me["csrf"]
        return status, result


class HTTPFixture:
    def start_http(self, data_dir: Path):
        # Cada instalación temporal tiene su propio contador de intentos.
        with app.LOGIN_LOCK:
            app.LOGIN_FAILS.clear()
        app.configure(data_dir, port=0, demo=False)
        app.init_db()
        self.server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        self.server.daemon_threads = True
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        # Tests omit Origin. The application accepts its absence for local clients.
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop_http(self):
        if getattr(self, "server", None):
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=5)

    def result(self, client: Client, path: str, payload=None, *, expected=200, csrf=True):
        status, data, headers = client.request(path, payload, csrf=csrf)
        self.assertEqual(status, expected, f"Unexpected HTTP status for {path}: {data!r}")
        return data


class ApplicationTests(HTTPFixture, unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="laboratorio-http-test-")
        self.addCleanup(self.temp.cleanup)
        self.start_http(Path(self.temp.name))
        self.addCleanup(self.stop_http)
        self.admin_password = secrets.token_urlsafe(20)
        self.admin = Client(self.base)
        self.result(self.admin, "/api/setup", {
            "username": "admin_prueba", "name": "Administrador de prueba",
            "password": self.admin_password,
        })
        self.assertEqual(self.admin.login("admin_prueba", self.admin_password)[0], 200)

    def create_user(self, code="90001", *, role="tecnico", activities=None, name=None):
        if activities is None:
            activities = ["limpieza", "revision", "configuracion", "sellado", "asignacion", "recepcion"]
        password = code if role == "tecnico" else secrets.token_urlsafe(20)
        payload = {
            "username": code, "name": name or f"Persona de prueba {code}",
            "role": role, "activity_ids": activities,
        }
        if role != "tecnico":
            payload["password"] = password
        self.result(self.admin, "/api/usuarios", payload)
        users = self.result(self.admin, "/api/usuarios")["users"]
        user = next(item for item in users if item["username"] == code)
        client = Client(self.base)
        self.assertEqual(client.login(code, password)[0], 200)
        if self.result(client, "/api/me")["user"].get("must_change"):
            replacement = secrets.token_urlsafe(20)
            self.result(client, "/api/password", {"current_password": password, "password": replacement})
            self.assertEqual(client.login(code, replacement)[0], 200)
            password = replacement
        return user, client, password

    def event(self, activity="revision", *, actor=None, responsible=None,
              quantity=1, data=None, operation_id=None, work_date="2026-10-22",
              confirm=False, expected=200):
        if data is None:
            if activity == "revision":
                data = {"serie": "0000012345", "marca": "Marca de prueba A",
                        "voltaje": "240V", "condicion": "Base Rota"}
            elif activity == "limpieza":
                data = {"voltaje": "240V", "tiempo_minutos": 20,
                        "condicion_visual": "Bueno"}
            elif activity == "recepcion":
                data = {"sap": "9000001", "numero_orden": "ORDEN-DEMO-001",
                        "proceso": "Recepcion de prueba", "marca": "Marca de prueba",
                        "cantidad_esperada": 100}
            else:
                raise ValueError("Provide activity-specific test fields")
        payload = {"activity_id": activity, "work_date": work_date, "quantity": quantity,
                   "data": data, "operation_id": operation_id or str(uuid.uuid4()),
                   "confirm_reentry": confirm}
        if responsible is not None:
            payload["responsible_id"] = responsible
        return self.result(actor or self.admin, "/api/eventos", payload, expected=expected)

    def test_bootstrap_is_one_time_and_static_resources_work(self):
        self.result(self.admin, "/api/setup", {
            "username": "otro_admin", "name": "No debe crearse", "password": secrets.token_urlsafe(20)
        }, expected=409)
        for path, marker in [("/", b"<!doctype html"), ("/app.js", b"/api/"),
                             ("/app.css", b"{"), ("/edesur.png", b"\x89PNG")]:
            status, body, headers = self.admin.request(path)
            self.assertEqual(status, 200, path)
            self.assertIn(marker.lower(), body.lower(), path)
            self.assertIn("X-Content-Type-Options", headers)

    def test_six_activities_and_sap_are_configured(self):
        activities = self.result(self.admin, "/api/actividades")["activities"]
        self.assertEqual({item["id"] for item in activities},
                         {"limpieza", "revision", "configuracion", "sellado", "asignacion", "recepcion"})
        cleaning = next(item for item in activities if item["id"] == "limpieza")
        self.assertEqual(cleaning["name"], "Limpieza o recuperación de medidores")
        review = next(item for item in activities if item["id"] == "revision")
        self.assertFalse(next(field for field in review["fields"] if field["key"] == "sap")["required"])
        sap = self.result(self.admin, "/api/sap")["items"]
        confirmed = next(item for item in sap if item["code"] == "1003913")
        self.assertEqual(confirmed["voltage"], "240V")
        self.assertEqual(confirmed["classification"].lower(), "recuperado")

    def test_anonymous_and_csrf_protections(self):
        anonymous = Client(self.base)
        self.result(anonymous, "/api/eventos", expected=401)
        self.result(anonymous, "/api/actividades", expected=401)
        self.result(self.admin, "/api/catalogos", {"kind": "voltajes", "label": "480V"},
                    csrf=False, expected=403)
        self.assertFalse(self.result(anonymous, "/api/me")["logged"])

    def test_login_backoff_counts_six_failures_reports_remaining_time_and_expires(self):
        _, tech, _ = self.create_user("90009")
        clock = app.time.time()
        with mock.patch.object(app.time, "time", return_value=clock) as simulated_time:
            for _ in range(6):
                status, _, _ = tech.request("/api/login", {
                    "username": "90009", "password": "clave-incorrecta"
                }, csrf=False)
                self.assertEqual(status, 401)
            status, blocked, headers = tech.request("/api/login", {
                "username": "90009", "password": "90009"
            }, csrf=False)
            self.assertEqual(status, 429)
            self.assertEqual(blocked["retry_after_seconds"], 900)
            self.assertEqual(headers.get("Retry-After"), "900")
            self.assertIn("15 min", blocked["error"])
            simulated_time.return_value = clock + 120
            status, later, headers = tech.request("/api/login", {
                "username": "90009", "password": "otra-clave-incorrecta"
            }, csrf=False)
            self.assertEqual(status, 429)
            self.assertEqual(later["retry_after_seconds"], 780)
            self.assertEqual(headers.get("Retry-After"), "780")
            # Blocked requests must not extend the window or count as new failures.
            simulated_time.return_value = clock + 900
            self.assertEqual(tech.login("90009", "90009")[0], 200)
            self.assertTrue(self.result(tech, "/api/me")["logged"])

    def test_sap_optional_and_brand_independent_of_code(self):
        first = self.event()["record"]
        self.assertEqual(first["data"]["serie"], "0000012345")
        self.assertIn(first["data"].get("sap"), (None, ""))
        for index, brand in enumerate(("Marca de prueba A", "Otra marca de prueba"), 1):
            data = {"serie": f"000009990{index}", "marca": brand, "voltaje": "240V",
                    "condicion": "Base Rota", "sap": "1003913", "clasificacion": "Recuperado"}
            record = self.event(data=data)["record"]
            self.assertEqual(record["data"]["marca"], brand)
            self.assertEqual(record["data"]["sap"], "1003913")

    def test_individual_quantity_and_dates_are_validated(self):
        self.event(quantity=2, expected=400)
        self.event(work_date="2026-02-30", expected=400)
        self.event("limpieza", quantity=0, expected=400)
        self.assertEqual(self.result(self.admin, "/api/eventos")["total"], 0)

    def test_reentry_requires_explicit_same_day_confirmation(self):
        first = self.event()["record"]
        rejected = self.event(expected=409)
        self.assertTrue(rejected["needs_confirmation"])
        self.assertTrue(rejected["same_day"])
        self.assertTrue(rejected["previous"])
        self.assertEqual(self.result(self.admin, "/api/eventos")["total"], 1)
        second = self.event(confirm=True)["record"]
        self.assertNotEqual(second["id"], first["id"])
        self.assertEqual(second["revision"], 2)
        history = self.result(self.admin, "/api/historial?medidor=0000012345")
        self.assertEqual(history["count"], 2)
        self.assertEqual({r["data"]["serie"] for r in history["records"]}, {"0000012345"})

    def test_idempotency_replays_same_operation_but_rejects_changed_payload(self):
        key = str(uuid.uuid4())
        first = self.event(operation_id=key)["record"]
        same = self.event(operation_id=key)["record"]
        self.assertEqual(first["id"], same["id"])
        self.event(operation_id=key, work_date="2026-10-21", expected=409)
        self.assertEqual(self.result(self.admin, "/api/eventos")["total"], 1)

    def test_concurrent_retries_create_only_one_operation(self):
        clients = [Client(self.base), Client(self.base)]
        for client in clients:
            self.assertEqual(client.login("admin_prueba", self.admin_password)[0], 200)
        payload = {"activity_id": "revision", "work_date": "2026-10-22", "quantity": 1,
                   "data": {"serie": "000CONCURRENTE", "marca": "Marca de prueba",
                            "voltaje": "240V", "condicion": "Base Rota"},
                   "operation_id": str(uuid.uuid4())}
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda client: client.request("/api/eventos", payload), clients))
        self.assertEqual([status for status, _, _ in results], [200, 200])
        self.assertEqual(len({result["record"]["id"] for _, result, _ in results}), 1)
        self.assertEqual(self.result(self.admin, "/api/eventos")["total"], 1)

    def test_lot_quantities_and_identified_meters_remain_distinct(self):
        self.event("limpieza", quantity=100)
        self.event("limpieza", quantity=50)
        self.event()
        dashboard = self.result(self.admin, "/api/dashboard")
        self.assertEqual(dashboard["event_count"], 3)
        self.assertEqual(dashboard["review_count"], 1)
        self.assertEqual(dashboard["identified_unique"], 1)
        cleaning = next(row for row in dashboard["by_activity"] if "Limpieza" in row["label"])
        self.assertEqual(cleaning["value"], 150)
        self.assertEqual(cleaning["unit"], "medidores")

    def test_configuration_sealing_and_assignment_keep_their_units(self):
        user, tech, _ = self.create_user()
        configured = self.event("configuracion", actor=tech, quantity=4, data={
            "tipo_configuracion": "Prepago", "sap": "1003913", "marca": "Marca de configuración"
        })["record"]
        self.assertEqual(configured["quantity"], 4)
        self.assertEqual(configured["data"]["voltaje"], "240V")
        sealed = self.event("sellado", actor=tech, data={
            "serie": "000SELLADO01", "sap": "1003913", "marca": "Marca de sellado",
            "clasificacion": "Recuperado",
        })["record"]
        self.assertEqual(sealed["quantity"], 1)
        self.assertEqual(sealed["data"]["serie"], "000SELLADO01")
        self.event("asignacion", actor=tech, quantity=7, data={
            "tipo_articulo": "Medidor", "sap": "1003913", "destino": "Destino de prueba"
        })
        self.event("asignacion", actor=tech, quantity=50, data={
            "tipo_articulo": "Sello", "sap": "9000002", "destino": "Destino de prueba"
        })
        dashboard = self.result(tech, "/api/dashboard?activity_id=asignacion")
        self.assertEqual(dashboard["totals_by_unit"], {"medidores": 7, "sellos": 50})
        self.assertEqual({row["unit"]: row["value"] for row in dashboard["by_activity"]},
                         {"medidores": 7, "sellos": 50})
        self.result(self.admin, "/api/metas", {
            "responsible_id": user["id"], "activity_id": "asignacion", "unit": "medidores",
            "start_date": "2026-10-01", "end_date": "2026-10-31", "target": 10,
        })
        goal = self.result(tech, "/api/metas")["goals"][0]
        self.assertEqual(goal["produced"], 7)
        self.assertEqual(goal["pct"], 70)
        self.assertEqual(goal["pending"], 3)

    def test_responsible_and_capturing_user_are_separate(self):
        tech, _, _ = self.create_user()
        record = self.event(responsible=tech["id"])["record"]
        admin_id = self.result(self.admin, "/api/me")["user"]["id"]
        self.assertEqual(record["responsible_id"], tech["id"])
        self.assertEqual(record["recorded_by"], admin_id)
        self.assertNotEqual(record["responsible_id"], record["recorded_by"])

    def test_technician_assignment_scope_and_identity_enforcement(self):
        first, tech, _ = self.create_user(activities=["revision"])
        second, other, _ = self.create_user("90002", activities=["revision"])
        record = self.event(actor=tech, responsible=second["id"])["record"]
        self.assertEqual(record["responsible_id"], first["id"])
        self.assertEqual(record["recorded_by"], first["id"])
        self.assertEqual(self.result(other, "/api/eventos")["total"], 0)
        self.event("limpieza", actor=tech, quantity=10, expected=403)
        self.result(other, f"/api/eventos/{record['id']}/anular", {"reason": "No autorizado"}, expected=403)
        self.result(tech, "/api/actividades", {"name": "No permitido", "mode": "lote",
                    "unit": "unidades", "fields": []}, expected=403)

    def test_technician_cannot_expand_scope_with_filters_or_exports(self):
        first, tech, _ = self.create_user()
        second, other, _ = self.create_user("90002")
        self.event(actor=tech)
        self.event(actor=other, data={"serie": "000SOLOOTRO", "marca": "Marca de prueba",
                                     "voltaje": "240V", "condicion": "Base Rota"})
        query = "?responsible_id=" + str(second["id"])
        status, result, _ = tech.request("/api/eventos" + query)
        self.assertIn(status, (200, 403))
        if status == 200:
            self.assertEqual(result["total"], 0)
        status, data, _ = tech.request("/api/dashboard" + query)
        self.assertIn(status, (200, 403))
        if status == 200:
            self.assertEqual(data["event_count"], 0)
        status, content, _ = tech.request("/api/export.csv" + query)
        self.assertIn(status, (200, 403))
        if status == 200:
            self.assertNotIn(b"000SOLOOTRO", content)

    def test_supervisor_cannot_create_an_administrator(self):
        _, supervisor, _ = self.create_user("supervisor_prueba", role="supervisor")
        self.result(supervisor, "/api/usuarios", {
            "username": "admin_no_autorizado", "name": "No autorizado", "role": "administrador",
            "password": secrets.token_urlsafe(20), "activity_ids": [],
        }, expected=403)

    def test_reset_restores_code_and_revokes_existing_sessions(self):
        user, tech, _ = self.create_user()
        changed = secrets.token_urlsafe(15)
        self.result(tech, "/api/password", {"current_password": "90001", "password": changed})
        session = Client(self.base)
        self.assertEqual(session.login("90001", changed)[0], 200)
        original = self.event(actor=session)["record"]
        _, other, _ = self.create_user("90002")
        for client, username, correct_password in ((session, "90001", changed), (other, "90002", "90002")):
            for _ in range(6):
                status, _, _ = client.request("/api/login", {
                    "username": username, "password": "clave-incorrecta"
                }, csrf=False)
                self.assertEqual(status, 401)
            self.assertEqual(Client(self.base).login(username, correct_password)[0], 429)
        self.result(self.admin, f"/api/usuarios/{user['id']}/restablecer", {})
        self.result(session, "/api/eventos", expected=401)
        fresh = Client(self.base)
        self.assertEqual(fresh.login("90001", "90001")[0], 200)
        records = self.result(fresh, "/api/eventos")["records"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["id"], original["id"])
        self.assertEqual(records[0]["data"]["serie"], "0000012345")
        self.assertEqual(Client(self.base).login("90002", "90002")[0], 429,
                         "Resetting one account cleared another account's backoff")
        self.assertEqual(Client(self.base).login("90001", changed)[0], 401)

    def test_deactivation_blocks_access_without_losing_production(self):
        user, tech, _ = self.create_user()
        record = self.event(actor=tech)["record"]
        self.result(self.admin, f"/api/usuarios/{user['id']}/actualizar", {"active": False})
        self.result(tech, "/api/eventos", expected=401)
        self.assertEqual(Client(self.base).login("90001", "90001")[0], 401)
        records = self.result(self.admin, "/api/eventos")["records"]
        self.assertEqual(records[0]["id"], record["id"])
        self.assertEqual(records[0]["responsible_id"], user["id"])

    def test_visitor_has_aggregate_view_without_personal_detail(self):
        tech, technician, _ = self.create_user(name="Nombre sintético privado")
        self.event(actor=technician)
        _, visitor, _ = self.create_user("visitante_prueba", role="visitante", activities=[])
        dashboard = self.result(visitor, "/api/dashboard")
        self.assertEqual(dashboard["event_count"], 1)
        self.assertNotIn(tech["name"], json.dumps(dashboard, ensure_ascii=False))
        for path in ("/api/eventos", "/api/usuarios", "/api/auditoria", "/api/export.csv"):
            self.result(visitor, path, expected=403)
        self.result(visitor, "/api/dashboard?meter=0000012345", expected=403)
        self.result(visitor, "/api/dashboard?responsible_id=" + str(tech["id"]), expected=403)
        self.event(actor=visitor, expected=403)

    def test_activity_versions_preserve_old_schema_and_name(self):
        old = self.event()["record"]
        activity = next(a for a in self.result(self.admin, "/api/actividades")["activities"] if a["id"] == "revision")
        fields = activity["fields"] + [{"key": "dato_adicional", "label": "Dato adicional", "type": "text", "required": True}]
        self.result(self.admin, "/api/actividades", {"id": "revision", "name": "Revisión técnica ampliada",
                    "mode": "individual", "unit": "revisiones", "fields": fields, "active": True})
        historical = self.result(self.admin, "/api/eventos")["records"][0]
        self.assertEqual(historical["activity_version"], old["activity_version"])
        self.assertEqual(historical["activity_name"], old["activity_name"])
        self.assertNotIn("dato_adicional", historical["data"])
        self.event(data={"serie": "0000012346", "marca": "Marca de prueba", "voltaje": "240V", "condicion": "Base Rota"}, expected=400)
        new = self.event(data={"serie": "0000012347", "marca": "Marca de prueba", "voltaje": "240V",
                               "condicion": "Base Rota", "dato_adicional": "Dato nuevo"})["record"]
        self.assertGreater(new["activity_version"], old["activity_version"])
        corrected_data = dict(old["data"], observaciones="Corrección con formulario histórico")
        self.result(self.admin, f"/api/eventos/{old['id']}/corregir", {
            "data": corrected_data, "reason": "Completar observación histórica"
        })
        corrected = next(row for row in self.result(self.admin, "/api/eventos")["records"] if row["id"] == old["id"])
        self.assertEqual(corrected["activity_version"], old["activity_version"])
        self.assertEqual(corrected["activity_name"], old["activity_name"])
        self.assertNotIn("dato_adicional", corrected["data"])

    def test_new_activity_can_be_assigned_and_archived_without_losing_history(self):
        definition = {"name": "Ensayo adicional de prueba", "mode": "lote", "unit": "ensayos",
                      "fields": [{"key": "observaciones", "label": "Observaciones", "type": "text", "required": False}]}
        self.result(self.admin, "/api/actividades", definition)
        activity = next(item for item in self.result(self.admin, "/api/actividades")["activities"]
                        if item["name"] == definition["name"])
        user, tech, _ = self.create_user(activities=[activity["id"]])
        record = self.event(activity["id"], actor=tech, quantity=3,
                            data={"observaciones": "Ensayo ficticio"})["record"]
        self.result(self.admin, "/api/actividades", dict(definition, id=activity["id"], active=False))
        payload = {"activity_id": activity["id"], "work_date": "2026-10-22", "quantity": 1,
                   "data": {}, "operation_id": str(uuid.uuid4())}
        status, _, _ = tech.request("/api/eventos", payload)
        self.assertIn(status, (400, 403), "Archived activity accepted a new capture")
        archived = self.result(tech, "/api/eventos")["records"]
        self.assertEqual(len(archived), 1)
        self.assertEqual(archived[0]["id"], record["id"])
        self.assertEqual(archived[0]["quantity"], 3)
        self.assertEqual(archived[0]["unit"], "ensayos")

    def test_removed_assignment_stays_removed_after_restart(self):
        user, tech, _ = self.create_user(activities=["revision"])
        record = self.event(actor=tech)["record"]
        self.result(self.admin, f"/api/usuarios/{user['id']}/actualizar", {"activity_ids": []})
        app.init_db()
        self.event(actor=tech, data={"serie": "000SINASIGNACION", "marca": "Marca de prueba",
                                    "voltaje": "240V", "condicion": "Base Rota"}, expected=403)
        self.assertEqual(self.result(tech, "/api/eventos")["records"][0]["id"], record["id"])

    def test_corrections_voids_and_restoration_are_audited(self):
        original = self.event("limpieza", quantity=10)["record"]
        path = f"/api/eventos/{original['id']}"
        self.result(self.admin, path + "/corregir", {"quantity": 12, "reason": "Cantidad verificada"})
        self.result(self.admin, path + "/anular", {"reason": "Prueba de anulación"})
        self.assertEqual(self.result(self.admin, "/api/eventos")["total"], 0)
        all_records = self.result(self.admin, "/api/eventos?state=all")["records"]
        self.assertEqual(all_records[0]["quantity"], 12)
        self.result(self.admin, path + "/restaurar", {"reason": "Prueba de restauración"})
        self.assertEqual(self.result(self.admin, "/api/eventos")["total"], 1)
        audit = self.result(self.admin, "/api/auditoria")["entries"]
        reasons = {row["reason"] for row in audit}
        self.assertTrue({"Cantidad verificada", "Prueba de anulación", "Prueba de restauración"}.issubset(reasons))
        self.assertNotIn('"salt"', json.dumps(audit))
        self.assertNotIn('"hash"', json.dumps(audit))

    def test_partial_receipts_accumulate_and_unknown_expected_is_not_zero(self):
        self.event("recepcion", quantity=40)
        self.event("recepcion", quantity=30)
        rows = self.result(self.admin, "/api/recepciones")["receipts"]
        receipt = next(row for row in rows if row["order"] == "ORDEN-DEMO-001")
        self.assertEqual((receipt["received"], receipt["expected"], receipt["pending"]), (70, 100, 30))
        self.event("recepcion", quantity=8, data={"sap": "9000002", "numero_orden": "ORDEN-DEMO-002",
                   "proceso": "Recepción sin total esperado", "marca": "Marca de prueba"})
        unknown = next(row for row in self.result(self.admin, "/api/recepciones")["receipts"] if row["order"] == "ORDEN-DEMO-002")
        self.assertIsNone(unknown["expected"])
        self.assertIsNone(unknown["pending"])

    def test_shared_receipt_has_global_balance_and_separate_own_contribution(self):
        first, tech, _ = self.create_user()
        second, other, _ = self.create_user("90002")
        self.event("recepcion", actor=tech, quantity=40)
        self.event("recepcion", actor=other, quantity=60)
        self.event("recepcion", actor=other, quantity=5, data={
            "sap": "9000002", "numero_orden": "ORDEN-AJENA-002", "proceso": "Otra recepción",
            "marca": "Marca de prueba", "cantidad_esperada": 10,
        })
        own_view = self.result(tech, "/api/recepciones")["receipts"]
        self.assertEqual(len(own_view), 1)
        receipt = own_view[0]
        self.assertEqual(receipt["order"], "ORDEN-DEMO-001")
        self.assertEqual((receipt["received"], receipt["expected"], receipt["pending"]), (100, 100, 0))
        self.assertEqual(receipt["own_received"], 40)
        self.assertEqual(receipt["scope"], "orden")
        self.assertNotIn(second["name"], json.dumps(own_view, ensure_ascii=False))
        self.assertEqual(self.result(tech, "/api/dashboard")["receipts_pending"], 0)
        supervisor_view = self.result(self.admin, "/api/recepciones")["receipts"]
        collective = next(row for row in supervisor_view if row["order"] == "ORDEN-DEMO-001")
        self.assertEqual((collective["received"], collective["pending"]), (100, 0))
        supervisor_filtered = self.result(self.admin, "/api/recepciones?responsible_id=" + str(first["id"]))["receipts"]
        self.assertEqual(len(supervisor_filtered), 1)
        self.assertEqual(supervisor_filtered[0]["order"], "ORDEN-DEMO-001")
        self.assertEqual((supervisor_filtered[0]["received"], supervisor_filtered[0]["pending"]), (100, 0),
                         "A person filter turned an order balance into a partial-person balance")

    def test_goal_uses_quantities_for_matching_activity_person_and_period(self):
        tech, client, _ = self.create_user()
        self.result(self.admin, "/api/metas", {"responsible_id": tech["id"], "activity_id": "limpieza",
                    "start_date": "2026-10-01", "end_date": "2026-10-31", "target": 5})
        self.event("limpieza", actor=client, quantity=3)
        self.event("limpieza", actor=client, quantity=2)
        self.event("limpieza", quantity=100)
        self.event(actor=client)
        goal = self.result(client, "/api/metas")["goals"][0]
        self.assertEqual(goal["produced"], 5)
        self.assertEqual(goal["pct"], 100)
        self.assertEqual(goal["pending"], 0)

    def test_goal_expiration_uses_santo_domingo_day_at_utc_midnight(self):
        import production

        class FrozenDate(datetime_module.date):
            @classmethod
            def today(cls):
                return cls(2026, 10, 23)  # Host/UTC has advanced; local workday has not.

        class FrozenDateTime(datetime_module.datetime):
            @classmethod
            def now(cls, tz=None):
                instant = cls(2026, 10, 23, 1, 0, tzinfo=datetime_module.timezone.utc)
                return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)

        user, tech, _ = self.create_user()
        with mock.patch.object(production, "date", FrozenDate), \
             mock.patch.object(production, "datetime", FrozenDateTime):
            self.result(self.admin, "/api/metas", {
                "responsible_id": user["id"], "activity_id": "limpieza",
                "start_date": "2026-10-22", "end_date": "2026-10-22", "target": 5,
            })
            goal = self.result(tech, "/api/metas")["goals"][0]
        self.assertEqual(goal["state"], "en_progreso")

    def test_exports_apply_filters_and_preserve_identifier_text(self):
        self.event(data={"serie": "0000012345", "marca": "Marca de prueba", "voltaje": "240V",
                         "condicion": "Base Rota", "sap": "1003913", "observaciones": "=2+2"})
        self.event("limpieza", quantity=20, work_date="2026-10-21")
        suffix = "?activity_id=revision&desde=2026-10-22&hasta=2026-10-22"
        status, body, _ = self.admin.request("/api/export.csv" + suffix)
        self.assertEqual(status, 200)
        rows = list(csv.reader(io.StringIO(body.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(len(rows), 2)
        self.assertIn("0000012345", rows[1])
        self.assertIn("'=2+2", rows[1])
        import documents
        status, body, _ = self.admin.request("/api/export.xlsx" + suffix)
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith(b"PK"))
        exported = documents.read_table("produccion.xlsx", body)
        self.assertEqual(len(exported), 1)
        self.assertIn("0000012345", exported[0].values())
        status, body, _ = self.admin.request("/api/export.pdf" + suffix)
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith(b"%PDF-"))
        self.assertIn(b"%%EOF", body)

    def test_exports_include_operational_and_custom_fields(self):
        import documents
        self.event("limpieza", quantity=8, data={"voltaje": "240V", "tiempo_minutos": 35,
                   "condicion_visual": "Regular"})
        self.event("recepcion", quantity=40)
        for activity, label, value in [
            ("limpieza", "Tiempo total del lote (min)", "35"),
            ("recepcion", "Número de orden", "ORDEN-DEMO-001"),
            ("recepcion", "Proceso de recepción", "Recepcion de prueba"),
            ("recepcion", "Cantidad total esperada", "100"),
        ]:
            status, raw, _ = self.admin.request("/api/export.csv?activity_id=" + activity)
            self.assertEqual(status, 200)
            rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig")), delimiter=";"))
            column = next((key for key in rows[0] if key.startswith(label)), None)
            self.assertIsNotNone(column, f"Missing operational field {label}")
            self.assertEqual(rows[0][column], value)
        self.result(self.admin, "/api/actividades", {
            "name": "Ensayo exportable de prueba", "mode": "lote", "unit": "ensayos",
            "fields": [{"key": "lectura_prueba", "label": "Lectura de prueba", "type": "number", "required": True},
                       {"key": "nota_prueba", "label": "Nota particular", "type": "text", "required": True}],
        })
        activity = next(item for item in self.result(self.admin, "/api/actividades")["activities"]
                        if item["name"] == "Ensayo exportable de prueba")
        self.event(activity["id"], quantity=2, data={"lectura_prueba": 12.5, "nota_prueba": "Dato exportable"})
        status, raw, _ = self.admin.request("/api/export.xlsx?activity_id=" + activity["id"])
        self.assertEqual(status, 200)
        exported = documents.read_table("prueba.xlsx", raw)
        self.assertEqual(len(exported), 1)
        reading_key = next((key for key in exported[0] if key.startswith("lectura_de_prueba")), None)
        note_key = next((key for key in exported[0] if key.startswith("nota_particular")), None)
        self.assertIsNotNone(reading_key)
        self.assertIsNotNone(note_key)
        self.assertEqual(exported[0][reading_key], "12.5")
        self.assertEqual(exported[0][note_key], "Dato exportable")

    def upload(self, rows, *, activity="revision", kind="csv"):
        import documents
        columns = ["work_date", "responsible", "serie", "sap", "marca", "voltaje", "condicion", "clasificacion", "observaciones"]
        values = [[row.get(col, "") for col in columns] for row in rows]
        raw = documents.write_xlsx(columns, values) if kind == "xlsx" else documents.write_csv(columns, values)
        return self.result(self.admin, "/api/import/preview", {
            "activity_id": activity, "filename": "prueba." + kind,
            "content_base64": base64.b64encode(raw).decode("ascii"),
        })

    def test_import_errors_do_not_write_partial_production(self):
        self.create_user()
        common = {"work_date": "2026-10-22", "marca": "Marca de prueba", "voltaje": "240V", "condicion": "Base Rota"}
        preview = self.upload([dict(common, responsible="90001", serie="000IMPORT01"),
                               dict(common, responsible="99999", serie="000IMPORT02")])
        self.assertTrue(preview["errors"])
        self.assertEqual(self.result(self.admin, "/api/eventos")["total"], 0)
        self.result(self.admin, "/api/import/confirm", {"preview_id": preview["preview_id"], "confirm_reentry": True}, expected=400)
        self.assertEqual(self.result(self.admin, "/api/eventos")["total"], 0)

    def test_xlsx_import_attributes_rows_and_repeated_confirmation_is_idempotent(self):
        first, _, _ = self.create_user()
        second, _, _ = self.create_user("90002")
        common = {"work_date": "2026-10-22", "marca": "Marca de prueba", "voltaje": "240V", "condicion": "Base Rota"}
        preview = self.upload([dict(common, responsible="90001", serie="000IMPORT01"),
                               dict(common, responsible="90002", serie="000IMPORT02")], kind="xlsx")
        self.assertEqual(preview["errors"], [])
        self.assertEqual(preview["valid_count"], 2)
        payload = {"preview_id": preview["preview_id"], "confirm_reentry": True}
        self.result(self.admin, "/api/import/confirm", payload)
        self.result(self.admin, "/api/import/confirm", payload)
        records = self.result(self.admin, "/api/eventos")["records"]
        self.assertEqual(len(records), 2)
        self.assertEqual({row["responsible_id"] for row in records}, {first["id"], second["id"]})
        self.assertEqual({row["data"]["serie"] for row in records}, {"000IMPORT01", "000IMPORT02"})
        admin_id = self.result(self.admin, "/api/me")["user"]["id"]
        self.assertEqual({row["recorded_by"] for row in records}, {admin_id})

    def test_same_day_import_reentries_require_confirmation_and_rollback_whole_batch(self):
        self.create_user()
        row = {"work_date": "2026-10-22", "responsible": "90001", "serie": "000REINGRESO01",
               "marca": "Marca de prueba", "voltaje": "240V", "condicion": "Base Rota"}
        preview = self.upload([dict(row, observaciones="Primera revisión del día"),
                               dict(row, observaciones="Segunda revisión legítima")])
        self.assertEqual(preview["errors"], [])
        self.assertEqual(preview["valid_count"], 2)
        self.assertTrue(preview["warnings"])
        self.result(self.admin, "/api/import/confirm", {
            "preview_id": preview["preview_id"], "confirm_reentry": False
        }, expected=409)
        self.assertEqual(self.result(self.admin, "/api/eventos")["total"], 0,
                         "A late reentry conflict left an earlier imported row committed")
        self.result(self.admin, "/api/import/confirm", {
            "preview_id": preview["preview_id"], "confirm_reentry": True
        })
        records = self.result(self.admin, "/api/eventos")["records"]
        self.assertEqual(len(records), 2)
        self.assertEqual({record["revision"] for record in records}, {1, 2})
        self.assertEqual({record["data"]["serie"] for record in records}, {"000REINGRESO01"})

    def test_database_persists_records_and_credentials_after_reinitialization(self):
        original = self.event()["record"]
        app.init_db()
        relogged = Client(self.base)
        self.assertEqual(relogged.login("admin_prueba", self.admin_password)[0], 200)
        records = self.result(relogged, "/api/eventos")["records"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["id"], original["id"])
        with contextlib.closing(sqlite3.connect(app.DB_PATH)) as db, db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_administrator_backup_is_restorable_and_technician_is_denied(self):
        record = self.event()["record"]
        _, tech, _ = self.create_user()
        self.result(tech, "/api/backup", {}, expected=403)
        result = self.result(self.admin, "/api/backup", {})
        self.assertTrue(result["ok"])
        filename = result["filename"]
        self.assertEqual(Path(filename).name, filename)
        backup = Path(self.temp.name) / "backups" / filename
        self.assertTrue(backup.is_file())
        restored = Path(self.temp.name) / "restauracion-prueba.db"
        with (contextlib.closing(sqlite3.connect(backup)) as source, source,
              contextlib.closing(sqlite3.connect(restored)) as destination, destination):
            source.backup(destination)
            self.assertEqual(destination.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            row = destination.execute("SELECT id,data_json FROM production_events WHERE id=?", (record["id"],)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(json.loads(row[1])["serie"], "0000012345")


class CLIRegressionTests(HTTPFixture, unittest.TestCase):
    """Actual isolated processes reproduce browser cookies shared across ports."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="laboratorio-cli-test-")
        self.addCleanup(self.temp.cleanup)
        self.instances = []
        self.addCleanup(self.stop_instances)

    def start_cli(self, name, *, demo=False):
        directory = Path(self.temp.name) / name
        command = [sys.executable, "-u", str(APP_ROOT / "app.py"),
                   "--data-dir", str(directory), "--port", "0", "--no-browser"]
        if demo:
            command.append("--demo")
        process = subprocess.Popen(command, cwd=APP_ROOT, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, bufsize=1)
        ready = queue.Queue()
        output = []

        def read_output():
            for line in process.stdout:
                output.append(line.rstrip())
                if re.fullmatch(r"http://127\.0\.0\.1:\d+", line.strip()):
                    ready.put(line.strip())
            ready.put(None)

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        instance = {"process": process, "reader": reader, "directory": directory}
        self.instances.append(instance)
        try:
            base = ready.get(timeout=15)
        except queue.Empty:
            self.fail("The temporary CLI instance did not become ready")
        self.assertIsNotNone(base, "Temporary CLI startup failed: " + "\n".join(output[-12:]))
        instance["base"] = base
        return instance

    @staticmethod
    def stop_instance(instance):
        process = instance["process"]
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        instance["reader"].join(timeout=2)
        if process.stdout is not None and not process.stdout.closed:
            process.stdout.close()

    def stop_instances(self):
        for instance in reversed(self.instances):
            self.stop_instance(instance)

    def setup_admin(self, client, username="admin_cli_prueba"):
        password = secrets.token_urlsafe(20)
        self.result(client, "/api/setup", {"username": username,
                    "name": "Administrador de prueba CLI", "password": password})
        self.assertEqual(client.login(username, password)[0], 200)
        return password

    def test_normal_and_demo_sessions_survive_each_others_logout_and_password_change(self):
        normal_process = self.start_cli("normal")
        demo_process = self.start_cli("demo", demo=True)
        browser_cookies = http.cookiejar.CookieJar()
        normal = Client(normal_process["base"], cookiejar=browser_cookies)
        demo = Client(demo_process["base"], cookiejar=browser_cookies)
        normal_password = self.setup_admin(normal)
        # These are the documented fictional demonstration credentials, never real accounts.
        self.assertEqual(demo.login("supervisor_demo", "LaboratorioDemo2026!")[0], 200)
        self.assertEqual({cookie.name for cookie in browser_cookies}, {"sid", "sid_demo"})
        self.assertEqual(self.result(normal, "/api/me")["user"]["username"], "admin_cli_prueba")
        self.assertEqual(self.result(demo, "/api/me")["user"]["username"], "supervisor_demo")
        self.assertEqual(self.result(normal, "/api/eventos")["total"], 0)
        self.assertGreater(self.result(demo, "/api/eventos")["total"], 0)
        self.result(normal, "/api/logout", {})
        self.assertFalse(self.result(normal, "/api/me")["logged"])
        self.assertTrue(self.result(demo, "/api/me")["logged"])
        self.assertEqual({cookie.name for cookie in browser_cookies}, {"sid_demo"})
        self.assertEqual(normal.login("admin_cli_prueba", normal_password)[0], 200)
        demo_password = secrets.token_urlsafe(20)
        self.result(demo, "/api/password", {
            "current_password": "LaboratorioDemo2026!", "password": demo_password
        })
        self.assertFalse(self.result(demo, "/api/me")["logged"])
        self.assertTrue(self.result(normal, "/api/me")["logged"])
        self.assertEqual(demo.login("supervisor_demo", demo_password)[0], 200)
        self.result(normal, "/api/password", {
            "current_password": normal_password, "password": secrets.token_urlsafe(20)
        })
        self.assertFalse(self.result(normal, "/api/me")["logged"])
        self.assertTrue(self.result(demo, "/api/me")["logged"])

    def test_process_restart_clears_backoff_without_erasing_users_or_production(self):
        first = self.start_cli("persistent")
        client = Client(first["base"])
        password = self.setup_admin(client)
        record = self.result(client, "/api/eventos", {
            "activity_id": "revision", "work_date": "2026-10-22", "quantity": 1,
            "data": {"serie": "000PERSISTETRAS429", "marca": "Marca de prueba",
                     "voltaje": "240V", "condicion": "Base Rota"},
            "operation_id": str(uuid.uuid4()),
        })["record"]
        for _ in range(6):
            status, _, _ = client.request("/api/login", {
                "username": "admin_cli_prueba", "password": "clave-incorrecta"
            }, csrf=False)
            self.assertEqual(status, 401)
        self.assertEqual(Client(first["base"]).login("admin_cli_prueba", password)[0], 429)
        self.stop_instance(first)
        restarted = self.start_cli("persistent")
        after = Client(restarted["base"])
        self.assertEqual(after.login("admin_cli_prueba", password)[0], 200)
        records = self.result(after, "/api/eventos")["records"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["id"], record["id"])
        self.assertEqual(records[0]["data"]["serie"], "000PERSISTETRAS429")
        self.assertEqual(len(self.result(after, "/api/usuarios")["users"]), 1)

    def test_cli_chooses_separate_default_ports_without_binding_live_services(self):
        original = (app.DATA_DIR, app.DB_PATH, app.PORT, app.DEMO_MODE)

        class StoppedServer:
            def __init__(self, address, _handler, **_kwargs):
                self.server_port = address[1]

            def server_bind(self):
                pass

            def server_activate(self):
                pass

            def serve_forever(self):
                raise KeyboardInterrupt()

            def server_close(self):
                pass

        try:
            for options, expected_port in [([], 8765), (["--demo"], 8766),
                                           (["--demo", "--port", "17891"], 17891)]:
                with self.subTest(options=options), \
                     mock.patch.object(sys, "argv", ["app.py", "--no-browser", "--data-dir", self.temp.name] + options), \
                     mock.patch.object(app, "ThreadingHTTPServer", side_effect=StoppedServer) as server, \
                     mock.patch.object(app, "init_db"), mock.patch.object(app, "seed_demo"), \
                     contextlib.redirect_stdout(io.StringIO()):
                    app.main()
                    self.assertEqual(server.call_args.args[0], ("127.0.0.1", expected_port))
        finally:
            app.DATA_DIR, app.DB_PATH, app.PORT, app.DEMO_MODE = original


LEGACY_SCHEMA = """
CREATE TABLE users(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
 name TEXT NOT NULL,salt TEXT NOT NULL,hash TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('supervisor','tecnico')),active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE sessions(token_hash TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),
 csrf TEXT NOT NULL,expires INTEGER NOT NULL);
CREATE TABLE catalog(id INTEGER PRIMARY KEY AUTOINCREMENT,
 kind TEXT NOT NULL CHECK(kind IN ('marcas','voltajes','condiciones')),label TEXT NOT NULL,
 active INTEGER NOT NULL DEFAULT 1,UNIQUE(kind,label));
CREATE TABLE records(id INTEGER PRIMARY KEY AUTOINCREMENT,work_date TEXT NOT NULL,meter TEXT NOT NULL,
 brand TEXT NOT NULL,voltage TEXT NOT NULL,condition TEXT NOT NULL,notes TEXT NOT NULL DEFAULT '',
 user_id INTEGER NOT NULL REFERENCES users(id),revision INTEGER NOT NULL,created_at TEXT NOT NULL);
"""


class MigrationTests(HTTPFixture, unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="laboratorio-legacy-test-")
        self.addCleanup(self.temp.cleanup)
        self.data_dir = Path(self.temp.name)
        self.password = secrets.token_urlsafe(18)
        self.salt = secrets.token_hex(16)
        self.digest = app.pw_hash(self.password, self.salt)
        self.legacy = self.data_dir / "laboratorio.db"
        with contextlib.closing(sqlite3.connect(self.legacy)) as db, db:
            db.executescript(LEGACY_SCHEMA)
            db.execute("INSERT INTO users(id,username,name,salt,hash,role) VALUES(?,?,?,?,?,?)",
                       (7, "supervisor_legado", "Supervisor de prueba legado", self.salt, self.digest, "supervisor"))
            db.executemany("INSERT INTO catalog(kind,label) VALUES(?,?)", [
                ("marcas", "Marca legado"), ("voltajes", "240V"), ("condiciones", "Base Rota")])
            db.executemany("""INSERT INTO records(id,work_date,meter,brand,voltage,condition,notes,user_id,revision,created_at)
                         VALUES(?,?,?,?,?,?,?,?,?,?)""", [
                (41, "2026-09-01", "00000517", "Marca legado", "240V", "Base Rota", "Primera revisión", 7, 1, "2026-09-01T12:00:00Z"),
                (89, "2026-10-01", "00000517", "Marca legado", "240V", "Base Rota", "Segunda revisión", 7, 2, "2026-10-01T12:00:00Z"),
            ])
            self.original_records = db.execute("SELECT * FROM records ORDER BY id").fetchall()
        self.start_http(self.data_dir)
        self.addCleanup(self.stop_http)
        self.supervisor = Client(self.base)
        self.assertEqual(self.supervisor.login("supervisor_legado", self.password)[0], 200)

    def test_migration_preserves_legacy_rows_hashes_dates_and_revisions(self):
        profile = self.result(self.supervisor, "/api/me")["user"]
        self.assertEqual(profile["id"], 7)
        self.assertEqual(profile["role"], "administrador")
        events = self.result(self.supervisor, "/api/eventos")["records"]
        self.assertEqual(len(events), 2)
        self.assertEqual({row["legacy_id"] for row in events}, {41, 89})
        self.assertEqual({row["revision"] for row in events}, {1, 2})
        self.assertEqual({row["data"]["serie"] for row in events}, {"00000517"})
        self.assertEqual({row["work_date"] for row in events}, {"2026-09-01", "2026-10-01"})
        self.assertEqual({row["responsible_id"] for row in events}, {7})
        with contextlib.closing(sqlite3.connect(app.DB_PATH)) as db, db:
            self.assertEqual(db.execute("SELECT * FROM records ORDER BY id").fetchall(), self.original_records)
            user = db.execute("SELECT id,salt,hash,role,access_role FROM users WHERE username='supervisor_legado'").fetchone()
            self.assertEqual(user[0], 7)
            self.assertTrue(user[1] == self.salt and user[2] == self.digest, "Legacy verifier was changed")
            self.assertEqual(user[3], "supervisor")
            self.assertEqual(user[4], "administrador")
        backup = self.result(self.supervisor, "/api/backup", {})
        self.assertTrue(backup["ok"])
        self.assertTrue((self.data_dir / "backups" / backup["filename"]).is_file())
        app.init_db()
        self.assertEqual(self.result(self.supervisor, "/api/eventos")["total"], 2)

    def test_migration_creates_a_restorable_backup_and_is_idempotent(self):
        backups = [path for path in self.data_dir.rglob("*") if path.is_file()
                   and path != self.legacy and path.suffix in (".db", ".sqlite", ".sqlite3", ".bak")]
        self.assertTrue(backups, "Migration must keep a consistent SQLite backup")
        found_original = False
        for path in backups:
            try:
                with contextlib.closing(sqlite3.connect(path)) as db, db:
                    if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        continue
                    rows = db.execute("SELECT * FROM records ORDER BY id").fetchall()
                    found_original |= rows == self.original_records
            except sqlite3.DatabaseError:
                continue
        self.assertTrue(found_original, "No backup restored the original legacy records")
        app.init_db()
        app.init_db()
        self.assertEqual(self.result(self.supervisor, "/api/eventos")["total"], 2)

    def test_late_legacy_insert_is_reconciled_without_overwriting_new_or_corrected_events(self):
        old = next(row for row in self.result(self.supervisor, "/api/eventos")["records"] if row["legacy_id"] == 41)
        self.result(self.supervisor, f"/api/eventos/{old['id']}/corregir", {
            "data": dict(old["data"], observaciones="Corregido en la aplicación nueva"),
            "reason": "Corrección posterior a migración",
        })
        new = self.result(self.supervisor, "/api/eventos", {
            "activity_id": "revision", "work_date": "2026-10-22", "quantity": 1,
            "data": {"serie": "000NUEVAPROD", "marca": "Marca legado", "voltaje": "240V", "condicion": "Base Rota"},
            "operation_id": str(uuid.uuid4()),
        })["record"]
        collision_id = new["id"]
        self.assertNotIn(collision_id, (41, 89))
        # Simulate a last request completed by the old process after the first migration.
        with contextlib.closing(sqlite3.connect(app.DB_PATH)) as db, db:
            db.execute("""INSERT INTO records(id,work_date,meter,brand,voltage,condition,notes,user_id,revision,created_at)
                         VALUES(?,?,?,?,?,?,?,?,?,?)""",
                       (collision_id, "2026-10-20", "000LEGADOTARDIO", "Marca legado", "240V", "Base Rota",
                        "Llegada tardía del proceso original", 7, 1, "2026-10-20T12:00:00Z"))
        app.init_db()
        app.init_db()
        events = self.result(self.supervisor, "/api/eventos")["records"]
        self.assertEqual(len(events), 4)
        production = next(row for row in events if row["id"] == new["id"])
        self.assertEqual(production["data"]["serie"], "000NUEVAPROD")
        self.assertIsNone(production["legacy_id"])
        late = next(row for row in events if row["legacy_id"] == collision_id)
        self.assertNotEqual(late["id"], new["id"])
        self.assertEqual(late["data"]["serie"], "000LEGADOTARDIO")
        corrected = next(row for row in events if row["legacy_id"] == 41)
        self.assertEqual(corrected["data"]["observaciones"], "Corregido en la aplicación nueva")

    def test_occupied_port_does_not_migrate_or_modify_another_database(self):
        blocked_dir = self.data_dir / "blocked-instance"
        blocked_dir.mkdir()
        untouched = blocked_dir / "laboratorio.db"
        with contextlib.closing(sqlite3.connect(untouched)) as db, db:
            db.executescript(LEGACY_SCHEMA)
            db.execute("INSERT INTO users(id,username,name,salt,hash,role) VALUES(?,?,?,?,?,?)",
                       (7, "supervisor_legado", "Supervisor de prueba", self.salt, self.digest, "supervisor"))
            db.execute("""INSERT INTO records(id,work_date,meter,brand,voltage,condition,notes,user_id,revision,created_at)
                         VALUES(1,'2026-10-22','000NOALTERAR','Marca legado','240V','Base Rota','Original',7,1,'2026-10-22T12:00:00Z')""")
        original_digest = hashlib.sha256(untouched.read_bytes()).digest()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen(1)
            result = subprocess.run([
                sys.executable, str(APP_ROOT / "app.py"), "--data-dir", str(blocked_dir),
                "--port", str(occupied.getsockname()[1]), "--no-browser",
            ], capture_output=True, timeout=15, cwd=APP_ROOT)
        self.assertNotEqual(result.returncode, 0, "A second process started on an occupied port")
        message = (result.stdout + result.stderr).decode("utf-8", errors="replace")
        self.assertRegex(message, r"El puerto \d+ ya está en uso")
        self.assertEqual(hashlib.sha256(untouched.read_bytes()).digest(), original_digest,
                         "A failed startup modified the selected database before obtaining its port")
        with contextlib.closing(sqlite3.connect(untouched)) as db, db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 0)
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertNotIn("production_events", tables)
            self.assertEqual(db.execute("SELECT meter FROM records WHERE id=1").fetchone()[0], "000NOALTERAR")


if __name__ == "__main__":
    unittest.main(verbosity=2)
