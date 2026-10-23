"""V6 acceptance checks through HTTP, using isolated synthetic databases."""
from __future__ import annotations

import base64
import concurrent.futures
import hashlib
import io
import json
from pathlib import Path
import secrets
import sqlite3
import tempfile
import unittest
import urllib.parse
import uuid
import zipfile

from test_application import Client, HTTPFixture, app


class V6HTTPTests(HTTPFixture, unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="laboratorio-v6-http-")
        self.addCleanup(self.temp.cleanup)
        self.start_http(Path(self.temp.name))
        self.addCleanup(self.stop_http)
        self.admin_password = secrets.token_urlsafe(22)
        self.admin = Client(self.base)
        self.result(self.admin, "/api/setup", {
            "username": "administracion_v6", "name": "Administración sintética V6",
            "password": self.admin_password,
        })
        self.assertEqual(self.admin.login("administracion_v6", self.admin_password)[0], 200)

    def person(self, code="90001", *, role="tecnico"):
        password = code if role == "tecnico" else secrets.token_urlsafe(20)
        payload = {"username": code, "name": "Persona sintética " + code,
                   "role": role, "activity_ids": [] if role == "visitante" else [
                       "revision", "sellado", "recepcion", "limpieza", "configuracion", "asignacion"]}
        if role != "tecnico":
            payload["password"] = password
        self.result(self.admin, "/api/usuarios", payload)
        person = next(row for row in self.result(self.admin, "/api/usuarios")["users"]
                      if row["username"] == code)
        client = Client(self.base)
        self.assertEqual(client.login(code, password)[0], 200)
        return person, client

    def event(self, activity, data, *, quantity=1, work_date="2026-10-22",
              actor=None, responsible=None, operation=None, expected=200):
        payload = {"activity_id": activity, "work_date": work_date,
                   "quantity": quantity, "data": data,
                   "operation_id": operation or str(uuid.uuid4())}
        if responsible is not None:
            payload["responsible_id"] = responsible
        return self.result(actor or self.admin, "/api/eventos", payload, expected=expected)

    def review(self, serial, *, result="Apto", work_date="2026-10-22", actor=None, **extra):
        values = {"serie": serial, "marca": "Marca de prueba", "voltaje": "240V",
                  "condicion": "Medidor en Óptimas Condiciones", "resultado": result, **extra}
        return self.event("revision", values, work_date=work_date, actor=actor)

    def order(self, *, process="PROCESO-V6-0001", number="ORDEN-V6-0001", expected=100,
              sap="00070001", due_date="2026-10-01"):
        return self.result(self.admin, "/api/ordenes", {
            "process": process, "order_number": number, "sap": sap,
            "expected": expected, "due_date": due_date,
            "notes": "Orden de aceptación con datos ficticios",
        })["order"]

    def delivery(self, order, quantity, *, actor=None, responsible=None, operation=None):
        return self.event("recepcion", {
            "numero_orden": order["order_number"], "proceso": order["process"],
            "sap": order["sap"], "marca": "Marca sintética de recepción",
            "cantidad_esperada": order["expected"],
        }, quantity=quantity, actor=actor, responsible=responsible, operation=operation)["record"]

    def test_sap_configurations_drive_sealing_without_restricting_brand_or_history(self):
        code = "00074001"
        self.result(self.admin, "/api/sap", {"code": code, "voltage": "240V", "classification": "Recuperado"})
        self.result(self.admin, "/api/sap", {
            "code": code, "configuration_id": "new", "voltage": "208V",
            "classification": "Nuevo", "brand": "Marca de referencia",
            "model": "Modelo de referencia", "label": "Variante de prueba", "active": True,
        })
        catalog = self.result(self.admin, "/api/sap")["items"]
        entry = next(row for row in catalog if row["code"] == code)
        self.assertGreaterEqual(len(entry["configurations"]), 2)
        config = next(row for row in entry["configurations"] if row["voltage"] == "208V")
        sealed = self.event("sellado", {
            "serie": "00000074001", "sap": code, "sap_config_id": config["id"],
            "marca": "Otra marca válida", "modelo": "Modelo elegido libremente",
        })["record"]
        self.assertEqual(sealed["data"]["serie"], "00000074001")
        self.assertEqual(sealed["data"]["sap"], code)
        self.assertEqual(sealed["data"]["clasificacion"], "Nuevo")
        self.assertEqual(sealed["data"]["voltaje"], "208V")
        self.assertEqual(sealed["data"]["marca"], "Otra marca válida")
        self.result(self.admin, "/api/sap", {
            "code": code, "configuration_id": config["id"], "voltage": "208V",
            "classification": "Recuperado", "brand": "Marca editada", "model": "Modelo editado",
            "label": "Variante editada", "active": True,
        })
        historical = next(row for row in self.result(self.admin, "/api/eventos")["records"]
                          if row["id"] == sealed["id"])
        self.assertEqual(historical["data"], sealed["data"])

    def test_order_process_is_unique_and_partial_delivery_can_be_certified(self):
        order = self.order()
        self.assertEqual((order["received"], order["pending"]), (0, 100))
        self.result(self.admin, "/api/ordenes", {
            "process": order["process"], "order_number": "ORDEN-DISTINTA",
            "sap": order["sap"], "expected": 5,
        }, expected=409)
        self.delivery(order, 35)
        partial = self.result(self.admin, f"/api/ordenes/{order['id']}")["order"]
        self.assertEqual((partial["received"], partial["pending"], partial["deliveries"]), (35, 65, 1))
        self.assertEqual(partial["signal"], "rojo")
        self.result(self.admin, f"/api/ordenes/{order['id']}/cerrar", {}, expected=409)
        self.delivery(order, 65)
        detail = self.result(self.admin, f"/api/ordenes/{order['id']}")
        self.assertEqual((detail["order"]["received"], detail["order"]["pending"]), (100, 0))
        self.assertEqual(len(detail["deliveries"]), 2)
        self.result(self.admin, f"/api/ordenes/{order['id']}/cerrar", {"reason": "Lote verificado"})
        closed = self.result(self.admin, f"/api/ordenes/{order['id']}")["order"]
        self.assertEqual(closed["state"], "cerrada")
        certificate = self.result(self.admin, f"/api/ordenes/{order['id']}/acta")["certificate"]
        self.assertEqual(len(certificate["hash"]), 64)
        canonical = json.dumps(certificate["snapshot"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.assertEqual(hashlib.sha256(canonical.encode()).hexdigest(), certificate["hash"])
        self.assertIn(order["process"], canonical)
        self.assertEqual(self.result(self.admin, f"/api/ordenes/{order['id']}/acta")["certificate"], certificate)
        status, body, headers = self.admin.request(f"/api/ordenes/{order['id']}/acta.pdf")
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith(b"%PDF-"))
        self.assertIn(b"%%EOF", body)
        self.assertIn("application/pdf", headers["Content-Type"])

    def test_closed_order_blocks_mutations_and_reopen_recalculates_pending(self):
        order = self.order(expected=12)
        event = self.delivery(order, 12)
        self.result(self.admin, f"/api/ordenes/{order['id']}/cerrar", {"reason": "Completado"})
        for action, payload in (("corregir", {"quantity": 11, "reason": "Conteo revisado"}),
                                ("anular", {"reason": "Entrega revisada"})):
            self.result(self.admin, f"/api/eventos/{event['id']}/{action}", payload, expected=409)
        self.result(self.admin, f"/api/ordenes/{order['id']}/reabrir", {}, expected=400)
        self.result(self.admin, f"/api/ordenes/{order['id']}/reabrir", {"reason": "Revisión de cantidades"})
        self.result(self.admin, f"/api/eventos/{event['id']}/corregir", {"quantity": 11, "reason": "Conteo verificado"})
        reopened = self.result(self.admin, f"/api/ordenes/{order['id']}")["order"]
        self.assertEqual((reopened["received"], reopened["pending"]), (11, 1))
        self.result(self.admin, f"/api/ordenes/{order['id']}/cerrar", {}, expected=409)

    def test_repeated_concurrent_delivery_is_one_event_and_one_contribution(self):
        order = self.order(expected=20)
        operation = str(uuid.uuid4())
        # Separate browser sessions avoid sharing mutable HTTP cookie jars across threads.
        clients = [Client(self.base) for _ in range(4)]
        for client in clients:
            self.assertEqual(client.login("administracion_v6", self.admin_password)[0], 200)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            records = list(pool.map(lambda c: self.delivery(order, 7, actor=c, operation=operation), clients))
        self.assertEqual(len({record["id"] for record in records}), 1)
        current = self.result(self.admin, f"/api/ordenes/{order['id']}")["order"]
        self.assertEqual((current["received"], current["deliveries"], current["pending"]), (7, 1, 13))

    def test_order_balances_remain_global_while_access_and_deliveries_are_scoped(self):
        first, technician = self.person()
        second, other = self.person("90002")
        _, visitor = self.person("visitante_v6", role="visitante")
        order = self.order(expected=10)
        self.delivery(order, 4, actor=technician)
        self.delivery(order, 6, actor=other)
        own = self.result(technician, f"/api/ordenes/{order['id']}")
        self.assertEqual((own["order"]["received"], own["order"]["pending"]), (10, 0))
        self.assertNotIn(second["name"], json.dumps(own, ensure_ascii=False))
        self.assertTrue(all(row["responsible_id"] == first["id"] for row in own["deliveries"]))
        self.result(technician, f"/api/ordenes/{order['id']}/cerrar", {}, expected=403)
        self.result(visitor, "/api/ordenes", expected=403)
        self.result(visitor, f"/api/ordenes/{order['id']}", expected=403)
        self.result(visitor, "/api/auditoria/integridad", expected=403)

    def test_quality_counts_and_calibration_use_explicit_denominators_and_roles(self):
        person, technician = self.person()
        _, visitor = self.person("visitante_v6", role="visitante")
        for serial, result in (("000QA1", "Apto"), ("000QA2", "Apto"),
                               ("000QA3", "No apto"), ("000QA4", "Pendiente"), ("000QA5", "")):
            extra = {"tipo_inspeccion": "Calibración", "valor_referencia": 100,
                     "valor_medido": 103, "tolerancia_pct": 2, "fallo": "Error de medición"} if serial == "000QA3" else {}
            self.review(serial, result=result, actor=technician, **extra)
        self.review("000OTRO", result="No apto")
        quality = self.result(technician, "/api/calidad?desde=2026-10-22&hasta=2026-10-22&granularity=diaria")
        summary = quality["summary"]
        self.assertEqual((summary["total"], summary["evaluated"], summary["approved"], summary["rejected"],
                          summary["pending"], summary["without_result"]), (5, 3, 2, 1, 1, 1))
        self.assertAlmostEqual(summary["approval_rate"], 200 / 3, delta=0.01)
        self.assertAlmostEqual(summary["rejection_rate"], 100 / 3, delta=0.01)
        self.assertEqual((summary["calibrations"], summary["calibrations_outside_tolerance"]), (1, 1))
        self.assertAlmostEqual(summary["mean_deviation_pct"], 3)
        self.assertEqual(len(quality["by_technician"]), 1)
        aggregate = self.result(visitor, "/api/calidad")
        self.assertEqual(aggregate["summary"]["total"], 6)
        self.assertEqual(aggregate["by_technician"], [])
        self.assertNotIn(person["name"], json.dumps(aggregate, ensure_ascii=False))
        self.result(visitor, "/api/calidad?responsible_id=" + str(person["id"]), expected=403)
        self.result(technician, "/api/calidad?responsible_id=999999", expected=403)

    def test_comparison_keeps_units_separate_and_handles_zero_base(self):
        for when, quantity in (("2026-09-22", 2), ("2026-10-22", 5)):
            self.event("limpieza", {"voltaje": "240V", "tiempo_minutos": 15, "condicion_visual": "Bueno"},
                       quantity=quantity, work_date=when)
        self.review("000SEP1", work_date="2026-09-22")
        self.review("000SEP2", work_date="2026-09-22")
        self.review("000OCT1", work_date="2026-10-22")
        self.event("asignacion", {"tipo_articulo": "Sello", "sap": "000SELL01", "destino": "Destino sintético"}, quantity=7)
        params = {"a_desde": "2026-09-01", "a_hasta": "2026-09-30",
                  "b_desde": "2026-10-01", "b_hasta": "2026-10-31", "granularity": "semanal"}
        query = "?" + urllib.parse.urlencode(params)
        report = self.result(self.admin, "/api/comparativas" + query)
        by_activity = {row["activity_id"]: row for row in report["rows"]}
        cleaning = by_activity["limpieza"]
        self.assertEqual((cleaning["a"], cleaning["b"], cleaning["delta"], cleaning["percent"]), (2, 5, 3, 150))
        review = by_activity["revision"]
        self.assertEqual((review["a"], review["b"], review["delta"], review["percent"]), (2, 1, -1, -50))
        assignment = by_activity["asignacion"]
        self.assertEqual((assignment["a"], assignment["b"], assignment["delta"]), (0, 7, 7))
        self.assertIsNone(assignment["percent"])
        self.assertEqual(assignment["percent_state"], "sin_base")
        self.assertEqual(report["summary"]["records_a"], 3)
        self.assertEqual(report["summary"]["records_b"], 3)
        self.assertTrue(report["series_a"])
        self.assertTrue(report["series_b"])
        invalid = dict(params, a_desde="2026-10-01", a_hasta="2026-09-30")
        self.result(self.admin, "/api/comparativas?" + urllib.parse.urlencode(invalid), expected=400)
        self.result(self.admin, "/api/comparativas?a_desde=2026-01-01", expected=400)
        for path in ("/api/comparativas.xlsx", "/api/comparativas.pdf"):
            status, body, headers = self.admin.request(path + query)
            self.assertEqual(status, 200)
            if path.endswith(".xlsx"):
                with zipfile.ZipFile(io.BytesIO(body)) as archive:
                    self.assertIsNone(archive.testzip())
                    self.assertIn("xl/worksheets/sheet1.xml", archive.namelist())
            else:
                self.assertTrue(body.startswith(b"%PDF-"))
                self.assertIn(b"%%EOF", body)

    def test_quality_templates_bulk_import_and_export_preserve_calibration_data(self):
        person, _ = self.person()
        import documents
        columns = ["work_date", "responsible", "serie", "marca", "voltaje", "condicion", "resultado",
                   "tipo_inspeccion", "valor_referencia", "valor_medido", "tolerancia_pct"]
        row = ["2026-10-22", person["username"], "000BULK-QA", "Marca sintética", "240V",
               "Medidor en Óptimas Condiciones", "Apto", "Calibración", "100", "100.5", "1"]
        raw = documents.write_csv(columns, [row])
        preview = self.result(self.admin, "/api/import/preview", {
            "activity_id": "revision", "filename": "calidad-v6.csv",
            "content_base64": base64.b64encode(raw).decode(),
        })
        self.assertEqual(preview["errors"], [])
        self.assertEqual(preview["valid_count"], 1)
        confirmation = {"preview_id": preview["preview_id"], "confirm_reentry": True}
        self.result(self.admin, "/api/import/confirm", confirmation)
        self.result(self.admin, "/api/import/confirm", confirmation)
        record = self.result(self.admin, "/api/eventos")["records"][0]
        self.assertEqual(record["data"]["serie"], "000BULK-QA")
        self.assertAlmostEqual(record["data"]["desviacion_pct"], 0.5)
        self.assertFalse(record["data"]["fuera_tolerancia"])
        self.assertEqual(self.result(self.admin, "/api/eventos")["total"], 1)
        status, template, _ = self.admin.request("/api/plantilla.csv?activity_id=revision")
        self.assertEqual(status, 200)
        self.assertIn(b"valor_referencia", template)
        for kind, marker in (("xlsx", b"PK"), ("pdf", b"%PDF-")):
            status, body, _ = self.admin.request("/api/calidad." + kind + "?desde=2026-10-22&hasta=2026-10-22")
            self.assertEqual(status, 200)
            self.assertTrue(body.startswith(marker))

    def test_analytics_downloads_apply_session_scope_and_visitor_redaction(self):
        first, technician = self.person()
        second, other = self.person("90002")
        _, visitor = self.person("visitante_v6", role="visitante")
        self.review("000PRIVATE-FIRST", actor=technician)
        self.review("000PRIVATE-SECOND", actor=other, result="No apto")
        import documents
        for client, forbidden in ((technician, second["name"]), (visitor, first["name"])):
            status, raw, _ = client.request("/api/calidad.xlsx?desde=2026-10-01&hasta=2026-10-31")
            self.assertEqual(status, 200)
            rows = documents.read_table("calidad.xlsx", raw)
            exported = json.dumps(rows, ensure_ascii=False)
            self.assertNotIn(forbidden, exported)
            self.assertNotIn("000PRIVATE-FIRST", exported)
            self.assertNotIn("000PRIVATE-SECOND", exported)
            if client is technician:
                self.assertIn(first["name"], exported)
            else:
                self.assertNotIn(second["name"], exported)
        for client in (technician, visitor):
            status, _, _ = client.request("/api/calidad.xlsx?responsible_id=" + str(second["id"]))
            self.assertEqual(status, 403)

    def test_audit_is_append_only_redacted_and_reinitialization_preserves_records(self):
        event = self.review("000AUDIT-V6")["record"]
        self.result(self.admin, f"/api/eventos/{event['id']}/corregir", {
            "reason": "Verificación sintética V6", "data": {"observaciones": "Observación corregida"},
        })
        integrity = self.result(self.admin, "/api/auditoria/integridad")
        self.assertTrue(integrity["ok"])
        self.assertGreater(integrity["entries"], 0)
        self.assertEqual(len(integrity["head_hash"]), 64)
        logs = self.result(self.admin, "/api/auditoria")["entries"]
        serialized = json.dumps(logs, ensure_ascii=False)
        self.assertNotIn(self.admin_password, serialized)
        self.assertNotIn('"salt"', serialized)
        self.assertNotIn('"password"', serialized)
        with app.database() as db:
            original_ids = [row[0] for row in db.execute("SELECT id FROM audit_entries ORDER BY id")]
            for statement in ("UPDATE audit_entries SET reason='forjado' WHERE id=?",
                              "DELETE FROM audit_entries WHERE id=?"):
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute(statement, (original_ids[0],))
        app.init_db()
        self.assertTrue(self.result(self.admin, "/api/auditoria/integridad")["ok"])
        with app.database() as db:
            remaining_ids = [row[0] for row in db.execute("SELECT id FROM audit_entries ORDER BY id")]
        self.assertEqual(remaining_ids, original_ids)
        current = self.result(self.admin, "/api/eventos")["records"][0]
        self.assertEqual((current["id"], current["activity_version"]), (event["id"], event["activity_version"]))
        self.assertEqual(current["data"]["observaciones"], "Observación corregida")
        client = Client(self.base)
        self.assertEqual(client.login("administracion_v6", self.admin_password)[0], 200)


if __name__ == "__main__":
    unittest.main()
