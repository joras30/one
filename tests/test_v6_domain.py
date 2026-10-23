"""Regresiones de dominio V6, bases temporales y personas ficticias."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "APLICACION_ACTUAL"))
import app
import operational
import production as p


class OperationalDomainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="laboratorio-v6-domain-")
        self.addCleanup(self.temp.cleanup)
        app.configure(self.temp.name, demo=False)
        app.init_db()
        with app.database() as db:
            uid = app.insert_user(db, "admin_ficticio", "Supervisión ficticia", "administrador", "ClaveFicticia2026!")
        self.user = {"id": uid, "name": "Supervisión ficticia", "role": "administrador"}

    def get(self, path, query=None):
        with app.database() as db:
            return p.handle_get(db, self.user, path, query or {})

    def post(self, path, data):
        with app.database() as db:
            return p.handle_post(db, self.user, path, data)

    def review(self, data=None):
        values = {"serie": "00000" + uuid.uuid4().hex[:8], "marca": "Marca ficticia", "voltaje": "240V", "condicion": "Base Rota"}
        values.update(data or {})
        return self.post("/api/eventos", {"activity_id": "revision", "work_date": "2026-10-23", "quantity": 1,
                                         "data": values, "operation_id": uuid.uuid4().hex})["record"]

    def seal(self, data):
        values = {"serie": "000" + uuid.uuid4().hex[:8], "marca": "Marca distinta"}
        values.update(data)
        return self.post("/api/eventos", {"activity_id": "sellado", "work_date": "2026-10-23", "quantity": 1,
                                         "data": values, "operation_id": uuid.uuid4().hex})["record"]

    def receipt(self, quantity=5, order="ORD-FICTICIA", process="PROC-FICTICIO", expected=10, sap="SAP-FICTICIO"):
        return self.post("/api/eventos", {"activity_id": "recepcion", "work_date": "2026-10-23", "quantity": quantity,
            "data": {"sap": sap, "numero_orden": order, "proceso": process, "marca": "Marca ficticia", "cantidad_esperada": expected},
            "operation_id": uuid.uuid4().hex})["record"]

    def test_configuration_created_as_new_has_no_duplicate_after_restart(self):
        config = self.post("/api/sap", {"code": "000045", "configuration_id": "new", "voltage": "277V", "classification": "Ensayo especial"})["configuration"]
        app.init_db()
        item = next(x for x in self.get("/api/sap")["items"] if x["code"] == "000045")
        self.assertEqual([x["id"] for x in item["configurations"]], [config["id"]])
        record = self.seal({"sap": "000045", "modelo": "Modelo libre"})
        self.assertEqual(record["data"]["clasificacion"], "Ensayo especial")
        self.assertEqual(record["data"]["voltaje"], "277V")

    def test_sap_brand_and_model_remain_independent_and_snapshot_survives_changes(self):
        config = self.post("/api/sap", {"code": "1003913", "configuration_id": "new", "voltage": "208V", "classification": "Nuevo", "brand": "Sugerencia", "model": "Sugerido"})["configuration"]
        record = self.seal({"sap": "1003913", "sap_config_id": config["id"], "marca": "Otra marca", "modelo": "Otro modelo"})
        self.assertEqual(record["data"]["clasificacion"], "Nuevo")
        self.assertEqual(record["data"]["marca"], "Otra marca")
        self.assertEqual(record["data"]["modelo"], "Otro modelo")
        self.post("/api/sap", {"code": "1003913", "configuration_id": config["id"], "voltage": "480V", "classification": "Recuperado"})
        fixed = self.post(f"/api/eventos/{record['id']}/corregir", {"reason": "Aclarar observación", "data": {"observaciones": "Texto corregido"}})["record"]
        self.assertEqual((fixed["data"]["voltaje"], fixed["data"]["clasificacion"]), ("208V", "Nuevo"))

    def test_multiple_compatible_configurations_require_explicit_selection(self):
        self.post("/api/sap", {"code": "1003913", "configuration_id": "new", "voltage": "240V", "classification": "Recuperado", "label": "Alternativa"})
        with self.assertRaises(p.ApiError) as error:
            self.seal({"sap": "1003913"})
        self.assertEqual(error.exception.status, 409)
        self.assertTrue(error.exception.details["needs_sap_configuration"])

    def test_quality_uses_signed_deviation_and_absolute_reference(self):
        record = self.review({"valor_referencia": -100, "valor_medido": -101, "tolerancia_pct": .5, "resultado": "No apto"})
        self.assertEqual(record["data"]["desviacion_pct"], -1)
        self.assertTrue(record["data"]["fuera_tolerancia"])
        equal = self.review({"valor_referencia": 100, "valor_medido": 101, "tolerancia_pct": 1, "resultado": "Apto"})
        self.assertFalse(equal["data"]["fuera_tolerancia"])

    def test_invalid_quality_is_atomic_and_derived_values_cannot_be_forged(self):
        before = self.get("/api/eventos")["total"]
        for values in ({"valor_referencia": 0, "valor_medido": 1, "tolerancia_pct": 1},
                       {"valor_referencia": 100},
                       {"valor_referencia": 100, "valor_medido": "NaN", "tolerancia_pct": 1},
                       {"valor_referencia": 100, "valor_medido": 103, "tolerancia_pct": 1, "resultado": "Apto"}):
            with self.subTest(values=values), self.assertRaises(p.ApiError):
                self.review(values)
        self.assertEqual(self.get("/api/eventos")["total"], before)
        record = self.review({"valor_referencia": 100, "valor_medido": 102, "tolerancia_pct": 1,
                              "desviacion_pct": 0, "fuera_tolerancia": False})
        self.assertEqual(record["data"]["desviacion_pct"], 2)
        self.assertTrue(record["data"]["fuera_tolerancia"])

    def test_audit_hashes_and_append_only_guards_survive_reinitialisation(self):
        self.review()
        with app.database() as db:
            before = [tuple(row) for row in db.execute("SELECT * FROM audit_entries ORDER BY id")]
            for sql in ("UPDATE audit_entries SET reason='alterado'", "DELETE FROM audit_entries"):
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute(sql)
        app.init_db()
        with app.database() as db:
            self.assertEqual(before, [tuple(row) for row in db.execute("SELECT * FROM audit_entries ORDER BY id")])
        self.assertTrue(self.get("/api/auditoria/integridad")["ok"])

    def test_direct_unhashed_insert_is_detected(self):
        self.review()
        with app.database() as db:
            db.execute("INSERT INTO audit_entries(entity,entity_id,action,created_at) VALUES('ficticio','1','crear',?)", (p.now(),))
        self.assertFalse(self.get("/api/auditoria/integridad")["ok"])

    def test_overdelivery_and_closed_order_guards_preserve_receipts(self):
        first = self.receipt(quantity=10)
        order = self.get("/api/ordenes")["orders"][0]
        self.post(f"/api/ordenes/{order['id']}/cerrar", {})
        for path, payload in ((f"/api/eventos/{first['id']}/corregir", {"reason": "Cambio", "quantity": 9}),
                              (f"/api/eventos/{first['id']}/anular", {"reason": "Cambio"}),
                              (f"/api/eventos/{first['id']}/restaurar", {"reason": "Cambio"})):
            with self.subTest(path=path), self.assertRaises(p.ApiError):
                self.post(path, payload)
        with self.assertRaises(p.ApiError):
            self.receipt(quantity=1)
        self.post(f"/api/ordenes/{order['id']}/reabrir", {"reason": "Revisar entrega adicional"})
        self.receipt(quantity=1)
        over = self.get("/api/ordenes")["orders"][0]
        self.assertEqual(over["excess"], 1)
        self.assertEqual(over["signal"], "rojo")
        with self.assertRaises(p.ApiError):
            self.post(f"/api/ordenes/{order['id']}/cerrar", {})

    def test_historical_certificates_remain_addressable_after_reclosing(self):
        self.receipt(quantity=10)
        order = self.get("/api/ordenes")["orders"][0]
        first = self.post(f"/api/ordenes/{order['id']}/cerrar", {})["certificate"]
        self.post(f"/api/ordenes/{order['id']}/reabrir", {"reason": "Segunda verificación"})
        second = self.post(f"/api/ordenes/{order['id']}/cerrar", {"reason": "Verificado de nuevo"})["certificate"]
        historical = self.get(f"/api/ordenes/{order['id']}/acta", {"certificate_id": str(first["id"])})["certificate"]
        self.assertEqual(historical["snapshot"], first["snapshot"])
        self.assertFalse(historical["current"])
        self.assertEqual(historical["hash"], hashlib.sha256(p._json(first["snapshot"]).encode()).hexdigest())
        current = self.get(f"/api/ordenes/{order['id']}/acta")["certificate"]
        self.assertTrue(current["current"])
        self.assertEqual(current["id"], second["id"])
        self.assertEqual(len(self.get(f"/api/ordenes/{order['id']}")["certificates"]), 2)
        with self.assertRaises(p.ApiError):
            self.get(f"/api/ordenes/{order['id']}/acta", {"certificate_id": "99999"})

    def test_legacy_receipt_process_collisions_are_preserved_and_can_be_resolved(self):
        with app.database() as db:
            for index in (1, 2):
                values = {"sap": f"SAP-{index}", "numero_orden": f"LEGACY-{index}", "proceso": "Proceso descriptivo antiguo", "marca": "Marca ficticia", "cantidad_esperada": 5}
                db.execute("""INSERT INTO production_events(activity_id,activity_version,work_date,responsible_id,recorded_by,quantity,unit,data_json,created_at,updated_at)
                    VALUES('recepcion',1,'2026-10-22',?,?,5,'medidores',?,?,?)""", (self.user["id"], self.user["id"], p._json(values), p.now(), p.now()))
            original = [tuple(r) for r in db.execute("SELECT id,data_json FROM production_events ORDER BY id")]
        app.init_db()
        orders = self.get("/api/ordenes")["orders"]
        self.assertEqual(len(orders), 2)
        self.assertTrue(all(o["process_conflict"] for o in orders))
        selected = orders[0]
        self.post("/api/ordenes", {"id": selected["id"], "process": "PROC-UNICO-RESUELTO", "reason": "Asignar número de proceso único"})
        self.assertFalse(any(o["process_conflict"] for o in self.get("/api/ordenes")["orders"]))
        with app.database() as db:
            self.assertEqual(original, [tuple(r) for r in db.execute("SELECT id,data_json FROM production_events ORDER BY id")])

    def test_calculated_quality_columns_are_in_operational_exports(self):
        self.review({"valor_referencia": 100, "valor_medido": 100.5, "tolerancia_pct": 1})
        with app.database() as db:
            exported = p.export_rows(db, self.user, {"activity_id": "revision"})
        self.assertIn("Desviación calculada (%)", exported["headers"])
        self.assertIn("Fuera de tolerancia", exported["headers"])
        self.assertEqual(exported["rows"][0][-2:], [.5, "No"])

    def test_master_changes_do_not_invalidate_receipt_snapshot_corrections(self):
        event = self.receipt(quantity=5)
        order = self.get("/api/ordenes")["orders"][0]
        self.post("/api/ordenes", {"id": order["id"], "expected": 12, "process": "PROC-CORREGIDO", "reason": "Ajustar orden"})
        updated = self.post(f"/api/eventos/{event['id']}/corregir", {"reason": "Aclarar observación", "data": {"observaciones": "Detalle aclarado"}})["record"]
        self.assertEqual(updated["data"]["proceso"], event["data"]["proceso"])
        self.assertEqual(updated["data"]["cantidad_esperada"], 10)
        self.assertEqual(self.get("/api/ordenes")["orders"][0]["expected"], 12)
        receipt = self.get("/api/recepciones")["receipts"][0]
        self.assertEqual((receipt["expected"], receipt["pending"]), (12, 7))

    def test_orders_without_deliveries_appear_in_pending_dashboard(self):
        self.post("/api/ordenes", {"process": "PROC-PENDIENTE", "order_number": "ORD-PENDIENTE", "sap": "SAP-PENDIENTE", "expected": 20})
        self.assertEqual(self.get("/api/dashboard")["receipts_pending"], 1)
        receipt = self.get("/api/recepciones")["receipts"][0]
        self.assertEqual((receipt["received"], receipt["expected"], receipt["pending"]), (0, 20, 20))

    def test_partial_historical_cutoff_does_not_appear_closed_or_green(self):
        first = self.receipt(quantity=5)
        self.post(f"/api/eventos/{first['id']}/corregir", {"reason": "Fecha ficticia histórica", "work_date": "2026-01-15"})
        second = self.receipt(quantity=5)
        self.post(f"/api/eventos/{second['id']}/corregir", {"reason": "Fecha ficticia histórica", "work_date": "2026-02-15"})
        order = self.get("/api/ordenes")["orders"][0]
        self.post(f"/api/ordenes/{order['id']}/cerrar", {})
        historical = self.get("/api/ordenes", {"hasta": "2026-01-31"})["orders"][0]
        self.assertEqual(historical["received"], 5)
        self.assertEqual(historical["pending"], 5)
        self.assertEqual(historical["state"], "pendiente")
        self.assertEqual(historical["administrative_state"], "cerrada")
        self.assertNotEqual(historical["signal"], "verde")

    def test_quality_overflow_and_custom_field_types_return_validation_errors(self):
        with self.assertRaises(p.ApiError):
            self.review({"valor_referencia": 1e-308, "valor_medido": 1, "tolerancia_pct": 0})
        activity = next(a for a in self.get("/api/actividades")["activities"] if a["id"] == "revision")
        for field in activity["fields"]:
            if field["key"] == "valor_referencia":
                field["type"] = "text"
        self.post("/api/actividades", {**activity, "fields": activity["fields"]})
        with self.assertRaises(p.ApiError):
            self.review({"valor_referencia": "sin referencia", "valor_medido": 100, "tolerancia_pct": 1})

    def test_replace_statements_cannot_bypass_immutable_guards(self):
        self.receipt(quantity=10)
        order = self.get("/api/ordenes")["orders"][0]
        certificate = self.post(f"/api/ordenes/{order['id']}/cerrar", {})["certificate"]
        with app.database() as db:
            audit_id = db.execute("SELECT MIN(id) FROM audit_entries").fetchone()[0]
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("INSERT OR REPLACE INTO audit_entries(id,entity,entity_id,action,created_at) VALUES(?,'falso','1','sustituir',?)", (audit_id, p.now()))
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("INSERT OR REPLACE INTO receipt_certificates(id,order_id,number,snapshot_json,hash,created_by,created_at) VALUES(?,?,?,?,?,?,?)", (certificate["id"], order["id"], certificate["number"], '{}', 'falso', self.user["id"], p.now()))

    def test_legacy_cancelled_expected_and_mixed_processes_require_review(self):
        with app.database() as db:
            for process, expected, state in (("PROC-ORIGINAL", 10, "valido"), ("PROC-ALTERNO", 999, "anulado")):
                values = {"sap": "SAP-LEGACY", "numero_orden": "ORD-LEGACY", "proceso": process, "marca": "Marca ficticia", "cantidad_esperada": expected}
                db.execute("""INSERT INTO production_events(activity_id,activity_version,work_date,responsible_id,recorded_by,quantity,unit,data_json,state,created_at,updated_at)
                    VALUES('recepcion',1,'2026-10-22',?,?,10,'medidores',?,?,?,?)""", (self.user["id"], self.user["id"], p._json(values), state, p.now(), p.now()))
        app.init_db()
        order = self.get("/api/ordenes")["orders"][0]
        self.assertEqual(order["expected"], 10)
        self.assertTrue(order["process_conflict"])
        with self.assertRaises(p.ApiError):
            self.post(f"/api/ordenes/{order['id']}/cerrar", {})
        self.post("/api/ordenes", {"id": order["id"], "process": "PROC-VERIFICADO", "reason": "Verificar discrepancia histórica"})
        self.post(f"/api/ordenes/{order['id']}/cerrar", {})


if __name__ == "__main__":
    unittest.main()
