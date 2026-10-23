"""Desglose de indicadores y exportaciones, usando SQLite y personas ficticias."""
import json
from pathlib import Path
import sqlite3
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "APLICACION_ACTUAL"))
import analytics
import production as p


class InteractiveDetailsTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:", isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT,name TEXT,role TEXT,access_role TEXT,active INTEGER);
            CREATE TABLE catalog(id INTEGER PRIMARY KEY,kind TEXT,label TEXT,active INTEGER);
            INSERT INTO users VALUES(1,'admin_ficticio','Administración ficticia','supervisor','administrador',1);
            INSERT INTO users VALUES(2,'90001','Técnico ficticio Uno','tecnico','tecnico',1);
            INSERT INTO users VALUES(3,'90002','Técnico ficticio Dos','tecnico','tecnico',1);
        """)
        p.init_schema(self.db)
        self.admin = {"id": 1, "role": "administrador"}
        self.tech = {"id": 2, "role": "tecnico"}
        self.visitor = {"id": 4, "role": "visitante"}
        self.scope = {"desde": "2026-01-01", "hasta": "2026-01-03"}

    def event(self, day="2026-01-02", activity="revision", *, person=2, quantity=1, unit=None, state="valido", **data):
        definition = p._activity(self.db, activity)
        fields = {"serie": "000-FICT-" + uuid.uuid4().hex, "sap": "000045", "marca": "Marca ficticia", "voltaje": "240V", **data}
        return self.db.execute("""INSERT INTO production_events(
            activity_id,activity_version,work_date,responsible_id,recorded_by,quantity,unit,data_json,state,operation_id,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (activity, definition["version"], day, person, 1, quantity,
            unit or definition["unit"], json.dumps(fields), state, uuid.uuid4().hex, p.now(), p.now())).lastrowid

    def detail(self, user=None, **query):
        return p.handle_get(self.db, user or self.admin, "/api/detalle", {**self.scope, **query})

    def records(self, user=None, **query):
        return p.handle_get(self.db, user or self.admin, "/api/eventos", {**self.scope, **query})

    def test_quality_cards_open_exact_matching_revision_sets(self):
        for result in ("Apto", "ÁPTO", "No apto", "Pendiente", "", "Otro resultado histórico"):
            self.event(resultado=result)
        self.event(resultado="Apto", state="anulado")
        self.event(activity="sellado", resultado="Apto")
        q = p._dashboard(self.db, self.admin, self.scope)["summary_quality"]
        for metric, count in (("reviews", q["total"]), ("approved", q["approved"]),
                              ("rejected", q["rejected"]), ("pending", q["pending"]),
                              ("without_result", q["without_result"]), ("evaluated", q["evaluated"]),
                              ("unfinished", q["pending"] + q["without_result"])):
            with self.subTest(metric=metric):
                result = self.detail(metric=metric)
                self.assertEqual(result["total"], count)
                self.assertEqual(len(result["records"]), count)
                self.assertTrue(all(row["activity_id"] == "revision" for row in result["records"]))

    def test_quality_predicates_preserve_an_existing_different_activity_filter(self):
        self.event(resultado="Apto")
        self.event(activity="limpieza", quantity=25)
        for metric in ("reviews", "approved", "evaluated", "unfinished"):
            self.assertEqual(self.detail(activity_id="limpieza", metric=metric)["total"], 0)

    def test_pagination_and_search_use_the_whole_selected_scope(self):
        for index in range(31):
            self.event(serie=f"000-FICT-{index:03d}", resultado="Apto" if index % 2 else "No apto",
                       observaciones="Búsqueda especial" if index in {0, 30} else "otra observación")
        first = self.detail(metric="approved", page_size=5)
        last = self.detail(metric="approved", page_size=5, page=99)
        self.assertEqual((first["total"], first["page_size"], first["pages"], len(first["records"])), (15, 5, 3, 5))
        self.assertEqual((last["page"], len(last["records"])), (3, 5))
        found = self.detail(search="BUSQUEDA ESPECIAL", page_size=1)
        self.assertEqual((found["total"], found["pages"], len(found["records"])), (2, 2, 1))
        self.assertEqual(self.records(search="BUSQUEDA ESPECIAL")["total"], 2)
        self.assertEqual(self.detail(search="000-FICT-030")["records"][0]["data"]["serie"], "000-FICT-030")

    def test_exports_keep_the_same_predicates_and_complete_filtered_scope(self):
        for index in range(8):
            self.event(resultado="Apto", serie=f"000-EXPORT-{index:03d}")
        self.event(resultado="No apto", serie="000-OTHER")
        query = {**self.scope, "metric": "approved", "unit": "revisiones", "page_size": 2,
                 "search": "000-EXPORT"}
        shown = p.handle_get(self.db, self.admin, "/api/detalle", query)
        export = p.export_rows(self.db, self.admin, query)
        self.assertEqual((shown["total"], len(shown["records"]), len(export["rows"])), (8, 2, 8))
        ids = {row[0] for row in export["rows"]}
        complete = self.detail(metric="approved", unit="revisiones", search="000-EXPORT", page_size=200)
        self.assertEqual(ids, {row["id"] for row in complete["records"]})
        self.assertTrue(all(str(row[8]).startswith("000-EXPORT") for row in export["rows"]))
        self.assertIn("Indicador: approved", export["title"])
        self.assertIn("Búsqueda: 000-EXPORT", export["title"])

    def test_export_context_preserves_valid_long_failure_and_search_without_truncation(self):
        failure = "Fallo ficticio detallado " + "x" * 300
        search = "Observación para búsqueda completa " + "y" * 150
        self.event(resultado="No apto", fallo=failure, observaciones=search)
        query = {**self.scope, "failure": failure, "search": search}
        self.assertEqual(self.detail(failure=failure, search=search)["total"], 1)
        result = p.export_rows(self.db, self.admin, query)
        self.assertEqual(len(result["rows"]), 1)
        self.assertIn(f"Fallo informado: {failure}", result["title"])
        self.assertIn(f"Búsqueda: {search}", result["title"])

    def test_detail_excludes_annulled_by_default_and_only_explicitly_includes_them(self):
        valid = self.event(resultado="Apto")
        annulled = self.event(resultado="Apto", state="anulado")
        self.assertEqual([row["id"] for row in self.detail(metric="approved")["records"]], [valid])
        self.assertEqual(self.detail(metric="approved")["total"],
                         p._dashboard(self.db, self.admin, self.scope)["summary_quality"]["approved"])
        self.assertEqual({row["id"] for row in self.detail(metric="approved", state="all")["records"]},
                         {valid, annulled})

    def test_identified_series_have_one_latest_representative_in_the_scope(self):
        self.event("2025-12-31", serie="000A")
        self.event("2026-01-01", serie="000A")
        latest = self.event("2026-01-03", "sellado", serie="000A")
        second = self.event(serie="000B")
        self.event(serie="")
        data = self.detail(metric="identified")
        self.assertEqual(data["total"], 2)
        self.assertEqual({row["id"] for row in data["records"]}, {latest, second})
        self.assertEqual(data["total"], p._dashboard(self.db, self.admin, self.scope)["identified_unique"])
        self.assertIn("representativa", data["count_scope"])

    def test_reentries_are_additional_reviews_in_selected_range_and_exclude_missing_series(self):
        self.event("2025-12-31", serie="000A")
        self.event("2026-01-01", serie="000A")
        second = self.event("2026-01-02", serie="000A")
        third = self.event("2026-01-03", serie="000A")
        self.event("2026-01-02", serie="000B")
        self.event("2026-01-02", serie="")
        self.event("2026-01-02", "sellado", serie="000A")
        result = self.detail(metric="reentries")
        self.assertEqual({row["id"] for row in result["records"]}, {second, third})
        self.assertEqual(result["total"], p._dashboard(self.db, self.admin, self.scope)["reentries"])
        self.assertEqual(self.detail(metric="reentries", search="000A")["total"], 2)

    def test_calibration_details_recalculate_valid_measurements_and_exact_tolerance(self):
        self.event(valor_referencia=100, valor_medido=101, tolerancia_pct=1, resultado="Apto")
        outside = self.event(valor_referencia=100, valor_medido=102, tolerancia_pct=1, resultado="No apto")
        self.event(valor_referencia=0, valor_medido=101, tolerancia_pct=1)
        self.event(activity="sellado", valor_referencia=100, valor_medido=110, tolerancia_pct=1)
        q = analytics._quality(self.db, self.admin, self.scope)["summary"]
        self.assertEqual(self.detail(metric="calibrations")["total"], q["calibrations"])
        found = self.detail(metric="outside_tolerance")
        self.assertEqual(found["total"], q["calibrations_outside_tolerance"])
        self.assertEqual([row["id"] for row in found["records"]], [outside])

    def test_failure_voltage_missing_units_and_historical_activity_name_filters(self):
        self.event(resultado="No apto", fallo="Fallo ficticio", voltaje="")
        self.event(resultado="No apto", condicion="Fallo ficticio", voltaje=None)
        self.event(resultado="Apto", fallo="Sin fallo")
        self.event(activity="sellado", fallo="Fallo ficticio")
        self.assertEqual(self.detail(failure="Fallo ficticio")["total"], 2)
        self.assertEqual(self.detail(voltage_missing="1")["total"], 2)
        self.assertEqual(self.detail(unit="medidores")["total"], 1)
        original = p._activity(self.db, "revision")
        p._save_activity(self.db, self.admin, {**original, "name": "Revisión técnica renombrada"})
        renamed = self.event(resultado="Apto")
        self.assertEqual(self.detail(activity_name="Revisión técnica")["total"], 3)
        self.assertEqual([row["id"] for row in self.detail(activity_name="Revisión técnica renombrada")["records"]], [renamed])
        exported = p.export_rows(self.db, self.admin, {**self.scope, "activity_name": "Revisión técnica renombrada"})
        self.assertEqual(len(exported["rows"]), 1)

    def test_technicians_and_record_lookup_have_backend_ownership_checks(self):
        own = self.event(resultado="Apto")
        other = self.event(person=3, resultado="No apto")
        self.assertEqual(self.detail(self.tech)["total"], 1)
        self.assertEqual(p.handle_get(self.db, self.tech, f"/api/eventos/{own}", {})["record"]["id"], own)
        for action in (lambda: self.detail(self.tech, responsible_id=3),
                       lambda: p.handle_get(self.db, self.tech, f"/api/eventos/{other}", {})):
            with self.assertRaises(p.ApiError) as error:
                action()
            self.assertEqual(error.exception.status, 403)
        self.assertEqual(p.handle_get(self.db, self.admin, f"/api/eventos/{other}", {})["record"]["id"], other)

    def test_visitors_receive_real_aggregates_without_operational_or_personal_details(self):
        event_id = self.event(resultado="No apto", serie="000-PRIVATE-SERIE", fallo="PRIVATE-FAULT")
        self.event(resultado="Apto", person=3)
        result = self.detail(self.visitor, metric="evaluated")
        self.assertEqual((result["total"], result["detail_allowed"], result["records"]), (2, False, []))
        self.assertEqual(result["summary"]["quality"]["evaluated"], 2)
        self.assertTrue(result["breakdown"]["by_day"])
        serialized = json.dumps(result)
        for private in ("000-PRIVATE-SERIE", "PRIVATE-FAULT", "Técnico ficticio", "90001", "90002"):
            self.assertNotIn(private, serialized)
        for action in (lambda: self.detail(self.visitor, search="PRIVATE"),
                       lambda: self.detail(self.visitor, failure="PRIVATE-FAULT"),
                       lambda: self.detail(self.visitor, responsible_id=2),
                       lambda: self.detail(self.visitor, meter="000"),
                       lambda: self.records(self.visitor),
                       lambda: p.export_rows(self.db, self.visitor, self.scope),
                       lambda: p.handle_get(self.db, self.visitor, f"/api/eventos/{event_id}", {})):
            with self.assertRaises(p.ApiError) as error:
                action()
            self.assertEqual(error.exception.status, 403)

    def test_failure_indicator_matches_anonymous_chart_without_false_no_failure_values(self):
        first = self.event(resultado="No apto", fallo="PRIVATE-FAULT-ONE", serie="000-PRIVATE-ONE")
        second = self.event(resultado="No apto", condicion="PRIVATE-FAULT-TWO", serie="000-PRIVATE-TWO")
        for ignored in ("Sin fallo", "Ninguno", "No aplica", "N/A", ""):
            self.event(resultado="Apto", fallo=ignored)
        self.event(resultado="No apto", valor_referencia=100, valor_medido=110, tolerancia_pct=1)
        self.event(activity="sellado", fallo="PRIVATE-OTHER-ACTIVITY")
        self.event(resultado="No apto", fallo="PRIVATE-ANNULLED", state="anulado")
        quality = analytics._quality(self.db, self.visitor, self.scope)
        anonymous = self.detail(self.visitor, metric="failures")
        self.assertEqual(anonymous["total"], sum(row["value"] for row in quality["by_failure"]))
        self.assertEqual((anonymous["total"], anonymous["records"], anonymous["detail_allowed"]), (2, [], False))
        self.assertNotIn("PRIVATE", json.dumps(anonymous))
        self.assertNotIn("90001", json.dumps(anonymous))
        manager = self.detail(metric="failures")
        self.assertEqual({row["id"] for row in manager["records"]}, {first, second})
        exported = p.export_rows(self.db, self.admin, {**self.scope, "metric": "failures"})
        self.assertEqual({row[0] for row in exported["rows"]}, {first, second})

    def test_invalid_detail_filters_fail_explicitly_and_do_not_change_data(self):
        self.event(resultado="Apto")
        for query in ({"metric": "made_up"}, {"metric": True}, {"unit": True}, {"page_size": 201},
                      {"page": 0}, {"search": "a" * 201}, {"voltage_missing": "yes"}, {"voltage_missing": True}):
            with self.subTest(query=query), self.assertRaises(p.ApiError):
                self.detail(**query)
        self.assertEqual(self.records()["total"], 1)

    def test_collaborator_graph_exposes_stable_ids_without_parsing_labels(self):
        self.event(resultado="Apto")
        self.event(person=3, resultado="No apto")
        result = p._dashboard(self.db, self.admin, self.scope)
        self.assertEqual({row["responsible_id"] for row in result["by_collaborator"]}, {2, 3})
        for row in result["by_collaborator"]:
            self.assertEqual(self.detail(responsible_id=row["responsible_id"])["total"], row["value"])

    def test_partial_detail_filters_never_receive_a_whole_period_goal(self):
        self.event(resultado="No apto", fallo="Fallo ficticio", voltaje="", observaciones="Búsqueda especial")
        self.db.execute("""INSERT INTO production_goals(responsible_id,activity_id,start_date,end_date,target,unit,created_by,created_at)
            VALUES(2,'revision','2026-01-01','2026-01-03',10,'revisiones',1,?)""", (p.now(),))
        queries = [{"search": "Búsqueda especial"}, {"failure": "Fallo ficticio"},
                   {"metric": "rejected"}, {"voltage_missing": "1"}, {"activity_name": "Revisión técnica"}]
        for extra in queries:
            query = {**self.scope, **extra}
            with self.subTest(extra=extra):
                result = analytics._quality(self.db, self.admin, query)
                self.assertEqual(result["by_technician"][0]["target_scope"], "filtered_subset")
                self.assertIsNone(result["by_technician"][0]["assigned_target"])
                self.assertTrue(all(result["applied_filters"][key] == value for key, value in extra.items()))
                headers, rows, _ = analytics.export_rows(self.db, self.admin, query, "calidad")
                self.assertTrue(all(len(row) == len(headers) for row in rows))
                self.assertTrue(all(str(value) in json.dumps(rows, ensure_ascii=False) for value in extra.values()))
        self.assertEqual(analytics._quality(self.db, self.admin, self.scope)["by_technician"][0]["assigned_target"], 10)

    def test_unit_filter_keeps_compatible_zero_production_goals_without_injecting_other_units(self):
        for activity, unit, target in (("revision", "revisiones", 10), ("limpieza", "medidores", 20)):
            self.db.execute("""INSERT INTO production_goals(responsible_id,activity_id,start_date,end_date,target,unit,created_by,created_at)
                VALUES(2,?,'2026-01-01','2026-01-03',?,?,1,?)""", (activity, target, unit, p.now()))
        query = {"a_desde": "2026-01-01", "a_hasta": "2026-01-03", "b_desde": "2026-02-01",
                 "b_hasta": "2026-02-03", "group_by": "technician_activity", "unit": "revisiones"}
        result = analytics._comparison(self.db, self.admin, query)
        self.assertEqual([(row["activity_id"], row["unit"], row["a"], row["target_a"])
                          for row in result["rows"]], [("revision", "revisiones", 0, 10)])
        self.assertEqual(result["applied_filters"]["unit"], "revisiones")
        query.update(search="No hay registros")
        self.assertEqual(analytics._comparison(self.db, self.admin, query)["rows"], [])


if __name__ == "__main__":
    unittest.main()
