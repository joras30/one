"""Catálogo abierto, recepción certificada y auditoría encadenada.

Solo usa SQLite y biblioteca estándar. La base y sus datos permanecen en el
servidor (o en la demostración individual). Ningún registro histórico se borra.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, DecimalException
import hashlib
import json
import math
import re
import uuid

import production as p


AUDIT_COLUMNS = ("id", "actor_id", "entity", "entity_id", "action", "before_json",
                 "after_json", "reason", "created_at")


def _audit_digest(row, previous):
    return hashlib.sha256(p._json({"previous": previous, **{k: row[k] for k in AUDIT_COLUMNS}}).encode()).hexdigest()


def init_schema(db):
    columns = {r[1] for r in db.execute("PRAGMA table_info(audit_entries)")}
    for name in ("previous_hash", "entry_hash"):
        if name not in columns:
            db.execute(f"ALTER TABLE audit_entries ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS sap_configurations (
            id TEXT PRIMARY KEY, code TEXT NOT NULL REFERENCES sap_catalog(code),
            voltage TEXT NOT NULL DEFAULT '', classification TEXT NOT NULL DEFAULT '',
            brand TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '', label TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sap_configurations_code ON sap_configurations(code);
        CREATE TABLE IF NOT EXISTS receipt_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            process TEXT NOT NULL, process_key TEXT UNIQUE NOT NULL,
            order_number TEXT NOT NULL, sap TEXT NOT NULL,
            expected INTEGER CHECK(expected IS NULL OR expected>=0),
            due_date TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
            state TEXT NOT NULL DEFAULT 'abierta' CHECK(state IN ('abierta','cerrada')),
            process_conflict INTEGER NOT NULL DEFAULT 0,
            source_process_conflict INTEGER NOT NULL DEFAULT 0,
            created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            closed_by INTEGER REFERENCES users(id), closed_at TEXT,
            UNIQUE(order_number,sap)
        );
        CREATE TABLE IF NOT EXISTS receipt_links (
            event_id INTEGER PRIMARY KEY REFERENCES production_events(id),
            order_id INTEGER NOT NULL REFERENCES receipt_orders(id)
        );
        CREATE INDEX IF NOT EXISTS idx_receipt_links_order ON receipt_links(order_id);
        CREATE TABLE IF NOT EXISTS receipt_certificates (
            id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL REFERENCES receipt_orders(id),
            number TEXT UNIQUE NOT NULL, snapshot_json TEXT NOT NULL, hash TEXT NOT NULL,
            created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL
        );
        CREATE TRIGGER IF NOT EXISTS receipt_certificates_no_update BEFORE UPDATE ON receipt_certificates
            BEGIN SELECT RAISE(ABORT,'Las actas certificadas son inmutables.'); END;
        CREATE TRIGGER IF NOT EXISTS receipt_certificates_no_delete BEFORE DELETE ON receipt_certificates
            BEGIN SELECT RAISE(ABORT,'Las actas certificadas son inmutables.'); END;
        CREATE TRIGGER IF NOT EXISTS receipt_certificates_no_replace BEFORE INSERT ON receipt_certificates
            WHEN EXISTS(SELECT 1 FROM receipt_certificates WHERE id=NEW.id OR number=NEW.number)
            BEGIN SELECT RAISE(ABORT,'Las actas certificadas no se reemplazan.'); END;
    """)
    order_columns = {r[1] for r in db.execute("PRAGMA table_info(receipt_orders)")}
    if "source_process_conflict" not in order_columns:
        db.execute("ALTER TABLE receipt_orders ADD COLUMN source_process_conflict INTEGER NOT NULL DEFAULT 0")
    with p._transaction(db):
        if not db.execute("SELECT 1 FROM production_meta WHERE key='audit_chain_v6'").fetchone():
            previous = "0" * 64
            for row in db.execute("SELECT * FROM audit_entries ORDER BY id").fetchall():
                digest = _audit_digest(row, previous)
                db.execute("UPDATE audit_entries SET previous_hash=?,entry_hash=? WHERE id=?", (previous, digest, row["id"]))
                previous = digest
            db.execute("INSERT INTO production_meta(key,value) VALUES('audit_head',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (previous,))
            db.execute("INSERT INTO production_meta VALUES('audit_chain_v6',?)", (p.now(),))
        for row in db.execute("SELECT * FROM sap_catalog").fetchall():
            if not db.execute("SELECT 1 FROM sap_configurations WHERE code=?", (row["code"],)).fetchone():
                db.execute("""INSERT INTO sap_configurations
                    (id,code,voltage,classification,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?)""",
                           ("default:" + row["code"], row["code"], row["voltage"], row["classification"], row["active"], row["updated_at"], row["updated_at"]))
        _upgrade_fields(db)
        # La asociación se añade aparte: los JSON históricos siguen intactos.
        rows = db.execute("""SELECT id FROM production_events WHERE activity_id='recepcion'
            AND id NOT IN (SELECT event_id FROM receipt_links) ORDER BY work_date,id""").fetchall()
        for row in rows:
            attach_receipt(db, None, p._event(db, row["id"]), migrating=True)
    db.executescript("""
        CREATE TRIGGER IF NOT EXISTS audit_entries_no_update BEFORE UPDATE ON audit_entries
            BEGIN SELECT RAISE(ABORT,'La auditoría es de solo adición.'); END;
        CREATE TRIGGER IF NOT EXISTS audit_entries_no_delete BEFORE DELETE ON audit_entries
            BEGIN SELECT RAISE(ABORT,'La auditoría es de solo adición.'); END;
        CREATE TRIGGER IF NOT EXISTS audit_entries_no_replace BEFORE INSERT ON audit_entries
            WHEN EXISTS(SELECT 1 FROM audit_entries WHERE id=NEW.id)
            BEGIN SELECT RAISE(ABORT,'La auditoría no admite reemplazos.'); END;
    """)


def _upgrade_fields(db):
    if db.execute("SELECT 1 FROM production_meta WHERE key='operational_fields_v6'").fetchone():
        return
    for row in db.execute("SELECT * FROM activities").fetchall():
        old = db.execute("SELECT * FROM activity_versions WHERE activity_id=? AND version=?", (row["id"], row["current_version"])).fetchone()
        fields = json.loads(old["fields_json"])
        keys = {f["key"] for f in fields}
        additions = []
        if "sap" in keys:
            additions.append(p._field("sap_config_id", "Configuración del SAP", required=False, maximum=160))
        if row["id"] in {"revision", "sellado"}:
            additions.append(p._field("modelo", "Modelo", required=False, maximum=150))
        if row["id"] == "revision":
            additions += [p._field("tipo_inspeccion", "Tipo de inspección", "select", False, ["Inspección", "Calibración"]),
                          p._field("fallo", "Fallo detectado", required=False, maximum=500),
                          p._field("valor_referencia", "Valor de referencia", "number", False, min=-1e12, max=1e12),
                          p._field("valor_medido", "Valor medido", "number", False, min=-1e12, max=1e12),
                          p._field("tolerancia_pct", "Tolerancia (%)", "number", False, min=0, max=1e6)]
        fields += [f for f in additions if f["key"] not in keys]
        if fields == json.loads(old["fields_json"]):
            continue
        version = row["current_version"] + 1
        db.execute("""INSERT INTO activity_versions(activity_id,version,name,mode,unit,fields_json,created_at)
            VALUES(?,?,?,?,?,?,?)""", (row["id"], version, old["name"], old["mode"], old["unit"], p._json(fields), p.now()))
        db.execute("UPDATE activities SET current_version=? WHERE id=?", (version, row["id"]))
    db.execute("INSERT INTO production_meta VALUES('operational_fields_v6',?)", (p.now(),))


def audit(db, actor, entity, entity_id, action, before=None, after=None, reason=""):
    actor_id = actor.get("id") if isinstance(actor, dict) else actor
    with p._transaction(db):
        last = db.execute("SELECT id,entry_hash FROM audit_entries ORDER BY id DESC LIMIT 1").fetchone()
        previous = last["entry_hash"] if last else "0" * 64
        row = {"id": last["id"] + 1 if last else 1, "actor_id": actor_id,
               "entity": str(entity), "entity_id": str(entity_id), "action": str(action),
               "before_json": p._json(before) if before is not None else None,
               "after_json": p._json(after) if after is not None else None,
               "reason": str(reason or "")[:1500], "created_at": p.now()}
        digest = _audit_digest(row, previous)
        db.execute("""INSERT INTO audit_entries(id,actor_id,entity,entity_id,action,before_json,after_json,reason,created_at,previous_hash,entry_hash)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (*[row[k] for k in AUDIT_COLUMNS], previous, digest))
        db.execute("INSERT INTO production_meta(key,value) VALUES('audit_head',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (digest,))


def audit_integrity(db, user):
    p._manager(user)
    previous, count = "0" * 64, 0
    for row in db.execute("SELECT * FROM audit_entries ORDER BY id"):
        count += 1
        if row["previous_hash"] != previous or row["entry_hash"] != _audit_digest(row, previous):
            return {"ok": False, "entries": count, "head_hash": previous, "invalid_id": row["id"]}
        previous = row["entry_hash"]
    stored = db.execute("SELECT value FROM production_meta WHERE key='audit_head'").fetchone()
    return {"ok": bool(stored and stored[0] == previous), "entries": count, "head_hash": previous}


def sap_items(db):
    result = []
    for row in db.execute("SELECT code,voltage,classification,active FROM sap_catalog ORDER BY code"):
        configs = [{**dict(config), "active": bool(config["active"])} for config in db.execute(
            "SELECT id,code,voltage,classification,brand,model,label,active FROM sap_configurations WHERE code=? ORDER BY created_at,id", (row["code"],))]
        result.append({**dict(row), "active": bool(row["active"]), "configurations": configs})
    return {"items": result}


def save_sap(db, user, data):
    p._manager(user)
    if not isinstance(data.get("code"), str):
        raise p.ApiError("Código SAP: introduce el identificador como texto.")
    code = p._text(data["code"], "Código SAP", 60, True)
    voltage = p._text(data.get("voltage"), "Voltaje", 100)
    classification = p._text(data.get("classification"), "Clasificación", 100)
    classification = {"nuevo": "Nuevo", "recuperado": "Recuperado"}.get(p._fold(classification), classification)
    active = bool(data.get("active", True))
    config_requested = data.get("configuration_id")
    config_id = "default:" + code if not config_requested else "config:" + uuid.uuid4().hex if config_requested == "new" else p._text(config_requested, "Configuración SAP", 160, True)
    with p._transaction(db):
        previous = db.execute("SELECT * FROM sap_configurations WHERE id=?", (config_id,)).fetchone()
        if config_requested not in (None, "", "new") and (not previous or previous["code"] != code):
            raise p.ApiError("La configuración no pertenece a ese código SAP.", 404)
        timestamp = p.now()
        master = db.execute("SELECT * FROM sap_catalog WHERE code=?", (code,)).fetchone()
        if not master:
            db.execute("INSERT INTO sap_catalog(code,voltage,classification,active,updated_at) VALUES(?,?,?,?,?)", (code, voltage, classification, 1, timestamp))
        elif not config_requested or config_id == "default:" + code:
            db.execute("UPDATE sap_catalog SET voltage=?,classification=?,active=?,updated_at=? WHERE code=?", (voltage, classification, int(active), timestamp, code))
        values = {"id": config_id, "code": code, "voltage": voltage, "classification": classification,
                  "brand": p._text(data.get("brand"), "Marca sugerida", 150), "model": p._text(data.get("model"), "Modelo sugerido", 150),
                  "label": p._text(data.get("label"), "Descripción", 150), "active": active}
        db.execute("""INSERT INTO sap_configurations(id,code,voltage,classification,brand,model,label,active,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET voltage=excluded.voltage,classification=excluded.classification,
            brand=excluded.brand,model=excluded.model,label=excluded.label,active=excluded.active,updated_at=excluded.updated_at""",
                   (config_id, code, voltage, classification, values["brand"], values["model"], values["label"], int(active), timestamp, timestamp))
        # Añade opciones, sin asociarlas de forma exclusiva al código o marca.
        if voltage:
            db.execute("INSERT OR IGNORE INTO catalog(kind,label) VALUES('voltajes',?)", (voltage,))
        audit(db, user, "sap", code, "actualizar" if previous else "crear", dict(previous) if previous else None, values)
    return {"ok": True, "configuration": values}


def prepare_sap(db, activity, raw, existing):
    known = {f["key"] for f in activity["fields"]}
    raw = dict(raw)
    old = existing["data"] if existing else {}
    if existing and all(raw.get(k, "") == old.get(k, "") for k in ("sap", "sap_config_id", "voltaje", "clasificacion")):
        return raw
    code = p._text(raw.get("sap"), "Código SAP", 60)
    if not code:
        if raw.get("sap_config_id"):
            raise p.ApiError("Selecciona un SAP antes de su configuración.")
        return raw
    master = db.execute("SELECT * FROM sap_catalog WHERE code=?", (code,)).fetchone()
    if master and not master["active"]:
        raise p.ApiError("Ese SAP está desactivado para nuevas capturas.")
    configs = [dict(r) for r in db.execute("SELECT * FROM sap_configurations WHERE code=? AND active=1", (code,))]
    selected_id = raw.get("sap_config_id")
    if selected_id:
        selected = next((r for r in configs if r["id"] == selected_id), None)
        if not selected:
            raise p.ApiError("La configuración SAP seleccionada no está activa o pertenece a otro código.")
        for key, source in (("voltaje", "voltage"), ("clasificacion", "classification")):
            if raw.get(key) not in (None, "") and selected[source] and p._fold(raw[key]) != p._fold(selected[source]):
                raise p.ApiError("Los datos no coinciden con la configuración SAP seleccionada. Elige otra configuración o actualiza el catálogo.")
    else:
        matches = [r for r in configs if all(raw.get(key) in (None, "") or not r[source] or p._fold(raw[key]) == p._fold(r[source]) for key, source in (("voltaje", "voltage"), ("clasificacion", "classification")))]
        if len(matches) > 1:
            raise p.ApiError("Este SAP tiene varias configuraciones. Selecciona la que corresponde al medidor.", 409, configurations=matches, needs_sap_configuration=True)
        selected = matches[0] if matches else None
        if configs and not selected and activity["id"] == "sellado":
            raise p.ApiError("Registra o selecciona una configuración SAP compatible antes de sellar.")
    if selected:
        for key, source in (("voltaje", "voltage"), ("clasificacion", "classification"), ("marca", "brand"), ("modelo", "model")):
            if key in known and raw.get(key) in (None, ""):
                raw[key] = selected[source]
        if "sap_config_id" in known:
            raw["sap_config_id"] = selected["id"]
    if activity["id"] == "sellado" and master and not raw.get("clasificacion"):
        raise p.ApiError("La configuración SAP necesita una clasificación antes de registrar el sellado.")
    return raw


def derive_quality(activity, clean):
    if activity["id"] != "revision":
        return clean
    keys = ("valor_referencia", "valor_medido", "tolerancia_pct")
    present = [clean.get(k) not in (None, "") for k in keys]
    if any(present) and not all(present):
        raise p.ApiError("Para calcular la calibración, completa referencia, medición y tolerancia.")
    if all(present):
        try:
            if any(isinstance(clean[k], bool) for k in keys):
                raise ValueError()
            reference, measured, tolerance = [Decimal(str(clean[k])) for k in keys]
            if not all(number.is_finite() for number in (reference, measured, tolerance)):
                raise ValueError()
            if abs(reference) > Decimal('1e12') or abs(measured) > Decimal('1e12') or not 0 <= tolerance <= Decimal('1e6'):
                raise ValueError()
            if reference == 0:
                raise p.ApiError("El valor de referencia debe ser distinto de cero.")
            deviation = (measured - reference) / abs(reference) * 100
            floating_deviation = float(deviation)
        except (DecimalException, ValueError, TypeError, OverflowError):
            raise p.ApiError("La calibración requiere valores numéricos finitos y una tolerancia no negativa dentro del rango admitido.") from None
        if not math.isfinite(floating_deviation):
            raise p.ApiError("La desviación calculada excede el rango numérico admitido. Revisa los valores de calibración.")
        clean["desviacion_pct"] = floating_deviation
        clean["fuera_tolerancia"] = abs(deviation) > tolerance
        if clean["fuera_tolerancia"] and p._fold(clean.get("resultado")) == "apto":
            raise p.ApiError("Una calibración fuera de tolerancia no puede marcarse Apto.")
    return clean


def _order_row(db, order_id):
    row = db.execute("SELECT * FROM receipt_orders WHERE id=?", (order_id,)).fetchone()
    if not row:
        raise p.ApiError("La orden de recepción no existe.", 404)
    return row


def _access_order(db, user, order_id):
    if user["role"] == "visitante":
        raise p.ApiError("La cuenta visitante no consulta órdenes individuales.", 403)
    if user["role"] not in p.MANAGERS and not db.execute("""SELECT 1 FROM receipt_links l JOIN production_events e ON e.id=l.event_id
        WHERE l.order_id=? AND e.responsible_id=?""", (order_id, user["id"])).fetchone():
        raise p.ApiError("No tienes entregas vinculadas a esta orden.", 403)


def _order_summary(db, row, user, cutoff=""):
    params = [row["id"]]
    sql = """SELECT e.* FROM production_events e JOIN receipt_links l ON l.event_id=e.id
        WHERE l.order_id=? AND e.state='valido'"""
    if cutoff:
        sql += " AND e.work_date<=?"
        params.append(cutoff)
    events = db.execute(sql, params).fetchall()
    received = sum(e["quantity"] for e in events)
    expected = row["expected"]
    pending = max(0, expected - received) if expected is not None else None
    excess = max(0, received - expected) if expected is not None else 0
    closed_at_cutoff = row["state"] == "cerrada" and (not cutoff or (row["closed_at"] or "")[:10] <= cutoff) and not pending and not excess
    state = "cerrada" if closed_at_cutoff else "por_confirmar" if expected is None else "pendiente" if pending else "completa"
    today = datetime.now(timezone(timedelta(hours=-4))).date().isoformat()
    overdue = bool(row["due_date"] and row["due_date"] < (cutoff or today) and state not in {"completa", "cerrada"})
    signal = "rojo" if overdue or excess or row["process_conflict"] else "verde" if state in {"completa", "cerrada"} else "amarillo"
    result = {"id": row["id"], "process": row["process"], "order_number": row["order_number"], "order": row["order_number"],
              "sap": row["sap"], "expected": expected, "received": received, "pending": pending, "excess": excess,
              "state": state, "signal": signal, "due_date": row["due_date"], "overdue": overdue,
              "process_conflict": bool(row["process_conflict"]), "notes": row["notes"], "deliveries": len(events),
              "last_date": max((e["work_date"] for e in events), default=""), "created_at": row["created_at"],
              "closed_at": row["closed_at"], "scope": "orden"}
    if p.phase2.enabled(db):
        provider=db.execute("SELECT provider FROM p2_receipt_providers WHERE order_id=?",(row["id"],)).fetchone()
        result["provider"]=provider[0] if provider else ""
    result["administrative_state"] = row["state"]
    result["as_of"] = cutoff or today
    result["progress_pct"] = round(received / expected * 100, 6) if expected else None
    if user["role"] == "tecnico":
        result["own_received"] = sum(e["quantity"] for e in events if e["responsible_id"] == user["id"])
    return result


def list_orders(db, user, query, allow_visitor=False):
    if user["role"] == "visitante" and not allow_visitor:
        raise p.ApiError("La cuenta visitante no consulta órdenes individuales.", 403)
    cutoff = p._date(query["hasta"], "Hasta") if query.get("hasta") else ""
    if query.get("desde"):
        p._date(query["desde"], "Desde")
        if cutoff and query["desde"] > cutoff:
            raise p.ApiError("La fecha Desde no puede ser posterior a Hasta.")
    filters = {**query, "activity_id": "recepcion", "state": "valido"}
    filters.pop("desde", None)  # El saldo es acumulado, con corte inclusivo.
    where, params = p._filters(user, filters, allow_visitor=allow_visitor)
    scoped_ids = {r[0] for r in db.execute("SELECT DISTINCT rl.order_id FROM production_events e JOIN receipt_links rl ON rl.event_id=e.id" + where, params)}
    allow_empty = user["role"] in p.MANAGERS or (user["role"] == "visitante" and allow_visitor)
    allow_empty = allow_empty and not any(query.get(k) for k in ("responsible_id", "voltage", "condition", "brand", "model", "meter"))
    result = []
    for row in db.execute("SELECT * FROM receipt_orders ORDER BY created_at DESC,id DESC"):
        if query.get("sap") and query["sap"] != row["sap"]:
            continue
        if row["id"] not in scoped_ids:
            if not allow_empty or (cutoff and row["created_at"][:10] > cutoff):
                continue
            # Mantener una orden vacía en seguimiento; un filtro por persona o
            # atributos de medidores, en cambio, exige una entrega que coincida.
            any_event = db.execute("SELECT 1 FROM receipt_links WHERE order_id=?", (row["id"],)).fetchone()
            if any_event and cutoff:
                continue
        item = _order_summary(db, row, user, cutoff)
        if query.get("state") and query["state"] != item["state"]:
            continue
        result.append(item)
    return {"orders": result, "summary": receipt_summary(result)}


def receipt_summary(orders):
    """Saldos por orden, sin compensar faltantes con excedentes de otro proceso.

    Las órdenes sin cantidad esperada participan en recibido, pero no inventan
    un denominador para avance ni convierten su pendiente desconocido en cero.
    """
    known = [order for order in orders if order["expected"] is not None]
    expected = sum(order["expected"] for order in known)
    received = sum(order["received"] for order in orders)
    fulfilled = sum(min(order["received"], order["expected"]) for order in known)
    unknown = len(orders) - len(known)
    return {"order_count": len(orders), "expected_total": expected, "ordered": expected,
            "received_total": received, "received_known_total": sum(order["received"] for order in known),
            "pending_total": sum(order["pending"] for order in known),
            "excess_total": sum(order["excess"] for order in known),
            "unknown_orders": unknown, "expected_known": unknown == 0,
            "completed_orders": sum(order["state"] in {"completa", "cerrada"} for order in orders),
            "pending_orders": sum(order["pending"] is None or order["pending"] > 0 for order in orders),
            "overdue_orders": sum(bool(order["overdue"]) for order in orders),
            "fulfillment_pct": round(fulfilled / expected * 100, 6) if expected else None,
            "scope": "historial acumulado al corte; esperado conocido; avance limitado por orden"}


def receipts(db, user, query=None, allow_visitor=False):
    filters = dict(query or {})
    filters.pop("state", None)
    return list_orders(db, user, filters, allow_visitor=allow_visitor)["orders"]


def save_order(db, user, data):
    p._manager(user)
    with p._transaction(db):
        existing = _order_row(db, p._integer(data["id"], "Orden", 1, 2**63-1)) if data.get("id") else None
        if existing and existing["state"] == "cerrada":
            raise p.ApiError("Reabre la orden antes de modificarla.", 409)
        reason = p._text(data.get("reason"), "Motivo de cambio", 1500, bool(existing))
        process = p._text(data.get("process", existing["process"] if existing else ""), "Número de proceso", 160, True)
        order_number = p._text(data.get("order_number", existing["order_number"] if existing else ""), "Número de orden", 160, True)
        sap = p._text(data.get("sap", existing["sap"] if existing else ""), "Código SAP", 60, True)
        expected_raw = data.get("expected", existing["expected"] if existing else None)
        expected = None if expected_raw in (None, "") else p._integer(expected_raw, "Cantidad esperada", 0)
        due_date = p._date(data["due_date"], "Fecha de seguimiento") if data.get("due_date") else existing["due_date"] if existing and "due_date" not in data else ""
        notes = p._text(data.get("notes", existing["notes"] if existing else ""), "Observaciones", 1500)
        others = db.execute("SELECT id,process FROM receipt_orders").fetchall()
        if any(r["id"] != (existing["id"] if existing else None) and p._fold(r["process"]) == p._fold(process) for r in others):
            raise p.ApiError("Ese número de proceso ya pertenece a otra orden.", 409)
        duplicate = db.execute("SELECT id FROM receipt_orders WHERE order_number=? AND sap=?", (order_number, sap)).fetchone()
        if duplicate and (not existing or duplicate["id"] != existing["id"]):
            raise p.ApiError("La combinación orden y SAP ya existe. Registra una entrega en esa orden.", 409)
        if existing and (order_number != existing["order_number"] or sap != existing["sap"]):
            raise p.ApiError("La orden y su SAP se conservan. Crea otra orden para otro material.")
        timestamp = p.now()
        if existing:
            order_id = existing["id"]
            db.execute("UPDATE receipt_orders SET process=?,process_key=?,expected=?,due_date=?,notes=?,process_conflict=0,source_process_conflict=0,updated_at=? WHERE id=?", (process, p._fold(process), expected, due_date, notes, timestamp, order_id))
        else:
            order_id = db.execute("""INSERT INTO receipt_orders(process,process_key,order_number,sap,expected,due_date,notes,created_by,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)""", (process, p._fold(process), order_number, sap, expected, due_date, notes, user["id"], timestamp, timestamp)).lastrowid
        # Al resolver una colisión histórica también se libera la otra orden,
        # siempre que su proceso haya quedado inequívoco.
        all_orders = db.execute("SELECT id,process,source_process_conflict FROM receipt_orders").fetchall()
        frequencies = {}
        for candidate in all_orders:
            key = p._fold(candidate["process"])
            frequencies[key] = frequencies.get(key, 0) + 1
        for candidate in all_orders:
            key = p._fold(candidate["process"])
            db.execute("UPDATE receipt_orders SET process_conflict=? WHERE id=?", (int(not key or frequencies[key] > 1 or candidate["source_process_conflict"]), candidate["id"]))
        if p.phase2.enabled(db) and "provider" in data:
            provider=p._text(data["provider"],"Proveedor",150)
            db.execute("INSERT INTO p2_receipt_providers VALUES(?,?) ON CONFLICT(order_id) DO UPDATE SET provider=excluded.provider",(order_id,provider))
        result = _order_summary(db, _order_row(db, order_id), user)
        audit(db, user, "orden", order_id, "actualizar" if existing else "crear", dict(existing) if existing else None, result, reason)
    return {"ok": True, "order": result}


def assert_receipt_open(db, event):
    row = db.execute("SELECT o.* FROM receipt_orders o JOIN receipt_links l ON l.order_id=o.id WHERE l.event_id=?", (event["id"],)).fetchone()
    if row and row["state"] == "cerrada":
        raise p.ApiError("La entrega pertenece a un lote cerrado. Supervisión debe reabrirlo con un motivo antes de modificarlo.", 409)


def attach_receipt(db, user, event, migrating=False, existing=None):
    if event["activity_id"] != "recepcion":
        return
    values = event["data"]
    order_number, sap = values.get("numero_orden", ""), values.get("sap", "")
    process = values.get("proceso", "")
    row = db.execute("SELECT * FROM receipt_orders WHERE order_number=? AND sap=?", (order_number, sap)).fetchone()
    expected = values.get("cantidad_esperada")
    expected = None if expected in (None, "") else int(expected)
    original_data = existing["data"] if existing else None
    same_order = bool(existing and original_data.get("numero_orden", "") == order_number and original_data.get("sap", "") == sap)
    if not row:
        duplicate = [r for r in db.execute("SELECT id,process FROM receipt_orders") if p._fold(r["process"]) == p._fold(process)]
        if duplicate and not migrating:
            raise p.ApiError("Ese número de proceso está vinculado a otra orden o SAP.", 409)
        conflict = bool(duplicate) or not process
        process_key = ("legacy:" + str(event["id"])) if conflict else p._fold(process)
        timestamp = p.now()
        order_id = db.execute("""INSERT INTO receipt_orders(process,process_key,order_number,sap,expected,process_conflict,created_by,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?)""", (process, process_key, order_number, sap, expected if event["state"] == "valido" else None, int(conflict), event["recorded_by"], timestamp, timestamp)).lastrowid
        if duplicate:
            db.executemany("UPDATE receipt_orders SET process_conflict=1 WHERE id=?", [(r["id"],) for r in duplicate])
        row = _order_row(db, order_id)
        if not migrating:
            audit(db, user, "orden", order_id, "crear_desde_entrega", after=dict(row))
    elif migrating:
        if p._fold(row["process"]) != p._fold(process):
            db.execute("UPDATE receipt_orders SET process_conflict=1,source_process_conflict=1 WHERE id=?", (row["id"],))
    else:
        if row["state"] == "cerrada":
            raise p.ApiError("El lote está cerrado. Reábrelo antes de registrar otra entrega.", 409)
        if p._fold(row["process"]) != p._fold(process) and not (same_order and process == original_data.get("proceso", "")):
            raise p.ApiError("El número de proceso no coincide con la orden de recepción.", 409)
        if expected is not None and expected != row["expected"] and not (same_order and expected == original_data.get("cantidad_esperada")):
            raise p.ApiError("La cantidad esperada difiere de la orden. Supervisión debe actualizar la orden con un motivo.", 409)
    if expected is not None and migrating and event["state"] == "valido":
        db.execute("UPDATE receipt_orders SET expected=?,updated_at=? WHERE id=?", (expected, p.now(), row["id"]))
    db.execute("INSERT INTO receipt_links(event_id,order_id) VALUES(?,?) ON CONFLICT(event_id) DO UPDATE SET order_id=excluded.order_id", (event["id"], row["id"]))


def order_detail(db, user, order_id):
    row = _order_row(db, order_id)
    _access_order(db, user, order_id)
    sql = p.EVENT_SELECT + " JOIN receipt_links rl ON rl.event_id=e.id WHERE rl.order_id=?"
    params = [order_id]
    if user["role"] == "tecnico":
        sql += " AND e.responsible_id=?"
        params.append(user["id"])
    deliveries = [p._serialize(r, db) for r in db.execute(sql + " ORDER BY e.work_date,e.id", params)]
    certificates = []
    if user["role"] in p.MANAGERS:
        rows = db.execute("SELECT id,number,hash,created_at FROM receipt_certificates WHERE order_id=? ORDER BY id DESC", (order_id,)).fetchall()
        for certificate_row in rows:
            certificates.append({**dict(certificate_row), "current": bool(row["state"] == "cerrada" and certificate_row["id"] == rows[0]["id"])})
    return {"order": _order_summary(db, row, user), "deliveries": deliveries, "certificates": certificates}


def close_order(db, user, order_id, data):
    p._manager(user)
    with p._transaction(db):
        row = _order_row(db, order_id)
        if row["state"] == "cerrada":
            return {"ok": True, "order": _order_summary(db, row, user), "already_saved": True}
        detail = order_detail(db, user, order_id)
        summary = detail["order"]
        if summary["expected"] is None or summary["received"] != summary["expected"] or summary["process_conflict"]:
            raise p.ApiError("Para cerrar el lote, confirma el total esperado, resuelve su proceso único y completa exactamente las entregas pendientes.", 409)
        if len(detail["deliveries"]) > 10000:
            raise p.ApiError("El acta supera el máximo de 10.000 entregas.", 413)
        reason = p._text(data.get("reason"), "Observaciones de cierre", 1500)
        timestamp = p.now()
        snapshot = {"order": summary, "deliveries": [e for e in detail["deliveries"] if e["state"] == "valido"],
                    "certified_by": {"id": user["id"], "name": user.get("name", "Supervisión")}, "certified_at": timestamp, "reason": reason}
        digest = hashlib.sha256(p._json(snapshot).encode()).hexdigest()
        number_id = db.execute("SELECT COALESCE(MAX(id),0)+1 FROM receipt_certificates").fetchone()[0]
        number = f"ACTA-{timestamp[:4]}-{number_id:06d}"
        db.execute("INSERT INTO receipt_certificates(id,order_id,number,snapshot_json,hash,created_by,created_at) VALUES(?,?,?,?,?,?,?)", (number_id, order_id, number, p._json(snapshot), digest, user["id"], timestamp))
        db.execute("UPDATE receipt_orders SET state='cerrada',closed_by=?,closed_at=?,updated_at=? WHERE id=?", (user["id"], timestamp, timestamp, order_id))
        result = _order_summary(db, _order_row(db, order_id), user)
        audit(db, user, "orden", order_id, "cerrar", summary, {**result, "certificate_number": number, "certificate_hash": digest}, reason)
    return {"ok": True, "order": result, "certificate": {"id": number_id, "number": number, "hash": digest, "created_at": timestamp, "snapshot": snapshot}}


def reopen_order(db, user, order_id, data):
    p._manager(user)
    reason = p._text(data.get("reason"), "Motivo de reapertura", 1500, True)
    with p._transaction(db):
        row = _order_row(db, order_id)
        before = _order_summary(db, row, user)
        if row["state"] != "cerrada":
            raise p.ApiError("La orden ya está abierta.", 409)
        db.execute("UPDATE receipt_orders SET state='abierta',closed_by=NULL,closed_at=NULL,updated_at=? WHERE id=?", (p.now(), order_id))
        result = _order_summary(db, _order_row(db, order_id), user)
        audit(db, user, "orden", order_id, "reabrir", before, result, reason)
    return {"ok": True, "order": result}


def certificate(db, user, order_id, certificate_id=None):
    p._manager(user)
    order = _order_row(db, order_id)
    latest = db.execute("SELECT id FROM receipt_certificates WHERE order_id=? ORDER BY id DESC LIMIT 1", (order_id,)).fetchone()
    if certificate_id is None:
        row = db.execute("SELECT * FROM receipt_certificates WHERE order_id=? ORDER BY id DESC LIMIT 1", (order_id,)).fetchone()
    else:
        certificate_id = p._integer(certificate_id, "Acta", 1, 2**63 - 1)
        row = db.execute("SELECT * FROM receipt_certificates WHERE order_id=? AND id=?", (order_id, certificate_id)).fetchone()
    if not row:
        raise p.ApiError("La orden todavía no tiene un acta de cierre.", 404)
    snapshot = json.loads(row["snapshot_json"])
    digest = hashlib.sha256(p._json(snapshot).encode()).hexdigest()
    if digest != row["hash"]:
        raise p.ApiError("El acta no supera la comprobación de integridad.", 409)
    return {"certificate": {"id": row["id"], "number": row["number"], "hash": row["hash"], "created_at": row["created_at"],
                            "snapshot": snapshot, "current": bool(order["state"] == "cerrada" and latest and row["id"] == latest["id"]), "order_state": order["state"]}}


def handle_get(db, user, path, query):
    if path == "/api/auditoria/integridad":
        return audit_integrity(db, user)
    if path == "/api/ordenes":
        return list_orders(db, user, query)
    match = re.fullmatch(r"/api/ordenes/(\d+)(/acta)?", path)
    if match:
        return certificate(db, user, int(match.group(1)), query.get("certificate_id")) if match.group(2) else order_detail(db, user, int(match.group(1)))
    return None


def handle_post(db, user, path, data):
    if path == "/api/ordenes":
        return save_order(db, user, data)
    match = re.fullmatch(r"/api/ordenes/(\d+)/(cerrar|reabrir)", path)
    if match:
        return (close_order if match.group(2) == "cerrar" else reopen_order)(db, user, int(match.group(1)), data)
    return None
