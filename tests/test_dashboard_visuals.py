"""Métricas visuales: cantidades, fechas, saldos y permisos con datos ficticios."""
import json
from pathlib import Path
import sqlite3
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "APLICACION_ACTUAL"))
import operational
import production


class DashboardVisualTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:", isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT,name TEXT,role TEXT,access_role TEXT,active INTEGER);
            CREATE TABLE catalog(id INTEGER PRIMARY KEY,kind TEXT,label TEXT,active INTEGER);
            INSERT INTO users VALUES(1,'admin_ficticio','Administración ficticia','supervisor','administrador',1);
            INSERT INTO users VALUES(2,'90001','Persona ficticia Uno','tecnico','tecnico',1);
            INSERT INTO users VALUES(3,'90002','Persona ficticia Dos','tecnico','tecnico',1);
        """)
        production.init_schema(self.db)
        self.admin = {"id": 1, "role": "administrador"}
        self.tech = {"id": 2, "role": "tecnico"}
        self.visitor = {"id": 4, "role": "visitante"}

    def event(self, day, activity="revision", quantity=1, unit=None, person=2, state="valido", **fields):
        definition = production._activity(self.db, activity)
        return self.db.execute("""INSERT INTO production_events(
            activity_id,activity_version,work_date,responsible_id,recorded_by,quantity,unit,data_json,state,operation_id,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (activity, definition["version"], day, person, 1, quantity,
            unit or definition["unit"], json.dumps(fields), state, uuid.uuid4().hex, production.now(), production.now())).lastrowid

    def dashboard(self, user=None, **query):
        return production._dashboard(self.db, user or self.admin, {"desde": "2026-01-01", "hasta": "2026-01-03", "granularity": "diaria", **query})

    def order(self, name="FICTICIA", expected=100):
        return operational.save_order(self.db, self.admin, {"process": name, "order_number": name,
            "sap": "SAP-FICTICIO", "expected": expected})["order"]["id"]

    def delivery(self, order, day, quantity):
        event = self.event(day, "recepcion", quantity, sap="SAP-FICTICIO")
        self.db.execute("INSERT INTO receipt_links(event_id,order_id) VALUES(?,?)", (event, order))

    def test_temporal_quantities_fill_missing_dates_and_separate_units(self):
        self.event("2026-01-01", "limpieza", 20)
        self.event("2026-01-03", "limpieza", 30)
        self.event("2026-01-03", "limpieza", 7, unit="lotes")
        self.event("2026-01-02", resultado="Apto")
        self.event("2026-01-02", "limpieza", 999, state="anulado")
        data = self.dashboard()
        series = {(row["activity_id"], row["unit"]): row for row in data["trend"]["series"]}
        self.assertEqual([point["value"] for point in series["limpieza", "medidores"]["points"]], [20, 0, 30])
        self.assertEqual(series["limpieza", "lotes"]["total"], 7)
        self.assertEqual(series["revision", "revisiones"]["total"], 1)
        self.assertEqual([point["value"] for point in data["trend"]["records"]], [1, 1, 2])
        self.assertEqual(data["trend"]["series"][0]["points"][0]["date"], "2026-01-01")

    def test_quality_counts_reviews_and_uses_evaluated_denominator(self):
        self.event("2026-01-01", serie="00001", resultado="Apto")
        self.event("2026-01-02", serie="00001", resultado="Apto")
        self.event("2026-01-02", serie="00002", resultado="No apto")
        self.event("2026-01-03", resultado="Pendiente")
        self.event("2026-01-03", "sellado", resultado="Apto")
        data = self.dashboard()
        quality = data["summary_quality"]
        self.assertEqual((quality["total"], quality["evaluated"], quality["approved"], quality["rejected"], quality["pending"]), (4, 3, 2, 1, 1))
        self.assertAlmostEqual(quality["approval_rate"], 66.666667)
        self.assertEqual(data["identified_unique"], 2)
        self.assertEqual(data["reentries"], 1, "Una revisión sin serie no demuestra un reingreso.")

    def test_roles_and_filters_apply_to_every_visual(self):
        self.event("2026-01-01", resultado="Apto", sap="0001")
        self.event("2026-01-01", person=3, resultado="No apto", sap="0002")
        self.assertEqual(self.dashboard(self.tech)["summary_quality"]["total"], 1)
        scoped = self.dashboard(sap="0001")
        self.assertEqual(scoped["summary_quality"]["approved"], 1)
        self.assertEqual(scoped["trend"]["series"][0]["total"], 1)
        visitor = self.dashboard(self.visitor)
        self.assertEqual(visitor["batch_progress"], [])
        self.assertNotIn("Persona ficticia", json.dumps(visitor))
        self.assertNotIn("90001", json.dumps(visitor))

    def test_empty_range_has_zero_buckets_and_no_fabricated_rate(self):
        data = self.dashboard()
        self.assertEqual(data["trend"]["series"], [])
        self.assertEqual([point["value"] for point in data["trend"]["records"]], [0, 0, 0])
        self.assertIsNone(data["summary_quality"]["approval_rate"])
        self.assertIsNone(data["receipt_summary"]["fulfillment_pct"])

    def test_iso_weeks_are_calendar_buckets_and_invalid_granularity_rejected(self):
        self.event("2026-01-01", "limpieza", 10)
        data = self.dashboard(granularity="semanal")
        self.assertEqual(data["trend"]["series"][0]["points"][0]["label"], "2026-S01")
        self.assertEqual(data["trend"]["series"][0]["points"][0]["from"], "2026-01-01")
        with self.assertRaises(production.ApiError):
            self.dashboard(granularity="inventada")

    def test_excess_does_not_hide_other_order_pending_and_unknowns(self):
        first = self.order("PROCESO-FICTICIO-A", 100)
        second = self.order("PROCESO-FICTICIO-B", 100)
        unknown = self.order("PROCESO-FICTICIO-C", None)
        self.delivery(first, "2026-01-01", 150)
        self.delivery(second, "2026-01-01", 50)
        self.delivery(unknown, "2026-01-01", 20)
        result = operational.list_orders(self.db, self.admin, {})
        summary = result["summary"]
        self.assertEqual((summary["expected_total"], summary["received_total"], summary["pending_total"], summary["excess_total"]), (200, 220, 50, 50))
        self.assertEqual(summary["fulfillment_pct"], 75)
        self.assertEqual(summary["unknown_orders"], 1)
        self.assertFalse(summary["expected_known"])
        progress = {order["id"]: order["progress_pct"] for order in result["orders"]}
        self.assertEqual(progress[first], 150)
        self.assertIsNone(progress[unknown])

    def test_receipt_progress_honors_cutoff_and_visitor_details_remain_private(self):
        order = self.order("PROCESO-FICTICIO-CORTE", 100)
        self.delivery(order, "2026-01-01", 40)
        self.delivery(order, "2026-01-03", 60)
        data = self.dashboard(hasta="2026-01-02")
        self.assertEqual(data["receipt_summary"]["received_total"], 40)
        self.assertEqual(data["receipt_summary"]["fulfillment_pct"], 40)
        self.assertEqual(data["batch_progress"][0]["pending"], 60)
        visitor = self.dashboard(self.visitor, hasta="2026-01-02")
        self.assertEqual(visitor["receipt_summary"]["received_total"], 40)
        self.assertEqual(visitor["batch_progress"], [])
        self.assertNotIn("PROCESO-FICTICIO-CORTE", json.dumps(visitor))


if __name__ == "__main__":
    unittest.main()
