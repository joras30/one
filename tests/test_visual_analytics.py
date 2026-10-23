"""Contratos para tablas y gráficos operativos con datos sintéticos y períodos exactos."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys
import unittest
import uuid
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "APLICACION_ACTUAL"))
import analytics
import production


class VisualAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:", isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.addCleanup(self.db.close)
        self.db.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT,name TEXT,role TEXT,access_role TEXT,active INTEGER);
            CREATE TABLE catalog(id INTEGER PRIMARY KEY,kind TEXT,label TEXT,active INTEGER);
            INSERT INTO users VALUES(1,'admin_sintetico','Administración sintética','supervisor','administrador',1);
            INSERT INTO users VALUES(2,'91001','Técnico sintético Alfa','tecnico','tecnico',1);
            INSERT INTO users VALUES(3,'91002','Técnico sintético Beta','tecnico','tecnico',1);
            INSERT INTO users VALUES(4,'visita_sintetica','Visita sintética','tecnico','visitante',1);
        """)
        production.init_schema(self.db)
        self.admin = {"id": 1, "role": "administrador"}
        self.tech = {"id": 2, "role": "tecnico"}
        self.visitor = {"id": 4, "role": "visitante"}
        self.periods = {"a_desde": "2026-01-01", "a_hasta": "2026-01-03",
                        "b_desde": "2026-02-01", "b_hasta": "2026-02-03"}

    def event(self, day, activity="revision", *, person=2, quantity=1, unit=None, state="valido", **data):
        definition = production._activity(self.db, activity)
        fields = {"serie": "000-SINT-" + uuid.uuid4().hex, "sap": "1003913", "marca": "Marca sintética", **data}
        return self.db.execute("""INSERT INTO production_events(
            activity_id,activity_version,work_date,responsible_id,recorded_by,quantity,unit,data_json,state,operation_id,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (activity, definition["version"], day, person, 1, quantity,
            unit or definition["unit"], json.dumps(fields), state, uuid.uuid4().hex, production.now(), production.now())).lastrowid

    def goal(self, *, person=2, activity="revision", start="2026-01-01", end="2026-01-03", target=3, unit=None):
        definition = production._activity(self.db, activity)
        return self.db.execute("""INSERT INTO production_goals(
            responsible_id,activity_id,start_date,end_date,target,unit,created_by,created_at) VALUES(?,?,?,?,?,?,1,?)""",
            (person, activity, start, end, target, unit or definition["unit"], production.now())).lastrowid

    def compare(self, user=None, **query):
        return analytics.handle_get(self.db, user or self.admin, "/api/comparativas", {**self.periods, **query})

    def quality(self, user=None, **query):
        return analytics.handle_get(self.db, user or self.admin, "/api/calidad",
                                    {"desde": "2026-01-01", "hasta": "2026-01-03", **query})

    def test_person_activity_rows_keep_responsible_and_historical_units_separate(self):
        self.event("2026-01-01", activity="limpieza", quantity=10)
        self.event("2026-02-01", activity="limpieza", quantity=15)
        self.event("2026-02-01", activity="limpieza", person=3, quantity=7)
        self.event("2026-02-01", activity="limpieza", quantity=2, unit="lotes")
        self.event("2026-01-01", resultado="Apto")
        result = self.compare(group_by="technician_activity")
        rows = {(row["responsible_id"], row["activity_id"], row["unit"]): row for row in result["rows"]}
        self.assertEqual(len(rows), 4)
        cleaning = rows[(2, "limpieza", "medidores")]
        self.assertEqual((cleaning["a"], cleaning["b"], cleaning["delta"], cleaning["percent"]), (10, 15, 5, 50))
        self.assertEqual(cleaning["responsible_username"], "91001")
        self.assertEqual(cleaning["activity_ids"], ["limpieza"])
        self.assertEqual(rows[(2, "limpieza", "lotes")]["b"], 2)
        self.assertEqual(rows[(3, "limpieza", "medidores")]["a"], 0)
        self.assertTrue(all(row["responsible_id"] is None for row in self.compare()["rows"]))

    def test_technician_group_mixed_activities_has_no_fabricated_single_goal(self):
        self.event("2026-01-01", activity="limpieza", quantity=10)
        self.event("2026-02-01", activity="sellado", quantity=20)
        self.goal(activity="limpieza", target=15)
        row = self.compare(group_by="technician")["rows"][0]
        self.assertEqual(row["unit"], "medidores")
        self.assertEqual((row["a"], row["b"]), (10, 20))
        self.assertEqual(row["activity_ids"], ["limpieza", "sellado"])
        self.assertIsNone(row["activity_id"])
        self.assertIsNone(row["target_a"])
        self.assertEqual(row["target_scope_a"], "multiple_activities")
        self.assertIn("no representan medidores físicos únicos", self.compare(group_by="technician")["comparison_scope"])

    def test_quality_comparison_uses_evaluated_reviews_and_percentage_points(self):
        self.event("2026-01-01", resultado="Apto")
        self.event("2026-01-02", resultado="No apto")
        self.event("2026-01-03", resultado="Pendiente")
        self.event("2026-02-01", resultado="No apto")
        self.event("2026-02-02", resultado="No apto", state="anulado")
        self.event("2026-01-01", activity="limpieza", quantity=10, resultado="No apto")
        rows = {row["activity_id"]: row for row in self.compare(group_by="technician_activity")["rows"]}
        review, cleaning = rows["revision"], rows["limpieza"]
        self.assertEqual((review["evaluated_a"], review["approved_a"], review["rejected_a"]), (2, 1, 1))
        self.assertEqual((review["rejection_rate_a"], review["rejection_rate_b"], review["rejection_rate_delta_pp"]), (50, 100, 50))
        self.assertEqual((cleaning["approved_a"], cleaning["rejected_a"], cleaning["evaluated_a"]), (0, 0, 0))
        self.assertIsNone(cleaning["rejection_rate_a"])
        self.assertIsNone(cleaning["rejection_rate_delta_pp"])

    def test_trends_are_actual_quantities_including_empty_calendar_buckets(self):
        self.event("2026-01-01", activity="limpieza", quantity=8)
        self.event("2026-01-03", activity="limpieza", quantity=4)
        self.event("2026-01-03", activity="limpieza", quantity=6)
        row = self.compare(group_by="technician_activity")["rows"][0]
        self.assertEqual([point["value"] for point in row["trend_a"]], [8, 0, 10])
        self.assertEqual([point["records"] for point in row["trend_a"]], [1, 0, 2])
        self.assertEqual(sum(point["value"] for point in row["trend_a"]), row["a"])
        self.assertEqual([point["value"] for point in row["trend_b"]], [0, 0, 0])
        weekly = self.compare(group_by="technician_activity", granularity="semanal")["rows"][0]
        self.assertEqual(weekly["trend_a"], [{"label": "2026-S01", "from": "2026-01-01", "to": "2026-01-03", "value": 18, "records": 3}])

    def test_targets_require_exact_dates_unit_and_no_unattributable_technical_filter(self):
        self.event("2026-01-01", resultado="Apto")
        self.event("2026-02-01", resultado="Apto")
        self.goal(target=4)
        self.goal(start="2026-02-01", end="2026-02-02", target=8)
        self.goal(start="2026-02-01", end="2026-02-03", target=10, unit="medidores")
        row = next(row for row in self.compare(group_by="technician_activity")["rows"] if row["unit"] == "revisiones")
        self.assertEqual((row["target_a"], row["attainment_a"], row["target_scope_a"]), (4, 25, "exact_period"))
        self.assertIsNone(row["target_b"])
        self.assertEqual(row["target_scope_b"], "no_exact_goal")
        filtered = self.compare(group_by="technician_activity", sap="1003913")["rows"][0]
        self.assertIsNone(filtered["target_a"])
        self.assertIsNone(filtered["attainment_a"])
        self.assertEqual(filtered["target_scope_a"], "filtered_subset")
        self.goal(start="2026-01-02", end="2026-01-02", target=2)
        overlapping = next(row for row in self.compare(group_by="technician_activity")["rows"] if row["unit"] == "revisiones")
        self.assertIsNone(overlapping["target_a"])
        self.assertEqual(overlapping["target_scope_a"], "ambiguous_goals")

    def test_activity_target_never_ignores_contributors_without_assigned_goal(self):
        self.event("2026-01-01", resultado="Apto")
        self.event("2026-01-01", person=3, resultado="Apto")
        self.goal(target=4)
        self.assertEqual(self.compare()["rows"][0]["target_scope_a"], "unassigned_contributors")
        self.assertIsNone(self.compare()["rows"][0]["target_a"])
        self.goal(person=3, target=6)
        row = self.compare()["rows"][0]
        self.assertEqual((row["target_a"], row["attainment_a"]), (10, 20))
        own = self.compare(self.tech)["rows"][0]
        self.assertEqual((own["target_a"], own["attainment_a"]), (4, 25))

    def test_quality_person_target_and_trend_distinguish_quantity_from_review_records(self):
        self.event("2026-01-01", quantity=2, resultado="Apto")
        self.event("2026-01-03", resultado="No apto")
        self.goal(target=6)
        person = self.quality()["by_technician"][0]
        self.assertEqual((person["total"], person["produced_quantity"]), (2, 3))
        self.assertEqual(person["quantities_by_unit"], {"revisiones": 3})
        self.assertEqual((person["assigned_target"], person["attainment"]), (6, 50))
        self.assertEqual([point["value"] for point in person["trend"]], [1, 0, 1])
        self.event("2026-01-02", unit="medidores", resultado="Apto")
        mixed = self.quality()["by_technician"][0]
        self.assertIsNone(mixed["assigned_target"])
        self.assertIsNone(mixed["produced_quantity"])
        self.assertEqual(mixed["target_scope"], "multiple_units")

    def test_failure_detail_has_recorded_facts_authorized_pagination_and_no_severity(self):
        first = self.event("2026-01-01", resultado="No apto", serie="000-ALFA")
        second = self.event("2026-01-02", resultado="Apto", serie="000-BETA", tipo_inspeccion="Calibración",
                            valor_referencia=100, valor_medido=103, tolerancia_pct=2, fuera_tolerancia=False)
        self.event("2026-01-03", resultado="Pendiente", serie="000-PEND")
        result = self.quality(failure_limit=1)
        self.assertEqual((result["failure_count"], result["failure_has_more"]), (2, True))
        detail = result["detailed_failures"][0]
        self.assertEqual((detail["event_id"], detail["serial"], detail["outside_tolerance"]), (second, "000-BETA", True))
        self.assertEqual(detail["failure"], "")
        self.assertNotIn("severity", detail)
        following = self.quality(failure_offset=1, failure_limit=1)
        self.assertEqual(following["detailed_failures"][0]["event_id"], first)
        self.assertFalse(following["failure_has_more"])

    def test_visitors_have_no_personal_grouping_identity_or_operational_free_text(self):
        self.event("2026-01-01", resultado="No apto", serie="000-PRIVADO", fallo="91001 Alfa 000-PRIVADO",
                   tipo_inspeccion="91001 Alfa 000-PRIVADO")
        result = self.quality(self.visitor)
        self.assertEqual(result["by_technician"], [])
        self.assertEqual(result["detailed_failures"], [])
        self.assertEqual(result["failure_count"], 0)
        serialized = json.dumps(result)
        self.assertNotIn("91001", serialized)
        self.assertNotIn("000-PRIVADO", serialized)
        self.assertNotIn("Alfa", serialized)
        for group_by in ("technician", "technician_activity"):
            with self.assertRaises(production.ApiError) as error:
                self.compare(self.visitor, group_by=group_by)
            self.assertEqual(error.exception.status, 403)
        self.assertTrue(all(row["responsible_name"] is None for row in self.compare(self.visitor)["rows"]))

    def test_technician_comparison_failure_detail_and_exports_keep_own_scope(self):
        self.event("2026-01-01", resultado="No apto", fallo="Fallo propio")
        self.event("2026-01-02", person=3, resultado="No apto", fallo="Fallo otro", serie="000-OTRO")
        rows = self.compare(self.tech, group_by="technician_activity")["rows"]
        self.assertEqual({row["responsible_id"] for row in rows}, {2})
        self.assertEqual(self.quality(self.tech)["failure_count"], 1)
        with self.assertRaises(production.ApiError) as error:
            self.compare(self.tech, group_by="technician_activity", responsible_id=3)
        self.assertEqual(error.exception.status, 403)
        for report, query in (("comparativas", {**self.periods, "group_by": "technician_activity"}),
                              ("calidad", {"desde": "2026-01-01", "hasta": "2026-01-03"})):
            _, exported, _ = analytics.export_rows(self.db, self.tech, query, report)
            text = json.dumps(exported)
            self.assertNotIn("91002", text)
            self.assertNotIn("000-OTRO", text)
            self.assertNotIn("Fallo otro", text)

    def test_exports_preserve_grouping_quality_meta_context_and_all_failure_details(self):
        self.event("2026-01-01", resultado="Apto")
        self.event("2026-02-01", resultado="No apto", fallo="Fallo sintético")
        self.goal(target=4)
        headers, rows, title = analytics.export_rows(self.db, self.admin,
            {**self.periods, "group_by": "technician_activity", "granularity": "mensual"}, "comparativas")
        self.assertTrue(all(len(row) == len(headers) for row in rows))
        exported = dict(zip(headers, next(row for row in rows if row[0] == "Técnico / actividad")))
        self.assertEqual((exported["Código empleado"], exported["Aptos A"], exported["No aptos B"]), ("91001", 1, 1))
        self.assertEqual((exported["Meta A"], exported["Cumplimiento A %"], exported["Variación rechazo pp"]), (4, 25, 100))
        self.assertIn("Por técnico, actividad y unidad", json.dumps(rows, ensure_ascii=False))
        self.assertIn("Por técnico, actividad y unidad", title)
        self.event("2026-02-02", resultado="No apto", serie="000-COMPLETO")
        headers, rows, _ = analytics.export_rows(self.db, self.admin,
            {"desde": "2026-02-01", "hasta": "2026-02-03", "failure_offset": 1, "failure_limit": 1}, "calidad")
        self.assertTrue(all(len(row) == len(headers) for row in rows))
        self.assertEqual(sum(row[0] == "Detalle de fallo" for row in rows), 2)
        self.assertIn("000-COMPLETO", json.dumps(rows))
        with mock.patch.object(analytics, "MAX_REPORT_ROWS", 1), self.assertRaises(production.ApiError) as error:
            analytics.export_rows(self.db, self.admin, {**self.periods, "group_by": "technician_activity"}, "comparativas")
        self.assertEqual(error.exception.status, 413)

    def test_invalid_grouping_and_failure_pagination_are_explicit(self):
        with self.assertRaises(production.ApiError):
            self.compare(group_by="supplier")
        for query in ({"failure_limit": 0}, {"failure_limit": 1001}, {"failure_offset": -1},
                      {"failure_limit": True}, {"failure_offset": "0.5"}):
            with self.subTest(query=query), self.assertRaises(production.ApiError):
                self.quality(**query)

    def test_exact_goals_include_zero_production_technicians_and_zero_trends(self):
        self.goal(person=2, target=5)
        self.goal(person=3, target=5)
        self.event("2026-01-01", resultado="Apto")
        for grouping in ("technician", "technician_activity"):
            rows = {row["responsible_id"]: row for row in self.compare(group_by=grouping)["rows"]}
            self.assertEqual(set(rows), {2, 3})
            self.assertEqual((rows[3]["a"], rows[3]["target_a"], rows[3]["attainment_a"]), (0, 5, 0))
            self.assertIsNone(rows[3]["rejection_rate_a"])
            self.assertTrue(all(point["value"] == 0 for point in rows[3]["trend_a"]))
            self.assertEqual(sum(row["target_a"] for row in rows.values()), self.compare()["rows"][0]["target_a"])
        people = {row["responsible_id"]: row for row in self.quality()["by_technician"]}
        self.assertEqual((people[3]["total"], people[3]["assigned_target"], people[3]["attainment"]), (0, 5, 0))
        self.assertIsNone(people[3]["approval_rate"])

    def test_zero_production_goal_rows_obey_scope_filters_and_units(self):
        self.goal(person=2, target=5)
        self.goal(person=3, target=7)
        self.goal(person=2, activity="limpieza", target=20)
        self.assertEqual({row["responsible_id"] for row in self.compare(self.tech, group_by="technician_activity")["rows"]}, {2})
        self.assertEqual(self.compare(sap="1003913", group_by="technician_activity")["rows"], [])
        self.assertEqual(self.quality(sap="1003913")["by_technician"], [])
        self.assertEqual(self.compare(self.visitor)["rows"], [])
        self.assertEqual(self.quality(self.visitor)["by_technician"], [])
        rows = self.compare(activity_id="limpieza", group_by="technician_activity")["rows"]
        self.assertEqual([(row["activity_id"], row["unit"], row["a"], row["target_a"]) for row in rows], [("limpieza", "medidores", 0, 20)])


if __name__ == "__main__":
    unittest.main()
