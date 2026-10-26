"""Analítica operativa V6: calidad y comparativas sin alterar el histórico.

Los filtros de permisos pertenecen a production; aquí se reutilizan también para
las exportaciones. Cada agrupación conserva las unidades del registro. Los
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
GROUP_LABELS = {"activity": "Por actividad y unidad", "technician": "Por técnico y unidad",
                "technician_activity": "Por técnico, actividad y unidad"}
TARGET_SCOPES = {
    "exact_period": "Meta registrada para el período completo, la actividad, la unidad y los responsables del alcance.",
    "no_exact_goal": "Sin meta registrada con las fechas exactas del período.",
    "filtered_subset": "La meta no distingue el filtro técnico aplicado; no se atribuye a este subconjunto.",
    "ambiguous_goals": "Hay metas superpuestas para el mismo responsable, actividad y unidad; no se suman.",
    "unassigned_contributors": "El alcance incluye responsables sin una meta exacta para el período.",
    "multiple_activities": "El grupo reúne actividades distintas; no tiene una meta única comparable.",
    "multiple_units": "El grupo contiene unidades distintas; no se combinan en una meta.",
    "restricted_role": "El perfil visitante no consulta metas individuales.",
}
FILTER_LABELS = {
    "activity_id": "Actividad", "responsible_id": "Responsable", "sap": "SAP",
    "voltage": "Voltaje", "brand": "Marca", "model": "Modelo", "condition": "Condición", "meter": "Serie",
    "group_by": "Agrupación",
    "activity_name": "Nombre histórico de actividad", "unit": "Unidad", "metric": "Indicador",
    "search": "Búsqueda", "failure": "Fallo informado", "voltage_missing": "Sin voltaje informado",
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
    approved, rejected = outcomes["apto"]+outcomes["reutilizable"], outcomes["no apto"]+outcomes["no reutilizable"]
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


def _goal_candidates(db, user, query):
    """Metas autorizadas, sin tratar un solapamiento de fechas como un objetivo del rango."""
    if user["role"] == "visitante":
        return []
    clauses, values = ["active=1"], []
    responsible = user["id"] if user["role"] == "tecnico" else query.get("responsible_id")
    if responsible:
        clauses.append("responsible_id=?")
        values.append(responsible)
    return [dict(row) for row in db.execute(
        "SELECT * FROM production_goals WHERE " + " AND ".join(clauses), values)]


def _partial_goal_scope(query):
    """Los filtros de detalle no dividen una meta de período completo."""
    return (any(query.get(key) for key in ("sap", "voltage", "brand", "model", "condition", "meter",
                                           "activity_name", "search", "failure"))
            or str(query.get("voltage_missing", "")) == "1"
            or production._detail_metric(query) != "events")


def _target(goals, user, query, first, last, activity_id, unit, responsible_id, events):
    """Una meta parcial, filtrada o superpuesta nunca se prorratea ni se duplica."""
    if user["role"] == "visitante":
        return None, "restricted_role"
    if not activity_id:
        return None, "multiple_activities"
    if not unit:
        return None, "multiple_units"
    if _partial_goal_scope(query):
        return None, "filtered_subset"
    start, end = first.isoformat(), last.isoformat()
    relevant = [goal for goal in goals if goal["activity_id"] == activity_id and goal["unit"] == unit
                and (responsible_id is None or goal["responsible_id"] == responsible_id)
                and goal["start_date"] <= end and goal["end_date"] >= start]
    exact = [goal for goal in relevant if goal["start_date"] == start and goal["end_date"] == end]
    if not exact:
        return None, "no_exact_goal"
    contributors = {event["responsible_id"] for event in events}
    assigned = {goal["responsible_id"] for goal in exact}
    if contributors - assigned:
        return None, "unassigned_contributors"
    overlaps = Counter(goal["responsible_id"] for goal in relevant)
    if any(overlaps[person] != 1 for person in assigned):
        return None, "ambiguous_goals"
    return sum(goal["target"] for goal in exact), "exact_period"


def _goal_dimensions(db, goals, query, periods, activity_id=None):
    """Incluir metas exactas sin producción, sin fabricar eventos ni sus tasas."""
    if _partial_goal_scope(query):
        return []
    filtered_unit = production._text(query["unit"], "Unidad", 120, True) if query.get("unit") else None
    ranges = {(first.isoformat(), last.isoformat()) for first, last in periods}
    result = {}
    for goal in goals:
        if filtered_unit is not None and goal["unit"] != filtered_unit:
            continue
        if (goal["start_date"], goal["end_date"]) not in ranges:
            continue
        if goal["activity_id"] != (activity_id or query.get("activity_id") or goal["activity_id"]):
            continue
        key = (goal["responsible_id"], goal["activity_id"], goal["unit"])
        if key in result:
            continue
        row = db.execute("""SELECT u.id AS responsible_id,u.name AS responsible_name,
            u.username AS responsible_username,a.id AS activity_id,a.name AS activity_name
            FROM users u JOIN activities a ON a.id=? WHERE u.id=?""",
            (goal["activity_id"], goal["responsible_id"])).fetchone()
        if row:
            result[key] = {**dict(row), "unit": goal["unit"]}
    return list(result.values())


def _trend(events, buckets, granularity, *, records=False):
    counts, quantities = Counter(), Counter()
    for event in events:
        label = _bucket(date.fromisoformat(event["work_date"]), granularity)[0]
        counts[label] += 1
        quantities[label] += event["quantity"]
    return [{"label": bucket["label"], "from": bucket["from"], "to": bucket["to"],
             "value": counts[bucket["label"]] if records else quantities[bucket["label"]],
             "records": counts[bucket["label"]]} for bucket in buckets]


def _failure_label(data):
    failure = str(data.get("fallo") or "").strip()
    if not failure and production._fold(data.get("resultado", "")) == "no apto":
        failure = str(data.get("condicion") or "").strip()
    return "" if production._fold(failure) in {"ninguno", "ninguna", "sin fallo", "sin fallos", "no", "no aplica", "n/a"} else failure


def _quality(db, user, query, *, all_failures=False):
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
    failures, inspection_types, detailed = Counter(), Counter(), []
    for event in events:
        people[event["responsible_id"]].append(event)
        grouped[_bucket(date.fromisoformat(event["work_date"]), granularity)[0]].append(event)
        data = event["data"]
        failure = _failure_label(data)
        if failure:
            # El fallo es texto libre: puede contener una serie o una persona.
            # El visitante recibe su cantidad agregada, no ese texto operativo.
            failures["Revisiones con fallo informado" if user["role"] == "visitante" else failure] += 1
        calibration = _calibration(data)
        outside = calibration[1] if calibration is not None else None
        if user["role"] != "visitante" and (failure or outside or production._fold(data.get("resultado", "")) == "no apto"):
            detailed.append({"event_id": event["id"], "serial": str(data.get("serie") or ""),
                             "failure": failure, "work_date": event["work_date"],
                             "responsible_id": event["responsible_id"], "responsible_name": event["responsible_name"],
                             "responsible_username": event["responsible_username"],
                             "result": str(data.get("resultado") or "Sin resultado"),
                             "inspection_type": str(data.get("tipo_inspeccion") or "Sin tipo informado"),
                             "outside_tolerance": outside})
        inspection_type = str(data.get("tipo_inspeccion") or "Sin tipo informado")
        if user["role"] == "visitante":
            # Las versiones antiguas pueden contener texto libre fuera del select.
            inspection_type = {"inspeccion": "Inspección", "calibracion": "Calibración",
                               "sin tipo informado": "Sin tipo informado"}.get(
                                   production._fold(inspection_type), "Otro tipo informado")
        inspection_types[inspection_type] += 1
    technicians = []
    goals = _goal_candidates(db, user, query)
    zero_people, goal_units = {}, defaultdict(set)
    for person in _goal_dimensions(db, goals, query, [(first, last)], "revision"):
        zero_people[person["responsible_id"]] = person
        goal_units[person["responsible_id"]].add(person["unit"])
        people.setdefault(person["responsible_id"], [])
    if user["role"] != "visitante":
        for person_id, person_events in people.items():
            person = person_events[0] if person_events else zero_people[person_id]
            quantities = Counter()
            for event in person_events:
                quantities[event["unit"]] += event["quantity"]
            if not person_events:
                quantities.update({unit: 0 for unit in goal_units[person_id]})
            unit = next(iter(quantities)) if len(quantities) == 1 else None
            target, target_scope = _target(goals, user, query, first, last, "revision", unit,
                                          person["responsible_id"], person_events)
            produced = quantities[unit] if unit else None
            technicians.append({"responsible_id": person["responsible_id"], "name": person["responsible_name"],
                                "username": person["responsible_username"], **_quality_summary(person_events),
                                "quantities_by_unit": dict(sorted(quantities.items())), "unit": unit,
                                "produced_quantity": produced, "assigned_target": target,
                                "attainment": _percent(produced, target) if target else None,
                                "target_scope": target_scope,
                                "trend": _trend(person_events, buckets, granularity, records=True)})
        technicians.sort(key=lambda item: (production._fold(item["name"]), item["responsible_id"]))
    failure_offset = production._integer(query.get("failure_offset", 0), "Inicio del detalle de fallos", 0, 1_000_000_000)
    failure_limit = production._integer(query.get("failure_limit", 200), "Tamaño del detalle de fallos", 1, 1000)
    detailed.sort(key=lambda item: (item["work_date"], item["event_id"]), reverse=True)
    selected_failures = detailed if all_failures else detailed[failure_offset:failure_offset + failure_limit]
    effective = {key: query[key] for key in FILTER_LABELS if query.get(key)}
    effective["activity_id"] = "revision"
    return {"summary": _quality_summary(events), "by_technician": technicians,
            "by_failure": [{"label": label, "value": count} for label, count in sorted(failures.items(), key=lambda item: (-item[1], item[0]))],
            "by_inspection_type": [{"label": label, "value": count} for label, count in sorted(inspection_types.items())],
            "by_period": [{**bucket, **_quality_summary(grouped[bucket["label"]])} for bucket in buckets],
            "detailed_failures": selected_failures, "failure_count": len(detailed),
            "failure_offset": 0 if all_failures else failure_offset,
            "failure_limit": len(detailed) if all_failures else failure_limit,
            "failure_has_more": False if all_failures else failure_offset + len(selected_failures) < len(detailed),
            "period": {"desde": first.isoformat(), "hasta": last.isoformat(), "granularity": granularity},
            "applied_filters": effective,
            "target_scope_labels": TARGET_SCOPES, "trend_unit": "registros de revisión",
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
    group_by = str(query.get("group_by") or "activity").strip().lower()
    if group_by not in GROUP_LABELS:
        raise production.ApiError("Selecciona agrupación por actividad, técnico o técnico y actividad.")
    if user["role"] == "visitante" and group_by != "activity":
        raise production.ApiError("El visitante consulta estadísticas agregadas, sin agrupación personal.", 403)
    first_a, last_a = _range(query.get("a_desde"), query.get("a_hasta"), "Inicio del período A", "Fin del período A")
    first_b, last_b = _range(query.get("b_desde"), query.get("b_hasta"), "Inicio del período B", "Fin del período B")
    buckets_a, buckets_b = _buckets(first_a, last_a, granularity), _buckets(first_b, last_b, granularity)
    events_a = _events(db, user, query, start=first_a, end=last_a)
    events_b = _events(db, user, query, start=first_b, end=last_b)
    grouped_a, grouped_b, names = defaultdict(list), defaultdict(list), {}
    for events, grouped in ((events_a, grouped_a), (events_b, grouped_b)):
        # La denominación vigente en B se muestra si una actividad fue renombrada.
        # El ID y la unidad, no la etiqueta editable, fijan la comparación.
        for event in sorted(events, key=lambda item: (item["work_date"], item["id"])):
            key = ((event["responsible_id"], event["unit"]) if group_by == "technician" else
                   (event["responsible_id"], event["activity_id"], event["unit"]) if group_by == "technician_activity" else
                   (event["activity_id"], event["unit"]))
            grouped[key].append(event)
            names[key] = event
    rows = []
    goals = _goal_candidates(db, user, query)
    goal_activities = defaultdict(set)
    for person in _goal_dimensions(db, goals, query, [(first_a, last_a), (first_b, last_b)]):
        key = ((person["responsible_id"], person["unit"]) if group_by == "technician" else
               (person["responsible_id"], person["activity_id"], person["unit"]) if group_by == "technician_activity" else
               (person["activity_id"], person["unit"]))
        names.setdefault(key, person)
        goal_activities[key].add(person["activity_id"])
    def order(key):
        event = names[key]
        return (production._fold(event["responsible_name"]) if group_by != "activity" else "",
                production._fold(event["activity_name"]) if group_by != "technician" else "", key)
    for key in sorted(names, key=order):
        row_a, row_b, person = grouped_a[key], grouped_b[key], names[key]
        quantity_a, quantity_b = sum(event["quantity"] for event in row_a), sum(event["quantity"] for event in row_b)
        delta, percent, state = _change(quantity_a, quantity_b)
        delta_records, percent_records, _ = _change(len(row_a), len(row_b))
        activity_ids = sorted({event["activity_id"] for event in row_a + row_b} | goal_activities[key])
        activity_id = activity_ids[0] if len(activity_ids) == 1 else None
        responsible_id = person["responsible_id"] if group_by != "activity" else None
        unit = person["unit"]
        quality_a = _quality_summary([event for event in row_a if event["activity_id"] == "revision"])
        quality_b = _quality_summary([event for event in row_b if event["activity_id"] == "revision"])
        target_a, scope_a = _target(goals, user, query, first_a, last_a, activity_id, unit, responsible_id, row_a)
        target_b, scope_b = _target(goals, user, query, first_b, last_b, activity_id, unit, responsible_id, row_b)
        rate_a, rate_b = quality_a["rejection_rate"], quality_b["rejection_rate"]
        rows.append({"activity_id": activity_id,
                     "activity_name": person["activity_name"] if activity_id else "Todas las actividades del grupo",
                     "activity_ids": activity_ids, "unit": unit,
                     "responsible_id": responsible_id,
                     "responsible_name": person["responsible_name"] if responsible_id is not None else None,
                     "responsible_username": person["responsible_username"] if responsible_id is not None else None,
                     "a": quantity_a, "b": quantity_b, "delta": delta,
                     "percent": percent, "percent_state": state, "records_a": len(row_a),
                     "records_b": len(row_b), "delta_records": delta_records, "percent_records": percent_records,
                     **{f"{metric}_{letter}": quality[metric] for letter, quality in (("a", quality_a), ("b", quality_b))
                        for metric in ("approved", "rejected", "evaluated", "approval_rate", "rejection_rate")},
                     "rejection_rate_delta_pp": round(rate_b - rate_a, 6) if rate_a is not None and rate_b is not None else None,
                     "target_a": target_a, "target_b": target_b,
                     "attainment_a": _percent(quantity_a, target_a) if target_a else None,
                     "attainment_b": _percent(quantity_b, target_b) if target_b else None,
                     "target_scope_a": scope_a, "target_scope_b": scope_b,
                     "trend_a": _trend(row_a, buckets_a, granularity),
                     "trend_b": _trend(row_b, buckets_b, granularity)})
    delta_records, percent_records, percent_state = _change(len(events_a), len(events_b))

    def period(first, last, events):
        totals = Counter()
        for event in events:
            totals[event["unit"]] += event["quantity"]
        return {"from": first.isoformat(), "to": last.isoformat(), "days": (last - first).days + 1,
                "event_count": len(events), "totals_by_unit": dict(sorted(totals.items()))}

    return {"period_a": period(first_a, last_a, events_a), "period_b": period(first_b, last_b, events_b),
            "granularity": granularity, "group_by": group_by, "rows": rows,
            "summary": {"records_a": len(events_a), "records_b": len(events_b),
                        "delta_records": delta_records, "percent_records": percent_records, "percent_state": percent_state},
            "series_a": _series(events_a, buckets_a, granularity), "series_b": _series(events_b, buckets_b, granularity),
            "applied_filters": {key: query[key] for key in FILTER_LABELS if query.get(key)},
            "target_scope_labels": TARGET_SCOPES,
            "rates_denominator": "evaluated = approved + rejected; solo registros de revisión técnica",
            "variation_formula": "(B - A) / A * 100; A = 0 y B > 0: sin base",
            "comparison_scope": ("Totales brutos de los rangos elegidos; no se normalizan por duración. "
                                 "Cantidades separadas por actividad y unidad." if group_by != "technician" else
                                 "Totales brutos de los rangos elegidos; no se normalizan por duración. "
                                 "Cantidades por técnico y unidad; pueden incluir actividades distintas y no representan medidores físicos únicos.")}


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
    rows.append(["Contexto", "Solo registros válidos. Cantidades con su unidad; los registros cuentan operaciones.", *([""] * (columns - 2))])
    return rows


def _report_limit(rows):
    if len(rows) > MAX_REPORT_ROWS:
        raise production.ApiError(f"El reporte supera {MAX_REPORT_ROWS} filas; reduce el período o los filtros.", 413)
    return rows


def export_rows(db, user, query, report):
    """Tabla completa para documents.write_*; las filas Contexto retienen los filtros."""
    if report == "calidad":
        # La paginación de pantalla no recorta una exportación institucional.
        result = _quality(db, user, query, all_failures=True)
        period = result["period"]
        title = (f"Calidad {period['desde']} a {period['hasta']} | {period['granularity']} | "
                 "Tasas sobre evaluados = aptos + no aptos")
        headers = ["Sección", "Dimensión", "Revisiones", "Evaluados", "Aptos", "No aptos", "Pendientes", "Sin resultado",
                   "Aprobación %", "Rechazo %", "Calibraciones", "Fuera de tolerancia", "Desviación media %",
                   "Desviación absoluta media %", "Semáforo", "Cantidad producida", "Unidad de cantidad",
                   "Meta del período", "Cumplimiento meta %", "Alcance de meta", "Serie", "Fecha", "Resultado",
                   "Inspección", "Fallo informado", "Fuera de tolerancia (detalle)", "ID registro"]
        def padded(row):
            return [*row, *([""] * (len(headers) - len(row)))]
        rows = _metadata_rows(result["applied_filters"], len(headers))
        rows.append(["Contexto", result["deviation_formula"], *([""] * (len(headers) - 2))])
        metrics = ("total", "evaluated", "approved", "rejected", "pending", "without_result", "approval_rate", "rejection_rate",
                   "calibrations", "calibrations_outside_tolerance", "mean_deviation_pct", "mean_absolute_deviation_pct", "traffic_light")
        rows.append(padded(["Resumen", "Laboratorio / alcance autorizado", *(result["summary"][key] for key in metrics)]))
        for person in result["by_technician"]:
            rows.append(padded(["Colaborador", f"{person['name']} ({person['username']})", *(person[key] for key in metrics),
                                person["produced_quantity"], person["unit"], person["assigned_target"], person["attainment"],
                                TARGET_SCOPES[person["target_scope"]]]))
        for bucket in result["by_period"]:
            rows.append(padded(["Período", f"{bucket['label']} ({bucket['from']} a {bucket['to']})", *(bucket[key] for key in metrics)]))
        for failure in result["by_failure"]:
            rows.append(["Fallo", failure["label"], failure["value"], *([""] * (len(headers) - 3))])
        for failure in result["detailed_failures"]:
            rows.append(["Detalle de fallo", f"{failure['responsible_name']} ({failure['responsible_username']})",
                         *([""] * len(metrics)), "", "", "", "", "", failure["serial"], failure["work_date"],
                         failure["result"], failure["inspection_type"], failure["failure"],
                         failure["outside_tolerance"], failure["event_id"]])
        return headers, _report_limit(rows), title
    if report == "comparativas":
        result = _comparison(db, user, query)
        pa, pb = result["period_a"], result["period_b"]
        title = (f"Comparativa A: {pa['from']} a {pa['to']} | B: {pb['from']} a {pb['to']} | "
                 f"{result['granularity']} | {GROUP_LABELS[result['group_by']]} | Variación (B-A)/A; A=0 sin base")
        headers = ["Sección", "Actividad / período", "Unidad", "Cantidad A", "Cantidad B", "Diferencia B-A", "Variación %",
                   "Base del porcentaje", "Registros A", "Registros B", "Diferencia registros", "Variación registros %",
                   "Responsable", "Código empleado", "Aptos A", "Aptos B", "No aptos A", "No aptos B",
                   "Evaluados A", "Evaluados B", "Rechazo A %", "Rechazo B %", "Variación rechazo pp",
                   "Meta A", "Meta B", "Cumplimiento A %", "Cumplimiento B %", "Alcance meta A", "Alcance meta B"]
        def padded(row):
            return [*row, *([""] * (len(headers) - len(row)))]
        grouping_label = GROUP_LABELS[result["group_by"]]
        rows = _metadata_rows({**result["applied_filters"], "group_by": grouping_label}, len(headers))
        rows.append(["Contexto", result["comparison_scope"], *([""] * (len(headers) - 2))])
        rows.append(["Contexto", result["rates_denominator"], *([""] * (len(headers) - 2))])
        summary = result["summary"]
        rows.append(padded(["Resumen", "Registros en el alcance autorizado", "registros", "", "", "", "", summary["percent_state"],
                            summary["records_a"], summary["records_b"], summary["delta_records"], summary["percent_records"]]))
        for row in result["rows"]:
            section = "Actividad" if result["group_by"] == "activity" else "Técnico / actividad" if result["group_by"] == "technician_activity" else "Técnico / unidad"
            rows.append([section, row["activity_name"], row["unit"], row["a"], row["b"], row["delta"], row["percent"],
                         row["percent_state"], row["records_a"], row["records_b"], row["delta_records"], row["percent_records"],
                         row["responsible_name"], row["responsible_username"], row["approved_a"], row["approved_b"],
                         row["rejected_a"], row["rejected_b"], row["evaluated_a"], row["evaluated_b"],
                         row["rejection_rate_a"], row["rejection_rate_b"], row["rejection_rate_delta_pp"],
                         row["target_a"], row["target_b"], row["attainment_a"], row["attainment_b"],
                         TARGET_SCOPES[row["target_scope_a"]], TARGET_SCOPES[row["target_scope_b"]]])
        for letter, series in (("A", result["series_a"]), ("B", result["series_b"])):
            for bucket in series:
                # Los registros aparecen una sola vez por intervalo, separados de
                # las cantidades por unidad para impedir una suma duplicada.
                rows.append(padded([f"Serie {letter}", f"{bucket['label']} ({bucket['from']} a {bucket['to']})", "registros", "", "", "", "", "",
                                    bucket["records"] if letter == "A" else "", bucket["records"] if letter == "B" else "", "", ""]))
                for unit, quantity in bucket["totals_by_unit"].items():
                    rows.append(padded([f"Cantidad {letter}", bucket["label"], unit, quantity if letter == "A" else "",
                                        quantity if letter == "B" else "", "", "", "", "", "", "", ""]))
        return headers, _report_limit(rows), title
    raise production.ApiError("Selecciona un reporte de calidad o comparativas.")
