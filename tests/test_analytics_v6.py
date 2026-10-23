"""Analítica V6 con SQLite y datos exclusivamente sintéticos."""
from __future__ import annotations

import io
import json
from pathlib import Path
import sqlite3
import sys
import unittest
import uuid
from unittest import mock
import zipfile

APP_DIR = Path(__file__).resolve().parents[1] / "APLICACION_ACTUAL"
sys.path.insert(0, str(APP_DIR))
import analytics
import documents
import production


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:", isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.addCleanup(self.db.close)
        self.db.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT,name TEXT,role TEXT,access_role TEXT,active INTEGER);
            CREATE TABLE catalog(id INTEGER PRIMARY KEY,kind TEXT,label TEXT,active INTEGER);
            INSERT INTO users VALUES(1,'admin_ficticio','Administración ficticia','supervisor','administrador',1);
            INSERT INTO users VALUES(2,'90001','Persona ficticia Uno','tecnico','tecnico',1);
            INSERT INTO users VALUES(3,'90002','Persona ficticia Dos','tecnico','tecnico',1);
            INSERT INTO users VALUES(4,'visitante_ficticio','Visitante ficticio','tecnico','visitante',1);
        """)
        production.init_schema(self.db)
        self.admin = {"id": 1, "role": "administrador"}
        self.tech = {"id": 2, "role": "tecnico"}
        self.visitor = {"id": 4, "role": "visitante"}

    def event(self, day, activity="revision", *, person=2, quantity=1, unit=None, state="valido", **data):
        definition = production._activity(self.db, activity)
        fields = {"serie": "000" + str(uuid.uuid4()), "sap": "1003913", "voltaje": "240V", "marca": "Marca ficticia", **data}
        cursor = self.db.execute("""INSERT INTO production_events(
            activity_id,activity_version,work_date,responsible_id,recorded_by,quantity,unit,data_json,state,operation_id,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (activity, definition["version"], day, person, 1, quantity,
            unit or definition["unit"], json.dumps(fields), state, uuid.uuid4().hex, production.now(), production.now()))
        return cursor.lastrowid

    def quality(self, user=None, **query):
        return analytics.handle_get(self.db, user or self.admin, "/api/calidad", {"desde": "2026-01-01", "hasta": "2026-01-31", **query})

    def compare(self, user=None, **query):
        return analytics.handle_get(self.db, user or self.admin, "/api/comparativas", {
            "a_desde": "2026-01-01", "a_hasta": "2026-01-31", "b_desde": "2026-02-01", "b_hasta": "2026-02-28", **query})

    def test_quality_rates_exclude_pending_unknown_and_annulled(self):
        self.event("2026-01-02", resultado="Apto")
        self.event("2026-01-03", resultado="Apto")
        self.event("2026-01-03", resultado="No apto", fallo="Display ficticio")
        self.event("2026-01-04", resultado="Pendiente")
        self.event("2026-01-05")
        self.event("2026-01-06", resultado="No apto", state="anulado")
        self.event("2026-01-07", activity="sellado", resultado="Apto")
        result = self.quality(state="all")
        summary = result["summary"]
        self.assertEqual((summary["total"], summary["evaluated"], summary["approved"], summary["rejected"], summary["pending"], summary["without_result"]), (5, 3, 2, 1, 1, 1))
        self.assertAlmostEqual(summary["approval_rate"], 66.666667)
        self.assertAlmostEqual(summary["rejection_rate"], 33.333333)
        self.assertEqual(result["by_failure"], [{"label": "Display ficticio", "value": 1}])
        self.assertEqual(summary["traffic_light"], "rojo")
        self.assertEqual(sum(bucket["total"] for bucket in result["by_period"]), 5)

    def test_calibration_signed_error_absolute_mean_and_exact_tolerance(self):
        # +2% y -2% cancelan su media firmada, pero no la desviación absoluta.
        self.event("2026-01-02", valor_referencia=100, valor_medido=102, tolerancia_pct=2, resultado="Apto", desviacion_pct=999, fuera_tolerancia=True)
        self.event("2026-01-03", person=3, valor_referencia=100, valor_medido=98, tolerancia_pct="1.9", resultado="No apto")
        self.event("2026-01-04", valor_referencia=-100, valor_medido=-98, tolerancia_pct=2, resultado="Apto")
        result = self.quality()
        summary = result["summary"]
        self.assertEqual(summary["calibrations"], 3)
        self.assertEqual(summary["calibrations_outside_tolerance"], 1)
        self.assertAlmostEqual(summary["mean_deviation_pct"], 2 / 3, places=6)
        self.assertEqual(summary["mean_absolute_deviation_pct"], 2)
        people = {person["responsible_id"]: person for person in result["by_technician"]}
        self.assertEqual(people[2]["mean_deviation_pct"], 2)
        self.assertEqual(people[3]["mean_deviation_pct"], -2)

    def test_legacy_invalid_measurements_are_not_fabricated_as_zero(self):
        for reference, measured, tolerance in ((0, 1, 1), (100, "NaN", 1), (100, 101, -1), (None, 1, 1), (100, True, 1), ("1e9999999", 1, 1)):
            self.event("2026-01-02", tipo_inspeccion="Calibración", valor_referencia=reference, valor_medido=measured, tolerancia_pct=tolerance)
        result = self.quality()["summary"]
        self.assertEqual(result["calibrations"], 0)
        self.assertIsNone(result["mean_deviation_pct"])
        self.assertEqual(result["calibration_pending"], 6)
        self.assertIsNone(result["approval_rate"])

    def test_quality_traffic_lights_have_explicit_operational_rules(self):
        self.assertEqual(self.quality()["summary"]["traffic_light"], "amarillo")
        self.event("2026-01-02", resultado="Apto")
        self.assertEqual(self.quality()["summary"]["traffic_light"], "verde")
        self.event("2026-01-03", resultado="Pendiente")
        self.assertEqual(self.quality()["summary"]["traffic_light"], "amarillo")

    def test_roles_apply_to_quality_comparison_and_exports(self):
        self.event("2026-01-02", resultado="Apto")
        self.event("2026-01-02", person=3, resultado="No apto", fallo="Serie 000999 de Persona ficticia Dos")
        self.event("2026-02-02", person=3, resultado="No apto")
        self.assertEqual(self.quality(self.tech)["summary"]["total"], 1)
        self.assertEqual(self.compare(self.tech)["summary"]["records_b"], 0)
        with self.assertRaises(production.ApiError) as forbidden:
            self.quality(self.tech, responsible_id=3)
        self.assertEqual(forbidden.exception.status, 403)
        visitor_quality = self.quality(self.visitor)
        self.assertEqual(visitor_quality["summary"]["total"], 2)
        self.assertEqual(visitor_quality["by_technician"], [])
        serialized = json.dumps(visitor_quality)
        self.assertNotIn("90001", serialized)
        self.assertNotIn("Persona ficticia", serialized)
        self.assertNotIn("000999", serialized)
        for query in ({"responsible_id": 2}, {"meter": "000"}):
            with self.assertRaises(production.ApiError) as error:
                self.compare(self.visitor, **query)
            self.assertEqual(error.exception.status, 403)
        _, rows, _ = analytics.export_rows(self.db, self.visitor, {"desde": "2026-01-01", "hasta": "2026-01-31"}, "calidad")
        self.assertNotIn("Persona ficticia", json.dumps(rows))

    def test_comparison_preserves_units_quantities_and_record_counts(self):
        self.event("2026-01-02", activity="limpieza", quantity=10)
        self.event("2026-02-02", activity="limpieza", quantity=15)
        self.event("2026-01-03", activity="revision", quantity=1)
        self.event("2026-02-03", activity="revision", quantity=1)
        self.event("2026-02-04", activity="revision", quantity=1)
        self.event("2026-02-04", activity="limpieza", quantity=100, state="anulado")
        result = self.compare(state="all")
        rows = {row["activity_id"]: row for row in result["rows"]}
        self.assertEqual((rows["limpieza"]["a"], rows["limpieza"]["b"], rows["limpieza"]["delta"], rows["limpieza"]["percent"]), (10, 15, 5, 50))
        self.assertEqual(rows["limpieza"]["unit"], "medidores")
        self.assertEqual(rows["revision"]["unit"], "revisiones")
        self.assertEqual(result["summary"], {"records_a": 2, "records_b": 3, "delta_records": 1, "percent_records": 50, "percent_state": "comparable"})
        self.assertEqual(result["period_a"]["totals_by_unit"], {"medidores": 10, "revisiones": 1})
        self.assertNotIn("quantity", result["summary"])

    def test_same_activity_changed_unit_is_never_combined(self):
        self.event("2026-01-02", activity="limpieza", quantity=10, unit="medidores")
        self.event("2026-02-02", activity="limpieza", quantity=3, unit="lotes")
        rows = self.compare()["rows"]
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["unit"] for row in rows}, {"medidores", "lotes"})
        self.assertEqual(next(row for row in rows if row["unit"] == "medidores")["percent"], -100)

    def test_zero_denominator_negative_delta_and_empty_ranges(self):
        self.event("2026-02-02", activity="limpieza", quantity=7)
        result = self.compare()
        self.assertIsNone(result["rows"][0]["percent"])
        self.assertEqual(result["rows"][0]["percent_state"], "sin_base")
        reverse = self.compare(a_desde="2026-02-01", a_hasta="2026-02-28", b_desde="2026-01-01", b_hasta="2026-01-31")
        self.assertEqual((reverse["rows"][0]["delta"], reverse["rows"][0]["percent"]), (-7, -100))
        empty = self.compare(a_desde="2025-01-01", a_hasta="2025-01-01", b_desde="2025-02-01", b_hasta="2025-02-01")
        self.assertEqual(empty["summary"]["percent_records"], 0)
        self.assertEqual(empty["summary"]["percent_state"], "sin_cambio")
        self.assertEqual(empty["rows"], [])
        self.assertEqual(empty["series_a"][0]["records"], 0)

    def test_weekly_iso_year_boundary_and_empty_buckets(self):
        self.event("2025-12-29", activity="limpieza", quantity=7)
        self.event("2026-01-01", activity="limpieza", quantity=3)
        result = self.compare(a_desde="2025-12-29", a_hasta="2026-01-18", granularity="semanal")
        series = result["series_a"]
        self.assertEqual([bucket["label"] for bucket in series], ["2026-S01", "2026-S02", "2026-S03"])
        self.assertEqual(series[0]["totals_by_unit"], {"medidores": 10})
        self.assertEqual(series[0]["records"], 2)
        self.assertEqual(series[1]["totals_by_unit"], {"medidores": 0})
        self.assertEqual(series[2]["records"], 0)
        self.assertEqual(series[0]["start"], "2025-12-29")
        self.assertEqual(series[0]["end"], "2026-01-04")

    def test_monthly_leap_year_annual_bounds_and_partial_intervals(self):
        monthly = self.compare(a_desde="2024-02-15", a_hasta="2024-03-03", granularity="mensual")
        self.assertEqual(monthly["series_a"][0]["end"], "2024-02-29")
        self.assertEqual(monthly["series_a"][0]["from"], "2024-02-15")
        self.assertEqual(monthly["period_a"]["days"], 18)
        yearly = self.compare(a_desde="9998-12-31", a_hasta="9999-12-31", b_desde="0001-01-01", b_hasta="0001-01-01", granularity="anual")
        self.assertEqual([item["label"] for item in yearly["series_a"]], ["9998", "9999"])
        self.assertEqual(yearly["series_b"][0]["start"], "0001-01-01")

    def test_filters_are_independent_and_periods_override_global_dates(self):
        self.event("2026-01-02", activity="limpieza", quantity=10, sap="0000123", voltaje="120V", marca="Marca ficticia A")
        self.event("2026-02-02", activity="limpieza", quantity=20, sap="0000123", voltaje="120V", marca="Marca ficticia A")
        self.event("2026-02-02", activity="limpieza", quantity=99, sap="0000456", voltaje="240V")
        result = self.compare(sap="0000123", voltage="120V", brand="Marca ficticia A", activity_id="limpieza", desde="2020-01-01", hasta="2020-01-31")
        self.assertEqual((result["rows"][0]["a"], result["rows"][0]["b"]), (10, 20))
        self.assertEqual(result["applied_filters"]["sap"], "0000123")

    def test_invalid_ranges_granularity_and_bucket_limits_are_explicit(self):
        for query in ({"a_desde": "2026-02-30"}, {"a_hasta": "2025-12-31"}, {"a_desde": ""}, {"granularity": "cada tanto"},
                      {"a_desde": "2000-01-01", "a_hasta": "2026-01-01", "granularity": "diaria"}):
            with self.subTest(query=query), self.assertRaises(production.ApiError):
                self.compare(**query)
        empty_quality = analytics.handle_get(self.db, self.admin, "/api/calidad", {"hasta": "2025-01-01"})
        self.assertEqual(empty_quality["period"]["desde"], "2025-01-01")

    def test_export_contains_all_context_finite_numbers_and_valid_formats(self):
        self.event("2026-01-02", resultado="Apto")
        self.event("2026-02-02", resultado="No apto")
        query = {"a_desde": "2026-01-01", "a_hasta": "2026-01-31", "b_desde": "2026-02-01", "b_hasta": "2026-02-28", "granularity": "mensual", "brand": "Marca ficticia", "sap": "1003913"}
        for report in ("calidad", "comparativas"):
            effective = query if report == "comparativas" else {"desde": "2026-01-01", "hasta": "2026-02-28", "sap": "1003913", "granularity": "mensual"}
            headers, rows, title = analytics.export_rows(self.db, self.admin, effective, report)
            self.assertLessEqual(len(title), 500)
            self.assertIn("2026-01-01", title)
            self.assertTrue(all(len(row) == len(headers) for row in rows))
            self.assertIn("SAP: 1003913", json.dumps(rows, ensure_ascii=False))
            self.assertTrue(documents.write_pdf(headers, rows, title).startswith(b"%PDF"))
            with zipfile.ZipFile(io.BytesIO(documents.write_xlsx(headers, rows, title))) as workbook:
                self.assertIsNone(workbook.testzip())
                self.assertIn(b"1003913", workbook.read("xl/worksheets/sheet1.xml"))
            self.assertTrue(documents.write_csv(headers, rows, title).startswith(b"\xef\xbb\xbf"))
        self.assertIsNone(analytics.handle_get(self.db, self.admin, "/api/noexiste", {}))
        with self.assertRaises(production.ApiError):
            analytics.export_rows(self.db, self.admin, {}, "desconocido")

    def test_export_row_limit_rejects_instead_of_truncating(self):
        self.event("2026-01-02", resultado="Apto")
        with mock.patch.object(analytics, "MAX_REPORT_ROWS", 2):
            with self.assertRaises(production.ApiError) as error:
                analytics.export_rows(self.db, self.admin, {"desde": "2026-01-01", "hasta": "2026-01-02"}, "calidad")
            self.assertEqual(error.exception.status, 413)


if __name__ == "__main__":
    unittest.main()
