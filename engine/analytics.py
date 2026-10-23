"""Analítica operativa V6: calidad y comparativas sin alterar el histórico.

Los filtros de permisos pertenecen a production; aquí se reutilizan también para
las exportaciones. Las cantidades se agrupan por actividad Y unidad. Los
porcentajes nunca convierten una base cero en un crecimiento ficticio.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, DecimalException
import math

import production


MAX_BUCKETS = 1000
MAX_REPORT_ROWS = 10_000
GRANULARITIES = {"diaria", "semanal", "mensual", "anual"}
FILTER_LABELS = {
    "activity_id": "Actividad", "responsible_id": "Responsable", "sap": "SAP",
    "voltage": "Voltaje", "brand": "Marca", "model": "Modelo", "condition": "Condición", "meter": "Serie",
}


def _granularity(query):
    value = str(query.get("granularity") or "diaria").strip().lower()
    if value not in GRANULARITIES:
        raise production.ApiError("Selecciona granularidad diaria, semanal, mensual o anual.")
    return value


def _day(value, label):
    return date.fromisoformat(production._date(value, label))


def _range(start, end, start_label, end_label):
    first, last = _day(start, start_label), _day(end, end_label)
    if first > last:
        raise production.ApiError(f"{start_label} no puede ser posterior a {end_label}.")
    return first, last


def _bucket(day, granularity):
    """Límites calendarios; las semanas usan año y semana ISO, de lunes a domingo."""
    if granularity == "diaria":
        return day.isoformat(), day, day
    if granularity == "semanal":
        iso_year, week, _ = day.isocalendar()
        start = date.fromordinal(max(1, day.toordinal() - day.weekday()))
        end = date.fromordinal(min(date.max.toordinal(), start.toordinal() + 6))
        return f"{iso_year:04d}-S{week:02d}", start, end
    if granularity == "mensual":
        start = day.replace(day=1)
        if day.year == 9999 and day.month == 12:
            end = date.max
        else:
            following = date(day.year + (day.month == 12), day.month % 12 + 1, 1)
            end = following - timedelta(days=1)
        return f"{day.year:04d}-{day.month:02d}", start, end
    return f"{day.year:04d}", date(day.year, 1, 1), date(day.year, 12, 31)


def _buckets(first, last, granularity):
    buckets, cursor = [], first
    while cursor <= last:
        label, start, end = _bucket(cursor, granularity)
        if len(buckets) >= MAX_BUCKETS:
            raise production.ApiError(
                f"El rango supera {MAX_BUCKETS} intervalos; reduce las fechas o elige una granularidad mayor."
            )
        buckets.append({"label": label, "start": start.isoformat(), "end": end.isoformat(),
                        "from": max(start, first).isoformat(), "to": min(end, last).isoformat()})
        if end >= last or end == date.max:
            break
        cursor = end + timedelta(days=1)
    return buckets


def _events(db, user, query, *, start=None, end=None, quality=False):
    effective = dict(query)
    # Anular una operación la excluye de los indicadores, incluso si la pantalla
    # de detalle estaba mostrando state=all antes de abrir este informe.
    effective["state"] = "valido"
    if quality:
        effective["activity_id"] = "revision"
    if start is not None:
        effective["desde"] = start.isoformat()
    if end is not None:
        effective["hasta"] = end.isoformat()
    return production._events(db, user, effective, allow_visitor=True)


def _percent(numerator, denominator):
    return round(float(Decimal(numerator) * 100 / Decimal(denominator)), 6) if denominator else None


def _change(a, b):
    delta = b - a
    if a:
        return delta, _percent(delta, a), "comparable"
    return delta, None if b else 0, "sin_base" if b else "sin_cambio"


def _decimal(value):
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        number = Decimal(str(value))
        return number if number.is_finite() else None
    except (DecimalException, ValueError, TypeError):
        return None


def _calibration(data):
    """Recalcular desde operandos permite auditar y no confiar en un derivado antiguo."""
    reference = _decimal(data.get("valor_referencia"))
    measured = _decimal(data.get("valor_medido"))
    tolerance = _decimal(data.get("tolerancia_pct"))
    if reference in (None, 0) or measured is None or tolerance is None or tolerance < 0:
        return None
    try:
        error = (measured - reference) * 100 / abs(reference)
        if not error.is_finite() or not math.isfinite(float(error)):
            return None
        return error, abs(error) > tolerance
    except (DecimalException, OverflowError, ValueError):
        return None


def _average(values, absolute=False):
    if not values:
        return None
    value = sum((abs(x) if absolute else x for x in values), Decimal(0)) / len(values)
    result = float(value)
    return round(result, 6) if math.isfinite(result) else None


def _quality_summary(events):
    outcomes = Counter(production._fold(event["data"].get("resultado", "")) for event in events)
    approved, rejected = outcomes["apto"], outcomes["no apto"]
    pending = outcomes["pendiente"]
    evaluated = approved + rejected
    calibrations = [value for event in events if (value := _calibration(event["data"])) is not None]
    deviations = [value[0] for value in calibrations]
    outside = sum(value[1] for value in calibrations)
    calibration_pending = sum(
        production._fold(event["data"].get("tipo_inspeccion", "")) == "calibracion"
        and _calibration(event["data"]) is None for event in events
    )
    without = len(events) - evaluated - pending
    traffic = "rojo" if rejected or outside else (
        "amarillo" if pending or without or not evaluated or calibration_pending else "verde"
    )
    return {"total": len(events), "evaluated": evaluated, "approved": approved,
            "rejected": rejected, "pending": pending, "without_result": without,
            "approval_rate": _percent(approved, evaluated), "rejection_rate": _percent(rejected, evaluated),
            "calibrations": len(calibrations), "calibrations_outside_tolerance": outside,
            "calibration_pending": calibration_pending,
            "mean_deviation_pct": _average(deviations),
            "mean_absolute_deviation_pct": _average(deviations, absolute=True),
            "traffic_light": traffic}


def _quality(db, user, query):
    granularity = _granularity(query)
    events = _events(db, user, query, quality=True)
    days = [date.fromisoformat(event["work_date"]) for event in events]
    today = datetime.now(timezone(timedelta(hours=-4))).date()
    requested_last = _day(query["hasta"], "Hasta") if query.get("hasta") else None
    first = _day(query["desde"], "Desde") if query.get("desde") else min(days, default=requested_last or today)
    last = requested_last or max(days, default=max(first, today))
    if first > last:
        raise production.ApiError("La fecha Desde no puede ser posterior a Hasta.")
    buckets = _buckets(first, last, granularity)
    people, grouped = defaultdict(list), defaultdict(list)
    failures, inspection_types = Counter(), Counter()
    for event in events:
        people[event["responsible_id"]].append(event)
        grouped[_bucket(date.fromisoformat(event["work_date"]), granularity)[0]].append(event)
        data = event["data"]
        failure = str(data.get("fallo") or "").strip()
        if not failure and production._fold(data.get("resultado", "")) == "no apto":
            failure = str(data.get("condicion") or "").strip()
        if failure and production._fold(failure) not in {"ninguno", "ninguna", "sin fallo", "sin fallos", "no", "no aplica", "n/a"}:
            # El fallo es texto libre: puede contener una serie o una persona.
            # El visitante recibe su cantidad agregada, no ese texto operativo.
            failures["Revisiones con fallo informado" if user["role"] == "visitante" else failure] += 1
        inspection_types[str(data.get("tipo_inspeccion") or "Sin tipo informado")] += 1
    technicians = []
    if user["role"] != "visitante":
        for person_events in people.values():
            person = person_events[0]
            technicians.append({"responsible_id": person["responsible_id"], "name": person["responsible_name"],
                                "username": person["responsible_username"], **_quality_summary(person_events)})
        technicians.sort(key=lambda item: (production._fold(item["name"]), item["responsible_id"]))
    effective = {key: query[key] for key in FILTER_LABELS if query.get(key)}
    effective["activity_id"] = "revision"
    return {"summary": _quality_summary(events), "by_technician": technicians,
            "by_failure": [{"label": label, "value": count} for label, count in sorted(failures.items(), key=lambda item: (-item[1], item[0]))],
            "by_inspection_type": [{"label": label, "value": count} for label, count in sorted(inspection_types.items())],
            "by_period": [{**bucket, **_quality_summary(grouped[bucket["label"]])} for bucket in buckets],
            "period": {"desde": first.isoformat(), "hasta": last.isoformat(), "granularity": granularity},
            "applied_filters": effective,
            "rates_denominator": "evaluated = approved + rejected",
            "traffic_rule": "Rojo: rechazos o calibraciones fuera de tolerancia. Amarillo: pendientes, ausencia de resultado, calibraciones sin medición válida o sin evaluados. Verde: evaluados aprobados sin pendientes.",
            "deviation_formula": "(valor_medido - valor_referencia) / abs(valor_referencia) * 100"}


def _series(events, buckets, granularity):
    counts, units = Counter(), defaultdict(Counter)
    for event in events:
        label = _bucket(date.fromisoformat(event["work_date"]), granularity)[0]
        counts[label] += 1
        units[label][event["unit"]] += event["quantity"]
    all_units = sorted({event["unit"] for event in events})
    return [{**bucket, "records": counts[bucket["label"]],
             "totals_by_unit": {unit: units[bucket["label"]][unit] for unit in all_units}}
            for bucket in buckets]


def _comparison(db, user, query):
    granularity = _granularity(query)
    first_a, last_a = _range(query.get("a_desde"), query.get("a_hasta"), "Inicio del período A", "Fin del período A")
    first_b, last_b = _range(query.get("b_desde"), query.get("b_hasta"), "Inicio del período B", "Fin del período B")
    buckets_a, buckets_b = _buckets(first_a, last_a, granularity), _buckets(first_b, last_b, granularity)
    events_a = _events(db, user, query, start=first_a, end=last_a)
    events_b = _events(db, user, query, start=first_b, end=last_b)
    counts_a, counts_b, quantities_a, quantities_b = Counter(), Counter(), Counter(), Counter()
    names = {}
    for events, counts, quantities in ((events_a, counts_a, quantities_a), (events_b, counts_b, quantities_b)):
        # La denominación vigente en B se muestra si una actividad fue renombrada.
        # El ID y la unidad, no la etiqueta editable, fijan la comparación.
        for event in sorted(events, key=lambda item: (item["work_date"], item["id"])):
            key = (event["activity_id"], event["unit"])
            counts[key] += 1
            quantities[key] += event["quantity"]
            names[key] = event["activity_name"]
    rows = []
    for key in sorted(set(counts_a) | set(counts_b), key=lambda key: (production._fold(names[key]), key)):
        delta, percent, state = _change(quantities_a[key], quantities_b[key])
        delta_records, percent_records, _ = _change(counts_a[key], counts_b[key])
        rows.append({"activity_id": key[0], "activity_name": names[key], "unit": key[1],
                     "a": quantities_a[key], "b": quantities_b[key], "delta": delta,
                     "percent": percent, "percent_state": state, "records_a": counts_a[key],
                     "records_b": counts_b[key], "delta_records": delta_records, "percent_records": percent_records})
    delta_records, percent_records, percent_state = _change(len(events_a), len(events_b))

    def period(first, last, events):
        totals = Counter()
        for event in events:
            totals[event["unit"]] += event["quantity"]
        return {"from": first.isoformat(), "to": last.isoformat(), "days": (last - first).days + 1,
                "event_count": len(events), "totals_by_unit": dict(sorted(totals.items()))}

    return {"period_a": period(first_a, last_a, events_a), "period_b": period(first_b, last_b, events_b),
            "granularity": granularity, "rows": rows,
            "summary": {"records_a": len(events_a), "records_b": len(events_b),
                        "delta_records": delta_records, "percent_records": percent_records, "percent_state": percent_state},
            "series_a": _series(events_a, buckets_a, granularity), "series_b": _series(events_b, buckets_b, granularity),
            "applied_filters": {key: query[key] for key in FILTER_LABELS if query.get(key)},
            "variation_formula": "(B - A) / A * 100; A = 0 y B > 0: sin base",
            "comparison_scope": "Totales brutos de los rangos elegidos; no se normalizan por duración. Cantidades separadas por actividad y unidad."}


def handle_get(db, user, path, query):
    if path == "/api/calidad":
        return _quality(db, user, query)
    if path == "/api/comparativas":
        return _comparison(db, user, query)
    return None


def _metadata_rows(filters, columns):
    rows = []
    for key, value in filters.items():
        rows.append(["Contexto", f"{FILTER_LABELS.get(key, key)}: {value}", *([""] * (columns - 2))])
    rows.append(["Contexto", "Solo registros válidos. Cantidades separadas por actividad y unidad.", *([""] * (columns - 2))])
    return rows


def _report_limit(rows):
    if len(rows) > MAX_REPORT_ROWS:
        raise production.ApiError(f"El reporte supera {MAX_REPORT_ROWS} filas; reduce el período o los filtros.", 413)
    return rows


def export_rows(db, user, query, report):
    """Tabla completa para documents.write_*; las filas Contexto retienen los filtros."""
    if report == "calidad":
        result = _quality(db, user, query)
        period = result["period"]
        title = (f"Calidad {period['desde']} a {period['hasta']} | {period['granularity']} | "
                 "Tasas sobre evaluados = aptos + no aptos")
        headers = ["Sección", "Dimensión", "Revisiones", "Evaluados", "Aptos", "No aptos", "Pendientes", "Sin resultado",
                   "Aprobación %", "Rechazo %", "Calibraciones", "Fuera de tolerancia", "Desviación media %",
                   "Desviación absoluta media %", "Semáforo"]
        rows = _metadata_rows(result["applied_filters"], len(headers))
        rows.append(["Contexto", result["deviation_formula"], *([""] * (len(headers) - 2))])
        metrics = ("total", "evaluated", "approved", "rejected", "pending", "without_result", "approval_rate", "rejection_rate",
                   "calibrations", "calibrations_outside_tolerance", "mean_deviation_pct", "mean_absolute_deviation_pct", "traffic_light")
        rows.append(["Resumen", "Laboratorio / alcance autorizado", *(result["summary"][key] for key in metrics)])
        for person in result["by_technician"]:
            rows.append(["Colaborador", f"{person['name']} ({person['username']})", *(person[key] for key in metrics)])
        for bucket in result["by_period"]:
            rows.append(["Período", f"{bucket['label']} ({bucket['from']} a {bucket['to']})", *(bucket[key] for key in metrics)])
        for failure in result["by_failure"]:
            rows.append(["Fallo", failure["label"], failure["value"], *([""] * (len(headers) - 3))])
        return headers, _report_limit(rows), title
    if report == "comparativas":
        result = _comparison(db, user, query)
        pa, pb = result["period_a"], result["period_b"]
        title = (f"Comparativa A: {pa['from']} a {pa['to']} | B: {pb['from']} a {pb['to']} | "
                 f"{result['granularity']} | Variación (B-A)/A; A=0 sin base")
        headers = ["Sección", "Actividad / período", "Unidad", "Cantidad A", "Cantidad B", "Diferencia B-A", "Variación %",
                   "Base del porcentaje", "Registros A", "Registros B", "Diferencia registros", "Variación registros %"]
        rows = _metadata_rows(result["applied_filters"], len(headers))
        rows.append(["Contexto", result["comparison_scope"], *([""] * (len(headers) - 2))])
        summary = result["summary"]
        rows.append(["Resumen", "Registros en el alcance autorizado", "registros", "", "", "", "", summary["percent_state"],
                     summary["records_a"], summary["records_b"], summary["delta_records"], summary["percent_records"]])
        for row in result["rows"]:
            rows.append(["Actividad", row["activity_name"], row["unit"], row["a"], row["b"], row["delta"], row["percent"],
                         row["percent_state"], row["records_a"], row["records_b"], row["delta_records"], row["percent_records"]])
        for letter, series in (("A", result["series_a"]), ("B", result["series_b"])):
            for bucket in series:
                # Los registros aparecen una sola vez por intervalo, separados de
                # las cantidades por unidad para impedir una suma duplicada.
                rows.append([f"Serie {letter}", f"{bucket['label']} ({bucket['from']} a {bucket['to']})", "registros", "", "", "", "", "",
                             bucket["records"] if letter == "A" else "", bucket["records"] if letter == "B" else "", "", ""])
                for unit, quantity in bucket["totals_by_unit"].items():
                    rows.append([f"Cantidad {letter}", bucket["label"], unit, quantity if letter == "A" else "",
                                 quantity if letter == "B" else "", "", "", "", "", "", "", ""])
        return headers, _report_limit(rows), title
    raise production.ApiError("Selecciona un reporte de calidad o comparativas.")
