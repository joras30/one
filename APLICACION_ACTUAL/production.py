"""Producción local: actividades versionadas, eventos y trazabilidad.

La tabla ``records`` del prototipo se conserva. Sus revisiones se incorporan una
sola vez al nuevo registro de eventos, manteniendo su identificador de origen.
Este módulo no conoce contraseñas ni almacena credenciales.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import re
import secrets
import sqlite3
import unicodedata
import uuid

import operational
import phase2


MANAGERS = {"supervisor", "administrador"}
FIELD_TYPES = {"text", "number", "select", "date", "checkbox"}
MODES = {"lote", "individual", "recepcion"}
MAX_QUANTITY = 1_000_000
MAX_IMPORT_ROWS = 5000


class ApiError(Exception):
    def __init__(self, message, status=400, **details):
        super().__init__(message)
        self.message = message
        self.status = status
        self.details = details


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _fold(value):
    return "".join(c for c in unicodedata.normalize("NFKD", str(value).strip())
                   if not unicodedata.combining(c)).casefold()


def _text(value, label, maximum=500, required=False):
    if value is None:
        value = ""
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        raise ApiError(f"{label}: formato de texto inválido.")
    result = str(value).strip()
    if required and not result:
        raise ApiError(f"{label}: campo obligatorio.")
    if len(result) > maximum or any(ord(c) < 32 and c not in "\n\r\t" for c in result):
        raise ApiError(f"{label}: longitud o contenido inválido (máximo {maximum}).")
    return result


def _integer(value, label, minimum=1, maximum=MAX_QUANTITY):
    if isinstance(value, bool):
        raise ApiError(f"{label}: introduce un número entero.")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ApiError(f"{label}: introduce un número entero.") from None
    if not number.is_finite():
        raise ApiError(f"{label}: introduce un número entero.")
    # Comparar límites antes de convertir evita materializar exponentes enormes.
    if not Decimal(minimum) <= number <= Decimal(maximum):
        raise ApiError(f"{label}: debe estar entre {minimum} y {maximum}.")
    if number != number.to_integral_value():
        raise ApiError(f"{label}: introduce un número entero.")
    integer = int(number)
    return integer


def _date(value, label="Fecha de trabajo"):
    text = str(value or "")
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            raise ValueError()
        date.fromisoformat(text)
    except ValueError:
        raise ApiError(f"{label}: introduce una fecha válida (AAAA-MM-DD).") from None
    return text


def _manager(user):
    if user.get("role") not in MANAGERS:
        raise ApiError("Esta operación requiere supervisor o administrador.", 403)


def _writer(user):
    if user.get("role") == "visitante":
        raise ApiError("La cuenta visitante tiene acceso de solo lectura.", 403)


@contextmanager
def _transaction(db):
    nested = db.in_transaction
    token = "sp_" + secrets.token_hex(6)
    db.execute(f"SAVEPOINT {token}" if nested else "BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        if nested:
            db.execute(f"ROLLBACK TO {token}")
            db.execute(f"RELEASE {token}")
        else:
            db.execute("ROLLBACK")
        raise
    else:
        db.execute(f"RELEASE {token}" if nested else "COMMIT")


def _field(key, label, type_="text", required=True, options=None, source=None, **kw):
    result = {"key": key, "label": label, "type": type_, "required": required}
    if options is not None:
        result["options"] = options
    if source:
        result["source"] = source
    result.update(kw)
    return result


def _default_activities():
    voltage = lambda required=True: _field("voltaje", "Voltaje", "select", required, source="voltajes")
    sap = lambda required=False: _field("sap", "Código SAP", required=required)
    brand = lambda: _field("marca", "Marca / modelo")
    serial = lambda: _field("serie", "Serie del medidor", maximum=60)
    classification = lambda required=False: _field("clasificacion", "Nuevo / recuperado", "select", required, ["Nuevo", "Recuperado"])
    notes = lambda: _field("observaciones", "Observaciones", required=False, maximum=1500)
    return [
        {"id": "limpieza", "name": "Limpieza o recuperación de medidores", "mode": "lote", "unit": "medidores",
         "fields": [voltage(), _field("tiempo_minutos", "Tiempo total del lote (min)", "number", min=0.01),
                    _field("condicion_visual", "Condición visual", "select", True, ["Bueno", "Regular", "Malo"]),
                    sap(), classification(), notes()]},
        {"id": "revision", "name": "Revisión técnica", "mode": "individual", "unit": "revisiones",
         "fields": [serial(), brand(), voltage(), sap(),
                    _field("condicion", "Condición encontrada", "select", source="condiciones"), classification(),
                    _field("resultado", "Resultado de reutilización", "select", False, ["Apto", "No apto", "Pendiente"]), notes()]},
        {"id": "configuracion", "name": "Configuración de medidores", "mode": "lote", "unit": "medidores",
         "fields": [_field("tipo_configuracion", "Tipo de configuración", "select", True, ["Prepago", "Industrial", "Colector"]),
                    sap(True), brand(), voltage(False), notes()]},
        {"id": "sellado", "name": "Sellado de medidores", "mode": "individual", "unit": "medidores",
         "fields": [serial(), sap(True), brand(), voltage(False), classification(True), notes()]},
        {"id": "asignacion", "name": "Asignación de medidores y sellos", "mode": "lote", "unit": "unidades",
         "fields": [_field("tipo_articulo", "Tipo de artículo", "select", True, ["Medidor", "Sello"]),
                    sap(True), _field("destino", "Destinatario / destino"), notes()]},
        {"id": "recepcion", "name": "Recepción de medidores nuevos", "mode": "recepcion", "unit": "medidores",
         "fields": [sap(True), _field("numero_orden", "Número de orden"), _field("proceso", "Proceso de recepción"),
                    brand(), _field("cantidad_esperada", "Cantidad total esperada", "number", False, min=0, integer=True), notes()]},
    ]


def init_schema(db):
    """Idempotente. No elimina ni modifica revisiones ni credenciales legado."""
    db.executescript("""
        CREATE TABLE IF NOT EXISTS production_meta (
            key TEXT PRIMARY KEY, value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS activities (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, mode TEXT NOT NULL,
            unit TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
            current_version INTEGER NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS activity_versions (
            activity_id TEXT NOT NULL REFERENCES activities(id), version INTEGER NOT NULL,
            name TEXT NOT NULL, mode TEXT NOT NULL, unit TEXT NOT NULL,
            fields_json TEXT NOT NULL, created_at TEXT NOT NULL,
            PRIMARY KEY(activity_id,version)
        );
        CREATE TABLE IF NOT EXISTS user_activities (
            user_id INTEGER NOT NULL REFERENCES users(id), activity_id TEXT NOT NULL REFERENCES activities(id),
            enabled INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL,
            PRIMARY KEY(user_id,activity_id)
        );
        CREATE TABLE IF NOT EXISTS sap_catalog (
            code TEXT PRIMARY KEY, voltage TEXT NOT NULL DEFAULT '',
            classification TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS production_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, legacy_id INTEGER UNIQUE,
            activity_id TEXT NOT NULL REFERENCES activities(id), activity_version INTEGER NOT NULL,
            work_date TEXT NOT NULL, responsible_id INTEGER NOT NULL REFERENCES users(id),
            recorded_by INTEGER NOT NULL REFERENCES users(id), quantity INTEGER NOT NULL CHECK(quantity>0),
            unit TEXT NOT NULL, data_json TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'valido' CHECK(state IN ('valido','anulado')),
            revision INTEGER NOT NULL DEFAULT 1, operation_id TEXT UNIQUE,
            request_json TEXT, import_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY(activity_id,activity_version) REFERENCES activity_versions(activity_id,version)
        );
        CREATE INDEX IF NOT EXISTS idx_events_responsible_date ON production_events(responsible_id,work_date);
        CREATE INDEX IF NOT EXISTS idx_events_activity_date ON production_events(activity_id,work_date);
        CREATE INDEX IF NOT EXISTS idx_events_import ON production_events(import_id);
        CREATE TABLE IF NOT EXISTS audit_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id INTEGER REFERENCES users(id),
            entity TEXT NOT NULL, entity_id TEXT NOT NULL, action TEXT NOT NULL,
            before_json TEXT, after_json TEXT, reason TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS production_goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, responsible_id INTEGER NOT NULL REFERENCES users(id),
            activity_id TEXT NOT NULL REFERENCES activities(id), start_date TEXT NOT NULL,
            end_date TEXT NOT NULL, target INTEGER NOT NULL CHECK(target>0), unit TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1, created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS import_jobs (
            id TEXT PRIMARY KEY, actor_id INTEGER NOT NULL REFERENCES users(id),
            activity_id TEXT NOT NULL REFERENCES activities(id), filename TEXT NOT NULL,
            fingerprint TEXT NOT NULL, rows_json TEXT NOT NULL, status TEXT NOT NULL,
            result_json TEXT, created_at TEXT NOT NULL, confirmed_at TEXT,
            UNIQUE(activity_id,fingerprint)
        );
    """)
    with _transaction(db):
        if not db.execute("SELECT 1 FROM production_meta WHERE key='initial_activities'").fetchone():
            for activity in _default_activities():
                db.execute("INSERT INTO activities(id,name,mode,unit,current_version,created_at) VALUES(?,?,?,?,1,?)",
                           (activity["id"], activity["name"], activity["mode"], activity["unit"], now()))
                db.execute("INSERT INTO activity_versions(activity_id,version,name,mode,unit,fields_json,created_at) VALUES(?,1,?,?,?,?,?)",
                           (activity["id"], activity["name"], activity["mode"], activity["unit"], _json(activity["fields"]), now()))
            db.execute("INSERT INTO sap_catalog(code,voltage,classification,updated_at) VALUES('1003913','240V','Recuperado',?)", (now(),))
            db.execute("INSERT INTO production_meta VALUES('initial_activities','1')")
        # Reconcilia también filas que un proceso legado hubiera añadido después
        # de la primera migración. No reimporta ni sobrescribe eventos corregidos.
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='records'").fetchone():
            legacy_rows = db.execute("""SELECT r.* FROM records r WHERE NOT EXISTS
                (SELECT 1 FROM production_events e WHERE e.legacy_id=r.id) ORDER BY r.id""").fetchall()
            for row in legacy_rows:
                data = {"serie": row["meter"], "marca": row["brand"], "voltaje": row["voltage"],
                        "condicion": row["condition"], "observaciones": row["notes"], "sap": ""}
                preferred_id = None if db.execute("SELECT 1 FROM production_events WHERE id=?", (row["id"],)).fetchone() else row["id"]
                operation_id = "legacy:" + str(row["id"])
                if db.execute("SELECT 1 FROM production_events WHERE operation_id=?", (operation_id,)).fetchone():
                    operation_id += ":" + uuid.uuid4().hex
                db.execute("""INSERT INTO production_events
                    (id,legacy_id,activity_id,activity_version,work_date,responsible_id,recorded_by,
                     quantity,unit,data_json,revision,operation_id,created_at,updated_at)
                    VALUES(?,?,'revision',1,?,?,?,1,'revisiones',?,?,?,?,?)""",
                           (preferred_id, row["id"], row["work_date"], row["user_id"], row["user_id"], _json(data),
                            row["revision"], operation_id, row["created_at"], row["created_at"]))
        db.execute("INSERT OR IGNORE INTO production_meta VALUES('legacy_records_migrated',?)", (now(),))
        if not db.execute("SELECT 1 FROM production_meta WHERE key='legacy_assignments_migrated'").fetchone():
            user_columns = {r[1] for r in db.execute("PRAGMA table_info(users)")}
            role_sql = "COALESCE(access_role,role)" if "access_role" in user_columns else "role"
            people = db.execute(f"SELECT id FROM users WHERE {role_sql}!='visitante'").fetchall()
            activity_ids = [r[0] for r in db.execute("SELECT id FROM activities")]
            for person in people:
                assign_user(db, person["id"], activity_ids)
            db.execute("INSERT INTO production_meta VALUES('legacy_assignments_migrated',?)", (now(),))
    operational.init_schema(db)


def audit(db, actor, entity, entity_id, action, before=None, after=None, reason=""):
    """El llamador controla la transacción; nunca incluir credenciales."""
    operational.audit(db, actor, entity, entity_id, action, before, after, reason)


def assign_user(db, user_id, activity_ids):
    if not isinstance(activity_ids, list) or len(activity_ids) > 200 or any(not isinstance(x, str) for x in activity_ids):
        raise ApiError("Selecciona una lista válida de actividades.")
    ids = list(dict.fromkeys(activity_ids))
    known = {r[0] for r in db.execute("SELECT id FROM activities")}
    if any(x not in known for x in ids):
        raise ApiError("Una de las actividades seleccionadas no existe.")
    db.execute("UPDATE user_activities SET enabled=0,updated_at=? WHERE user_id=?", (now(), user_id))
    for activity_id in ids:
        db.execute("""INSERT INTO user_activities(user_id,activity_id,enabled,updated_at) VALUES(?,?,1,?)
                      ON CONFLICT(user_id,activity_id) DO UPDATE SET enabled=1,updated_at=excluded.updated_at""",
                   (user_id, activity_id, now()))


def _expanded_fields(db, fields):
    result = []
    for original in fields:
        field = dict(original)
        if field.get("source") in {"voltajes", "condiciones", "marcas"}:
            field["options"] = [r[0] for r in db.execute("SELECT label FROM catalog WHERE kind=? AND active=1 ORDER BY label", (field["source"],))]
        if phase2.enabled(db) and field.get("source") in {"modelos","piezas","puestos","tipos"}:
            field["options"]=[r[0] for r in db.execute("SELECT label FROM p2_catalog WHERE kind=? AND active=1 ORDER BY label",(field["source"],))]
        if field["key"] == "clasificacion" and field["type"] == "select":
            # Las clasificaciones del maestro están abiertas; no son un enum SAP.
            has_configs = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sap_configurations'").fetchone()
            if has_configs:
                field["options"] = list(dict.fromkeys([*field.get("options", []), *[r[0] for r in db.execute("SELECT DISTINCT classification FROM sap_configurations WHERE active=1 AND classification!='' ORDER BY classification")]]))
        result.append(field)
    return result


def _activity(db, activity_id, version=None):
    row = db.execute("SELECT * FROM activities WHERE id=?", (activity_id,)).fetchone()
    if not row:
        raise ApiError("La actividad no existe.", 404)
    selected_version = version if version is not None else row["current_version"]
    definition = db.execute("SELECT * FROM activity_versions WHERE activity_id=? AND version=?", (activity_id, selected_version)).fetchone()
    if not definition:
        raise ApiError("La versión histórica de la actividad no existe.", 409)
    return {"id": row["id"], "name": definition["name"], "mode": definition["mode"], "unit": definition["unit"],
            "active": bool(row["active"]), "version": definition["version"],
            "illustration": (db.execute("SELECT illustration FROM p2_activity_preferences WHERE activity_id=?",(activity_id,)).fetchone() or ["◈"])[0] if phase2.enabled(db) else "◈",
            "fields": _expanded_fields(db, json.loads(definition["fields_json"]))}


def _activities(db, user):
    ids = [r[0] for r in db.execute("SELECT id FROM activities ORDER BY created_at,id")]
    assigned = {r[0] for r in db.execute("SELECT activity_id FROM user_activities WHERE user_id=? AND enabled=1", (user["id"],))}
    historical = {r[0] for r in db.execute("SELECT DISTINCT activity_id FROM production_events WHERE responsible_id=?", (user["id"],))}
    result = []
    for activity_id in ids:
        activity = _activity(db, activity_id)
        if phase2.enabled(db) and user["role"]=="tecnico":
            activity['permissions']=[permission for permission in phase2.PERMISSIONS if phase2.assignment(db,user['id'],activity_id,permission)]
            activity["assigned"] = bool(phase2.assignment(db,user["id"],activity_id))
            if not any(phase2.assignment(db,user["id"],activity_id,perm) for perm in ("ver","capturar","carga_masiva","proponer_baja","panel")):continue
            result.append(activity);continue
        activity["assigned"] = activity_id in assigned or user["role"] in MANAGERS
        if user["role"] == "tecnico" and activity_id not in assigned | historical:
            continue
        if user["role"] == "visitante" and not activity["active"]:
            continue
        result.append(activity)
    return {"activities": result}


def _validate_fields(fields, mode):
    if not isinstance(fields, list) or not 0 <= len(fields) <= 64:
        raise ApiError("La actividad admite hasta 64 campos.")
    clean, keys = [], set()
    for original in fields:
        if not isinstance(original, dict):
            raise ApiError("Definición de campo inválida.")
        key = _text(original.get("key"), "Clave de campo", 40, True)
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", key) or key in keys:
            raise ApiError("Las claves de campos deben ser únicas, con letras minúsculas, números y guion bajo.")
        keys.add(key)
        type_ = original.get("type", "text")
        if type_ not in FIELD_TYPES:
            raise ApiError("Tipo de campo no permitido.")
        field = {"key": key, "label": _text(original.get("label"), "Nombre del campo", 90, True),
                 "type": type_, "required": bool(original.get("required", False))}
        if original.get("source"):
            if original["source"] not in {"voltajes", "condiciones", "marcas", "modelos", "piezas", "puestos", "tipos"} or type_ != "select":
                raise ApiError("Origen de catálogo inválido.")
            field["source"] = original["source"]
        if type_ == "select":
            options = original.get("options", [])
            if not isinstance(options, list) or len(options) > 300:
                raise ApiError("Lista de opciones inválida.")
            field["options"] = list(dict.fromkeys(_text(x, "Opción", 150, True) for x in options))
            if not field["options"] and not field.get("source"):
                raise ApiError("Un campo de selección necesita opciones.")
        if type_ == "number":
            for bound in ("min", "max"):
                if bound in original:
                    try:
                        number = float(original[bound])
                    except (TypeError, ValueError):
                        raise ApiError("Límite numérico inválido.") from None
                    if not math.isfinite(number) or abs(number) > 1e12:
                        raise ApiError("Límite numérico inválido.")
                    field[bound] = number
            if field.get("min", -1e12) > field.get("max", 1e12):
                raise ApiError("El mínimo del campo supera el máximo.")
            field["integer"] = bool(original.get("integer", False))
        if type_ == "text" and "maximum" in original:
            field["maximum"] = _integer(original["maximum"], "Longitud máxima", 1, 2000)
        clean.append(field)
    if mode == "individual":
        serial = next((x for x in clean if x["key"] == "serie"), None)
        if not serial or serial["type"] != "text" or not serial["required"]:
            raise ApiError("Las actividades individuales requieren un campo de texto 'serie' obligatorio.")
    if mode == "recepcion" and not {"numero_orden", "sap"}.issubset(keys):
        raise ApiError("Las recepciones requieren campos numero_orden y sap.")
    return clean


def _save_activity(db, user, data):
    _manager(user)
    existing_id = data.get("id")
    with _transaction(db):
        previous = _activity(db, existing_id) if existing_id else None
        name = _text(data.get("name", previous["name"] if previous else ""), "Nombre de actividad", 120, True)
        mode = data.get("mode", previous["mode"] if previous else "lote")
        if mode not in MODES:
            raise ApiError("Tipo de actividad inválido.")
        if previous and mode != previous["mode"]:
            raise ApiError("El tipo de captura de una actividad existente se conserva. Crea otra actividad para cambiarlo.")
        unit = _text(data.get("unit", previous["unit"] if previous else ""), "Unidad de producción", 40, True)
        fields = _validate_fields(data.get("fields", previous["fields"] if previous else []), mode)
        if phase2.enabled(db):
            keys={field['key'] for field in fields}
            if existing_id!='sellado' and keys & {'sello_1','sello_2'}:raise ApiError('Los sellos físicos se registran únicamente en Sellado de medidores, la actividad unificada.')
            if 'sap' in keys:
                if 'clasificacion' not in keys:fields.append(_field('clasificacion','Valoración','select',False,phase2.VALUATIONS))
                if 'sap_config_id' not in keys:fields.append(_field('sap_config_id','Artículo SAP y valoración',required=False,maximum=160))

        active = bool(data.get("active", previous["active"] if previous else True))
        activity_id = existing_id or "actividad_" + uuid.uuid4().hex[:14]
        version = previous["version"] + 1 if previous else 1
        timestamp = now()
        if previous:
            db.execute("UPDATE activities SET name=?,mode=?,unit=?,active=?,current_version=? WHERE id=?",
                       (name, mode, unit, int(active), version, activity_id))
        else:
            db.execute("INSERT INTO activities(id,name,mode,unit,active,current_version,created_at) VALUES(?,?,?,?,?,?,?)",
                       (activity_id, name, mode, unit, int(active), version, timestamp))
        db.execute("INSERT INTO activity_versions(activity_id,version,name,mode,unit,fields_json,created_at) VALUES(?,?,?,?,?,?,?)",
                   (activity_id, version, name, mode, unit, _json(fields), timestamp))
        if phase2.enabled(db):
            illustration=data.get("illustration",previous.get("illustration","◈") if previous else "◈")
            if illustration not in ["◈","⌕","⇣","⚙","✓"]:raise ApiError("Selecciona una ilustración de la galería.")
            db.execute("INSERT INTO p2_activity_preferences VALUES(?,?) ON CONFLICT(activity_id) DO UPDATE SET illustration=excluded.illustration",(activity_id,illustration))
        result = _activity(db, activity_id)
        audit(db, user, "actividad", activity_id, "versionar" if previous else "crear", previous, result)
    return {"ok": True, "activity": result}


def _save_sap(db, user, data):
    return operational.save_sap(db, user, data)


def _responsible(db, user, payload, activity_id, existing=None):
    requested = payload.get("responsible_id", existing["responsible_id"] if existing else user["id"])
    responsible_id = _integer(requested, "Responsable", 1, 2**63 - 1)
    if phase2.enabled(db) and user["role"] == "tecnico" and responsible_id != user["id"]:
        raise ApiError("Solo puedes registrar tu propia producción.",403)
    if user["role"] == "tecnico":
        # La identidad operativa procede de la sesión, nunca del navegador.
        responsible_id = user["id"]
    person = db.execute("SELECT id,name,active,COALESCE(access_role,role) AS effective_role FROM users WHERE id=?", (responsible_id,)).fetchone()
    if not person or (not person["active"] and not existing):
        raise ApiError("Selecciona un colaborador activo.")
    if person["effective_role"] == "visitante":
        raise ApiError("Una cuenta visitante no puede ser responsable operativo.", 403)
    if person["effective_role"] == "tecnico" and not existing and not phase2.enabled(db):
        assignment = db.execute("SELECT 1 FROM user_activities WHERE user_id=? AND activity_id=? AND enabled=1", (responsible_id, activity_id)).fetchone()
        if not assignment:
            raise ApiError("El colaborador no tiene esta actividad habilitada.", 403)
    if existing and responsible_id != existing["responsible_id"]:
        raise ApiError("La corrección conserva el responsable original. Anula el registro y crea uno nuevo si se atribuyó mal.")
    return responsible_id


def _clean_data(db, activity, raw, existing=None):
    if not isinstance(raw, dict) or len(raw) > 80:
        raise ApiError("Los datos de actividad deben ser un objeto válido.")
    fields = activity["fields"]
    known = {field["key"] for field in fields}
    unknown = set(raw) - known - {"desviacion_pct", "fuera_tolerancia"}
    if unknown:
        raise ApiError("Hay campos que no pertenecen a esta versión de actividad: " + ", ".join(sorted(unknown)[:5]))
    raw = phase2.prepare_sap(db, activity, raw, existing) if phase2.enabled(db) else operational.prepare_sap(db, activity, raw, existing)
    old_data = existing["data"] if existing else {}
    clean = {}
    for field in fields:
        key, kind = field["key"], field["type"]
        value = raw.get(key, "")
        missing = value is None or value == "" or (isinstance(value, str) and not value.strip())
        if missing:
            if field["required"]:
                # En una corrección histórica se conservan ausencias anteriores.
                if not existing or key in old_data and old_data[key] not in ("", None):
                    raise ApiError(f"{field['label']}: campo obligatorio.")
            clean[key] = "" if kind != "checkbox" else False
            continue
        if kind == "text":
            if key in {"serie", "sap", "sello_1", "sello_2"} and not isinstance(value, str):
                raise ApiError(f"{field['label']}: introduce el identificador como texto para conservar ceros iniciales.")
            clean[key] = _text(value, field["label"], int(field.get("maximum", 1500 if key == "observaciones" else 500)))
            if key in {"serie", "sap", "sello_1", "sello_2"} and len(clean[key]) > 60:
                raise ApiError(f"{field['label']}: máximo 60 caracteres.")
        elif kind == "select":
            text = _text(value, field["label"], 150)
            choices = field.get("options", [])
            matching = next((option for option in choices if _fold(option) == _fold(text)), None)
            if matching is None and not (existing and text == old_data.get(key)):
                raise ApiError(f"{field['label']}: selecciona una opción válida.")
            clean[key] = matching if matching is not None else text
        elif kind == "date":
            clean[key] = _date(value, field["label"])
        elif kind == "checkbox":
            if isinstance(value, bool):
                clean[key] = value
            elif _fold(value) in {"si", "true", "1", "yes"}:
                clean[key] = True
            elif _fold(value) in {"no", "false", "0"}:
                clean[key] = False
            else:
                raise ApiError(f"{field['label']}: selecciona Sí o No.")
        elif kind == "number":
            if isinstance(value, bool):
                raise ApiError(f"{field['label']}: número inválido.")
            try:
                number = Decimal(str(value))
            except (InvalidOperation, TypeError, ValueError):
                raise ApiError(f"{field['label']}: número inválido.") from None
            low, high = Decimal(str(field.get("min", 0))), Decimal(str(field.get("max", 1e12)))
            if not number.is_finite() or not low <= number <= high:
                raise ApiError(f"{field['label']}: valor fuera del rango permitido.")
            if field.get("integer") and number != number.to_integral_value():
                raise ApiError(f"{field['label']}: introduce un entero.")
            clean[key] = int(number) if number == number.to_integral_value() else float(number)
    return operational.derive_quality(activity, clean)


EVENT_SELECT = """SELECT e.*, v.name AS activity_name,v.mode AS event_mode,
                    u.name AS responsible_name, c.name AS recorded_by_name, v.fields_json AS version_fields,
                    u.username AS responsible_username,c.username AS recorded_by_username
                  FROM production_events e
                  JOIN activity_versions v ON v.activity_id=e.activity_id AND v.version=e.activity_version
                  JOIN users u ON u.id=e.responsible_id JOIN users c ON c.id=e.recorded_by"""


def _serialize(row, db=None):
    data = json.loads(row["data_json"])
    fields = json.loads(row["version_fields"])
    if db is not None:
        fields = _expanded_fields(db, fields)
    for field in fields:
        if field["type"] == "select" and data.get(field["key"]) not in (None, ""):
            old_value = data[field["key"]]
            if old_value not in field.get("options", []):
                field["options"] = [*field.get("options", []), old_value]
    result = {"id": row["id"], "legacy_id": row["legacy_id"], "activity_id": row["activity_id"],
            "activity_name": row["activity_name"], "activity_version": row["activity_version"],
            "mode": row["event_mode"], "unit": row["unit"], "work_date": row["work_date"],
            "responsible_id": row["responsible_id"], "responsible_name": row["responsible_name"],
            "responsible_username": row["responsible_username"], "recorded_by_username": row["recorded_by_username"],
            "recorded_by": row["recorded_by"], "recorded_by_name": row["recorded_by_name"],
            "quantity": row["quantity"], "data": data, "fields": fields, "state": row["state"],
            "revision": row["revision"], "created_at": row["created_at"], "updated_at": row["updated_at"],
            "import_id": row["import_id"]}
    if db is not None and phase2.enabled(db):
        details=db.execute("SELECT x.*,c.number cycle_number FROM p2_event_details x LEFT JOIN p2_cycles c ON c.id=x.cycle_id WHERE x.event_id=?",(row["id"],)).fetchone()
        result["traceability"]=dict(details) if details else None
    return result


def _event(db, event_id):
    row = db.execute(EVENT_SELECT + " WHERE e.id=?", (event_id,)).fetchone()
    if not row:
        raise ApiError("El registro no existe.", 404)
    return _serialize(row, db)


def _event_permission(user, event):
    _writer(user)
    if user["role"] not in MANAGERS and event["responsible_id"] != user["id"]:
        raise ApiError("No puedes modificar registros de otra persona.", 403)


def _normalized_payload(db, user, payload, existing=None):
    _writer(user)
    activity_id = _text(payload.get("activity_id", existing["activity_id"] if existing else ""), "Actividad", 80, True)
    if existing and activity_id != existing["activity_id"]:
        raise ApiError("La actividad de un registro existente no se cambia.")
    activity = _activity(db, activity_id, existing["activity_version"] if existing else None)
    if not activity["active"] and not existing:
        raise ApiError("La actividad está desactivada para nuevas capturas.", 403)
    responsible = _responsible(db, user, payload, activity_id, existing)
    work_date = _date(payload.get("work_date", existing["work_date"] if existing else ""))
    quantity = _integer(payload.get("quantity", existing["quantity"] if existing else 1), "Cantidad")
    if activity["mode"] == "individual" and quantity != 1:
        raise ApiError("Cada registro individual representa un medidor; la cantidad debe ser 1.")
    event_data = _clean_data(db, activity, payload.get("data", existing["data"] if existing else {}), existing)
    unit = activity["unit"]
    if activity_id == "asignacion":
        unit = "sellos" if _fold(event_data.get("tipo_articulo")) == "sello" else "medidores"
    return {"activity_id": activity_id, "activity_version": activity["version"], "work_date": work_date,
            "responsible_id": responsible, "quantity": quantity, "unit": unit, "data": event_data, "mode": activity["mode"]}


def _request_identity(user, payload):
    # Mantener el payload original permite reconocer un reenvío aunque cambie el formulario.
    return _json({"actor": user["id"], "activity_id": payload.get("activity_id"),
                  "work_date": payload.get("work_date"), "responsible_id": str(payload.get("responsible_id", user["id"])),
                  "quantity": str(payload.get("quantity", 1)), "data": payload.get("data", {})})


def _prior_events(db, activity_id, serial, exclude=None):
    params = [activity_id, serial]
    where = " WHERE e.activity_id=? AND json_extract(e.data_json,'$.serie')=? AND e.state='valido'"
    if exclude is not None:
        where += " AND e.id!=?"
        params.append(exclude)
    return [_serialize(row, db) for row in db.execute(EVENT_SELECT + where + " ORDER BY e.work_date DESC,e.id DESC LIMIT 50", params)]


def _confirmation_error(previous, work_date, user):
    safe = []
    for event in previous[:10]:
        if user["role"] in MANAGERS or event["responsible_id"] == user["id"]:
            safe.append(event)
        else:
            safe.append({"work_date": event["work_date"], "activity_name": event["activity_name"],
                         "data": {k: event["data"].get(k, "") for k in ("serie", "voltaje", "condicion")},
                         "responsible_name": "Otro colaborador", "revision": event["revision"]})
    same_day = any(event["work_date"] == work_date for event in previous)
    message = "Este medidor ya tiene registros en la misma fecha. Confirma la nueva revisión." if same_day else "Este medidor ya tiene historial. Confirma el reingreso para crear otro registro."
    return ApiError(message, 409, needs_confirmation=True, same_day=same_day, previous=safe)


def _save_event(db, user, payload, import_id=None):
    _writer(user)
    operation_id = _text(payload.get("operation_id"), "Identificador de operación", 160, True)
    if operation_id.startswith("legacy:") or operation_id.startswith("import:") and not import_id:
        raise ApiError("El identificador usa un prefijo reservado del sistema.")
    identity = _request_identity(user, payload)
    existing_operation = db.execute("SELECT id,request_json FROM production_events WHERE operation_id=?", (operation_id,)).fetchone()
    if existing_operation:
        if existing_operation["request_json"] != identity:
            raise ApiError("El identificador de operación ya fue utilizado con otros datos.", 409)
        return {"ok": True, "record": _event(db, existing_operation["id"]), "already_saved": True}
    normalized = _normalized_payload(db, user, payload)
    previous = []
    if phase2.enabled(db):phase2.before_event(db,user,payload,normalized,bulk=bool(import_id))
    if not phase2.enabled(db) and normalized["mode"] == "individual":
        previous = _prior_events(db, normalized["activity_id"], normalized["data"]["serie"])
        if previous and payload.get("confirm_reentry") is not True:
            raise _confirmation_error(previous, normalized["work_date"], user)
    revision = max((row[0] for row in db.execute("""SELECT revision FROM production_events
                    WHERE activity_id=? AND json_extract(data_json,'$.serie')=?""",
                    (normalized["activity_id"], normalized["data"].get("serie", "")))), default=0) + 1 if normalized["mode"] == "individual" else 1
    timestamp = now()
    cursor = db.execute("""INSERT INTO production_events(activity_id,activity_version,work_date,responsible_id,
                         recorded_by,quantity,unit,data_json,revision,operation_id,request_json,import_id,created_at,updated_at)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (normalized["activity_id"], normalized["activity_version"], normalized["work_date"],
                         normalized["responsible_id"], user["id"], normalized["quantity"], normalized["unit"],
                         _json(normalized["data"]), revision, operation_id, identity, import_id, timestamp, timestamp))
    event = _event(db, cursor.lastrowid)
    operational.attach_receipt(db, user, event)
    if phase2.enabled(db):
        phase2.after_event(db,user,payload,event)
        event=_event(db,event["id"])
    audit(db, user, "registro", event["id"], "importar" if import_id else "crear", after=event)
    return {"ok": True, "record": event}


def _correct_event(db, user, event_id, payload):
    reason = _text(payload.get("reason"), "Motivo de corrección", 1500, True)
    with _transaction(db):
        existing = _event(db, event_id)
        _event_permission(user, existing)
        operational.assert_receipt_open(db, existing)
        if existing["state"] != "valido":
            raise ApiError("Restaura el registro anulado antes de corregirlo.", 409)
        # Conserva actividad, versión y responsable originales.
        if "data" in payload and not isinstance(payload["data"], dict):
            raise ApiError("Los datos de actividad son inválidos.")
        merged = dict(payload)
        merged["data"] = {**existing["data"], **payload.get("data", {})}
        normalized = _normalized_payload(db, user, merged, existing)
        if phase2.enabled(db):phase2.before_event(db,user,merged,normalized,existing)
        if normalized["mode"] == "individual":
            previous = _prior_events(db, existing["activity_id"], normalized["data"]["serie"], existing["id"])
            if previous and normalized["data"].get("serie") != existing["data"].get("serie") and payload.get("confirm_reentry") is not True:
                raise _confirmation_error(previous, normalized["work_date"], user)
        db.execute("UPDATE production_events SET work_date=?,quantity=?,unit=?,data_json=?,updated_at=? WHERE id=?",
                   (normalized["work_date"], normalized["quantity"], normalized["unit"], _json(normalized["data"]), now(), event_id))
        if phase2.enabled(db) and payload.get("duplicate_note"):
            db.execute("UPDATE p2_event_details SET duplicate_note=? WHERE event_id=?",(_text(payload["duplicate_note"],"Justificación",1500,True),event_id))
        result = _event(db, event_id)
        operational.attach_receipt(db, user, result, existing=existing)
        audit(db, user, "registro", event_id, "corregir", existing, result, reason)
    return {"ok": True, "record": result}


def _state_event(db, user, event_id, payload, restore=False):
    reason = _text(payload.get("reason"), "Motivo", 1500, True)
    with _transaction(db):
        existing = _event(db, event_id)
        _event_permission(user, existing)
        operational.assert_receipt_open(db, existing)
        if restore:
            _manager(user)
        state = "valido" if restore else "anulado"
        if existing["state"] == state:
            return {"ok": True, "record": existing, "already_saved": True}
        db.execute("UPDATE production_events SET state=?,updated_at=? WHERE id=?", (state, now(), event_id))
        result = _event(db, event_id)
        audit(db, user, "registro", event_id, "restaurar" if restore else "anular", existing, result, reason)
    return {"ok": True, "record": result}


def _filters(user, query, allow_visitor=False):
    if user["role"] == "visitante" and not allow_visitor:
        raise ApiError("La cuenta visitante no tiene acceso al detalle de registros.", 403)
    if user["role"] == "visitante" and query.get("meter"):
        raise ApiError("El visitante consulta estadísticas agregadas, sin búsquedas por medidor.", 403)
    if user["role"] == "visitante" and query.get("failure"):
        raise ApiError("El visitante consulta fallos agregados, sin buscar texto operativo.", 403)
    if user["role"] == "visitante" and query.get("search"):
        raise ApiError("El visitante consulta agregados, sin búsquedas por datos personales u operativos.", 403)
    _detail_metric(query)
    if query.get("failure"):
        _text(query["failure"], "Fallo informado", 1500, True)
    if query.get("search"):
        _text(query["search"], "Buscar registros", 200, True)
    if isinstance(query.get("voltage_missing"), bool) or query.get("voltage_missing") not in (None, "", "0", "1", 0, 1):
        raise ApiError("El filtro de voltaje sin informar debe ser 0 o 1.")
    clauses, values = [], []
    if user["role"] == "tecnico":
        clauses.append("e.responsible_id=?")
        values.append(user["id"])
        if query.get("responsible_id") and str(query["responsible_id"]) != str(user["id"]):
            raise ApiError("Solo puedes consultar tu propia producción.", 403)
    elif query.get("responsible_id"):
        if user["role"] == "visitante":
            raise ApiError("El visitante consulta estadísticas agregadas, sin filtros personales.", 403)
        clauses.append("e.responsible_id=?")
        values.append(_integer(query["responsible_id"], "Responsable", 1, 2**63 - 1))
    if query.get("desde"):
        clauses.append("e.work_date>=?")
        values.append(_date(query["desde"], "Desde"))
    if query.get("hasta"):
        clauses.append("e.work_date<=?")
        values.append(_date(query["hasta"], "Hasta"))
    if query.get("desde") and query.get("hasta") and query["desde"] > query["hasta"]:
        raise ApiError("La fecha Desde no puede ser posterior a Hasta.")
    if query.get("activity_id"):
        clauses.append("e.activity_id=?")
        values.append(_text(query["activity_id"], "Actividad", 80))
    if query.get("activity_name"):
        clauses.append("EXISTS(SELECT 1 FROM activity_versions av WHERE av.activity_id=e.activity_id AND av.version=e.activity_version AND av.name=?)")
        values.append(_text(query["activity_name"], "Nombre histórico de actividad", 150, True))
    if query.get("unit"):
        clauses.append("e.unit=?")
        values.append(_text(query["unit"], "Unidad", 120, True))
    if str(query.get("voltage_missing", "")) == "1":
        clauses.append("COALESCE(json_extract(e.data_json,'$.voltaje'),'')=''")
    for param, field in (("sap", "sap"), ("voltage", "voltaje"), ("condition", "condicion"), ("brand", "marca"), ("model", "modelo"), ("valuation", "clasificacion"), ("warehouse", "almacen")):
        if query.get(param):
            clauses.append(f"json_extract(e.data_json,'$.{field}')=?")
            values.append(_text(query[param], param, 150))
    if query.get("meter"):
        meter = _text(query["meter"], "Serie", 60).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        clauses.append("json_extract(e.data_json,'$.serie') LIKE ? ESCAPE '\\'")
        values.append("%" + meter + "%")
    state = query.get("state", "valido")
    if state not in {"valido", "anulado", "all"}:
        raise ApiError("Estado de registro inválido.")
    if state != "all":
        clauses.append("e.state=?")
        values.append(state)
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", values


def _events(db, user, query, allow_visitor=False):
    where, params = _filters(user, query, allow_visitor)
    rows = [_serialize(row, db) for row in db.execute(EVENT_SELECT + where + " ORDER BY e.work_date DESC,e.id DESC", params)]
    rows = _detail_selection(rows, query)
    if query.get("search"):
        needle = _fold(_text(query["search"], "Buscar registros", 200, True))
        def searchable(row):
            values = [row[key] for key in ("id", "work_date", "activity_name", "responsible_name", "responsible_username",
                      "recorded_by_name", "recorded_by_username", "quantity", "unit", "state")]
            values.extend(row["data"].values())
            return _fold(" ".join(str(value) for value in values if value is not None))
        rows = [row for row in rows if needle in searchable(row)]
    return rows


DETAIL_METRICS = {
    "events": ("Registros de actividad", "registros de actividad, no medidores físicos únicos"),
    "reviews": ("Revisiones realizadas", "registros de revisión técnica"),
    "approved": ("Revisiones aprobadas", "revisiones con resultado Apto"),
    "rejected": ("Revisiones rechazadas", "revisiones con resultado No apto"),
    "pending": ("Revisiones pendientes", "revisiones con resultado Pendiente"),
    "without_result": ("Revisiones sin resultado", "revisiones cuyo resultado no es Apto, No apto ni Pendiente"),
    "evaluated": ("Revisiones evaluadas", "revisiones concluidas: Apto + No apto"),
    "unfinished": ("Revisiones sin concluir", "revisiones pendientes o sin resultado reconocido"),
    "identified": ("Series identificadas", "una fila representativa por serie identificada en el alcance; se muestra su registro más reciente"),
    "reentries": ("Reingresos de revisión", "revisiones adicionales después de la primera de cada serie dentro del alcance seleccionado"),
    "calibrations": ("Mediciones de calibración", "revisiones con referencia, medición y tolerancia válidas"),
    "outside_tolerance": ("Fuera de tolerancia", "revisiones cuya desviación absoluta supera la tolerancia registrada"),
    "failures": ("Revisiones con fallo informado", "revisiones con un fallo registrado; no incluye las indicaciones Sin fallo o No aplica"),
}


def _detail_metric(query):
    metric = _text(query.get("metric") or "events", "Indicador", 60, True)
    if metric not in DETAIL_METRICS:
        raise ApiError("Selecciona un indicador válido para consultar sus datos.")
    return metric


def _detail_selection(rows, query):
    """La misma selección alimenta pantalla, paginación y archivos descargables.

    Normalizar en Python mantiene exactamente las reglas de calidad existentes,
    también con resultados históricos que contengan mayúsculas o acentos.
    """
    metric = _detail_metric(query)
    if query.get("failure"):
        from analytics import _failure_label
        failure = _text(query["failure"], "Fallo informado", 1500, True)
        rows = [row for row in rows if row["activity_id"] == "revision" and _failure_label(row["data"]) == failure]
    if metric == "events":
        return rows
    if metric == "identified":
        seen, selected = set(), []
        for row in rows:  # El origen está ordenado por fecha e ID descendentes.
            serial = row["data"].get("serie")
            if serial and serial not in seen:
                seen.add(serial)
                selected.append(row)
        return selected
    rows = [row for row in rows if row["activity_id"] == "revision"]
    if metric == "reviews":
        return rows
    if metric == "failures":
        from analytics import _failure_label
        return [row for row in rows if _failure_label(row["data"])]
    if metric == "reentries":
        seen, selected_ids = set(), set()
        for row in reversed(rows):
            serial = row["data"].get("serie")
            if not serial:
                continue
            if serial in seen:
                selected_ids.add(row["id"])
            seen.add(serial)
        return [row for row in rows if row["id"] in selected_ids]
    if metric in {"calibrations", "outside_tolerance"}:
        from analytics import _calibration
        return [row for row in rows if (value := _calibration(row["data"])) is not None
                and (metric == "calibrations" or value[1])]
    results = {"approved": {"apto", "reutilizable"}, "rejected": {"no apto", "no reutilizable"}, "pending": {"pendiente"},
               "evaluated": {"apto", "no apto", "reutilizable", "no reutilizable"}}
    if metric in results:
        return [row for row in rows if _fold(row["data"].get("resultado", "")) in results[metric]]
    excluded = {"apto", "no apto", "reutilizable", "no reutilizable", "pendiente"} if metric == "without_result" else {"apto", "no apto", "reutilizable", "no reutilizable"}
    return [row for row in rows if _fold(row["data"].get("resultado", "")) not in excluded]


def _event_page(rows, query):
    total = len(rows)
    page_size = _integer(query.get("page_size", 20), "Tamaño de página", 1, 200)
    pages = max(1, math.ceil(total / page_size))
    page = min(_integer(query.get("page", 1), "Página", 1, 1_000_000), pages)
    return {"records": rows[(page - 1) * page_size:page * page_size], "total": total,
            "page": page, "pages": pages, "page_size": page_size}


def _detail(db, user, query):
    from analytics import _quality_summary
    rows = _events(db, user, query, allow_visitor=True)
    metric = _detail_metric(query)
    totals, activities, days = Counter(), Counter(), Counter()
    for row in rows:
        totals[row["unit"]] += row["quantity"]
        activities[(row["activity_name"], row["unit"])] += row["quantity"]
        days[row["work_date"]] += 1
    result = _event_page(rows, query)
    detail_allowed = user["role"] != "visitante"
    if not detail_allowed:
        result["records"] = []
    return {**result, "detail_allowed": detail_allowed, "metric": metric,
            "metric_label": DETAIL_METRICS[metric][0], "count_scope": DETAIL_METRICS[metric][1],
            "summary": {"records": len(rows), "totals_by_unit": dict(totals),
                        "quality": _quality_summary([row for row in rows if row["activity_id"] == "revision"])},
            "breakdown": {"by_activity": [{"label": name, "unit": unit, "value": value}
                                          for (name, unit), value in activities.most_common()],
                          "by_day": [{"label": day, "value": value} for day, value in sorted(days.items())]}}


def _list_events(db, user, query):
    if _detail_metric(query) != "events" or query.get("failure") or query.get("search"):
        return _event_page(_events(db, user, query), query)
    where, params = _filters(user, query)
    total = db.execute("SELECT count(*) FROM production_events e" + where, params).fetchone()[0]
    page_size = _integer(query.get("page_size", 20), "Tamaño de página", 1, 200)
    pages = max(1, math.ceil(total / page_size))
    page = min(_integer(query.get("page", 1), "Página", 1, 1_000_000), pages)
    rows = db.execute(EVENT_SELECT + where + " ORDER BY e.work_date DESC,e.id DESC LIMIT ? OFFSET ?",
                      (*params, page_size, (page - 1) * page_size)).fetchall()
    return {"records": [_serialize(row, db) for row in rows], "total": total, "page": page, "pages": pages,
            "page_size": page_size}


def _history(db, user, query):
    if user["role"] == "visitante":
        raise ApiError("La cuenta visitante no tiene acceso al historial individual.", 403)
    serial = _text(query.get("medidor"), "Serie del medidor", 60, True)
    clauses = ["json_extract(e.data_json,'$.serie')=?"]
    params = [serial]
    if user["role"] == "tecnico":
        clauses.append("e.responsible_id=?")
        params.append(user["id"])
    rows = [_serialize(row, db) for row in db.execute(EVENT_SELECT + " WHERE " + " AND ".join(clauses) + " ORDER BY e.work_date DESC,e.id DESC", params)]
    return {"meter": serial, "count": len(rows), "records": rows}


def _receipts(db, user, query=None, allow_visitor=False):
    # El maestro conserva cantidades y órdenes todavía sin entregas. El balance
    # global no se reduce al aporte personal ni a las entregas del período.
    return operational.receipts(db, user, query, allow_visitor=allow_visitor)


def _goals(db, user, query=None, allow_visitor=False):
    if user["role"] == "visitante" and not allow_visitor:
        raise ApiError("La cuenta visitante no consulta metas individuales.", 403)
    clauses, params = ["g.active=1"], []
    if user["role"] == "tecnico":
        clauses.append("g.responsible_id=?")
        params.append(user["id"])
    q = query or {}
    if q.get("responsible_id") and user["role"] in MANAGERS:
        clauses.append("g.responsible_id=?")
        params.append(_integer(q["responsible_id"], "Responsable", 1, 2**63 - 1))
    if q.get("activity_id"):
        clauses.append("g.activity_id=?")
        params.append(q["activity_id"])
    rows = db.execute("""SELECT g.*,u.name AS responsible_name,a.name AS activity_name FROM production_goals g
                         JOIN users u ON u.id=g.responsible_id JOIN activities a ON a.id=g.activity_id WHERE """ + " AND ".join(clauses) + " ORDER BY g.end_date DESC,g.id DESC", params).fetchall()
    today = datetime.now(timezone(timedelta(hours=-4))).date().isoformat()
    result = []
    for row in rows:
        if q.get("desde") and row["end_date"] < _date(q["desde"], "Desde"):
            continue
        if q.get("hasta") and row["start_date"] > _date(q["hasta"], "Hasta"):
            continue
        produced = db.execute("""SELECT COALESCE(sum(quantity),0) FROM production_events
                WHERE responsible_id=? AND activity_id=? AND unit=? AND state='valido' AND work_date>=? AND work_date<=?""",
                (row["responsible_id"], row["activity_id"], row["unit"], row["start_date"], row["end_date"])).fetchone()[0]
        state = "cumplida" if produced >= row["target"] else "vencida" if today > row["end_date"] else "pendiente" if today < row["start_date"] else "en_progreso"
        result.append({"id": row["id"], "responsible_id": row["responsible_id"], "responsible_name": row["responsible_name"],
                       "activity_id": row["activity_id"], "activity_name": row["activity_name"], "start_date": row["start_date"],
                       "end_date": row["end_date"], "target": row["target"], "produced": produced,
                       "pct": round(produced / row["target"] * 100, 1), "pending": max(0, row["target"] - produced),
                       "state": state, "unit": row["unit"]})
    return result


def _save_goal(db, user, data):
    _manager(user)
    activity = _activity(db, _text(data.get("activity_id"), "Actividad", 80, True))
    if not activity["active"]:
        raise ApiError("La actividad de la meta debe estar activa.")
    responsible = _responsible(db, user, data, activity["id"])
    start = _date(data.get("start_date"), "Inicio de meta")
    end = _date(data.get("end_date"), "Fin de meta")
    if start > end:
        raise ApiError("El inicio de la meta no puede ser posterior al final.")
    target = _integer(data.get("target"), "Cantidad objetivo")
    unit = activity["unit"]
    if activity["id"] == "asignacion":
        unit = data.get("unit")
        if unit not in {"medidores", "sellos"}:
            raise ApiError("Para metas de asignación indica la unidad medidores o sellos.")
    with _transaction(db):
        cursor = db.execute("""INSERT INTO production_goals(responsible_id,activity_id,start_date,end_date,target,unit,created_by,created_at)
                              VALUES(?,?,?,?,?,?,?,?)""", (responsible, activity["id"], start, end, target, unit, user["id"], now()))
        audit(db, user, "meta", cursor.lastrowid, "crear", after={"responsible_id": responsible, "activity_id": activity["id"],
              "start_date": start, "end_date": end, "target": target, "unit": unit})
    return {"ok": True, "id": cursor.lastrowid}


def _dashboard_trend(events, query):
    """Curvas temporales independientes por actividad y unidad, con ceros reales."""
    # Importación diferida: analytics reutiliza los permisos de production.
    from analytics import _bucket, _buckets, _granularity
    granularity = _granularity({"granularity": query.get("granularity") or "semanal"})
    today = datetime.now(timezone(timedelta(hours=-4))).date().isoformat()
    first = date.fromisoformat(query.get("desde") or min((e["work_date"] for e in events), default=query.get("hasta") or today))
    last = date.fromisoformat(query.get("hasta") or max((e["work_date"] for e in events), default=first.isoformat()))
    # Un solo extremo abierto puede quedar fuera del último dato disponible.
    # En ese caso el rango vacío se representa en la fecha pedida, no al revés.
    if first > last:
        if query.get("desde") and query.get("hasta"):
            raise ApiError("La fecha Desde no puede ser posterior a Hasta.")
        first = last = first if query.get("desde") else last
    buckets = _buckets(first, last, granularity)
    grouped, counts = {}, Counter()
    for event in events:
        key = (event["activity_id"], event["unit"])
        item = grouped.setdefault(key, {"activity_name": event["activity_name"], "quantities": Counter(), "records": Counter()})
        bucket = _bucket(date.fromisoformat(event["work_date"]), granularity)[0]
        item["quantities"][bucket] += event["quantity"]
        item["records"][bucket] += 1
        counts[bucket] += 1
    series = []
    for (activity_id, unit), item in sorted(grouped.items()):
        points = [{**bucket, "date": bucket["from"], "value": item["quantities"][bucket["label"]],
                   "records": item["records"][bucket["label"]]} for bucket in buckets]
        series.append({"id": f"{activity_id}:{unit}", "activity_id": activity_id,
                       "activity_name": item["activity_name"], "unit": unit,
                       "total": sum(point["value"] for point in points), "points": points})
    return {"granularity": granularity, "from": first.isoformat(), "to": last.isoformat(), "series": series,
            "records": [{**bucket, "date": bucket["from"], "value": counts[bucket["label"]]} for bucket in buckets]}


def _dashboard(db, user, query):
    from analytics import _quality_summary
    valid_query = {**query, "state": "valido"}
    events = _events(db, user, valid_query, allow_visitor=True)
    reviews = [event for event in events if event["activity_id"] == "revision"]
    unique_reviews = {event["data"].get("serie") for event in reviews if event["data"].get("serie")}
    identified = {event["data"].get("serie") for event in events if event["data"].get("serie")}
    totals = Counter()
    by_activity, by_voltage, by_day, by_person = Counter(), Counter(), Counter(), Counter()
    by_person_ids = {}
    duration = Decimal(0)
    duration_qty = 0
    for event in events:
        totals[event["unit"]] += event["quantity"]
        by_activity[(event["activity_name"], event["unit"])] += event["quantity"]
        by_voltage[event["data"].get("voltaje") or "Sin voltaje"] += 1
        by_day[event["work_date"]] += 1
        person_label = f"{event['responsible_name']} ({event['responsible_username']})"
        by_person[person_label] += 1
        by_person_ids[person_label] = event["responsible_id"]
        if event["data"].get("tiempo_minutos") not in ("", None):
            duration += Decimal(str(event["data"]["tiempo_minutos"]))
            duration_qty += event["quantity"]
    goals = _goals(db, user, query, allow_visitor=True)
    goal_states = Counter(goal["state"] for goal in goals)
    receipts = _receipts(db, user, query, allow_visitor=True)
    aggregate = lambda counter: [{"label": label, "value": value} for label, value in counter.most_common()]
    return {"event_count": len(events), "review_count": len(reviews), "identified_unique": len(identified),
            "reentries": sum(bool(event["data"].get("serie")) for event in reviews) - len(unique_reviews), "totals_by_unit": dict(totals),
            "by_activity": [{"label": name, "value": value, "unit": unit} for (name, unit), value in by_activity.most_common()],
            "by_voltage": aggregate(by_voltage), "by_day": [{"label": day, "value": value} for day, value in sorted(by_day.items())],
            "by_collaborator": [] if user["role"] == "visitante" else [
                {"label": label, "value": value, "responsible_id": by_person_ids[label]}
                for label, value in by_person.most_common()],
            "receipts_pending": sum(1 for receipt in receipts if receipt["pending"] is None or receipt["pending"] > 0),
            "receipts_pending_scope": "historial al corte",
            "goals": [] if user["role"] == "visitante" else goals,
            "goals_summary": {"total": len(goals), "cumplidas": goal_states["cumplida"], "vencidas": goal_states["vencida"],
                              "en_progreso": goal_states["en_progreso"], "pendientes": goal_states["pendiente"]},
            "time_minutes": float(duration), "minutes_per_unit": round(float(duration) / duration_qty, 2) if duration_qty else None,
            "chart_unit": "registros", "reentries_scope": "revisiones adicionales dentro del período seleccionado",
            "summary_quality": _quality_summary(reviews), "trend": _dashboard_trend(events, query),
            "receipt_summary": operational.receipt_summary(receipts),
            "batch_progress": [] if user["role"] == "visitante" else receipts,
            "updated_at": now()}


def _row_payload(db, actor, activity_id, row):
    if not isinstance(row, dict):
        raise ApiError("La fila no tiene columnas válidas.")
    code = _text(row.get("responsible", row.get("codigo_empleado", row.get("username", ""))), "Código de empleado", 60, True)
    person = db.execute("SELECT id FROM users WHERE username=? COLLATE NOCASE", (code,)).fetchone()
    if not person:
        raise ApiError("El código de empleado no corresponde a un usuario existente.")
    work = row.get("work_date", "")
    if isinstance(work, str) and re.fullmatch(r"\d{2}/\d{2}/\d{4}", work.strip()):
        day, month, year = work.strip().split("/")
        work = f"{year}-{month}-{day}"
    activity = _activity(db, activity_id)
    field_keys = {field["key"] for field in activity["fields"]}
    values = {key: value for key, value in row.items() if key in field_keys}
    payload = {"activity_id": activity_id, "responsible_id": person["id"], "work_date": work,
               "quantity": row.get("quantity", 1) or 1, "data": values}
    _normalized_payload(db, actor, payload)
    return payload


def _preview_import(db, user, data):
    _manager(user)
    activity_id = data.get("activity_id")
    if activity_id not in {"revision", "sellado"}:
        raise ApiError("La importación inicial está disponible para revisión técnica y sellado.")
    rows = data.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ApiError("El archivo no contiene filas de datos.")
    if len(rows) > MAX_IMPORT_ROWS:
        raise ApiError(f"Importa hasta {MAX_IMPORT_ROWS} filas por archivo.", 413)
    fingerprint = _text(data.get("fingerprint"), "Huella del archivo", 128, True)
    if not re.fullmatch(r"[0-9a-fA-F]{64}", fingerprint):
        fingerprint = hashlib.sha256(_json(rows).encode()).hexdigest()
    filename = _text(data.get("filename", "archivo"), "Nombre del archivo", 200, True)
    errors, warnings, valid, summary = [], [], [], defaultdict(int)
    seen_serials = set()
    for index, row in enumerate(rows, 2):
        try:
            payload = _row_payload(db, user, activity_id, row)
            normalized = _normalized_payload(db, user, payload)
            serial = normalized["data"].get("serie", "")
            key = (serial, normalized["work_date"])
            if key in seen_serials:
                warnings.append({"row": index, "message": "La misma serie y fecha aparecen antes en este archivo; confirma que es otra revisión legítima.", "same_day": True})
            seen_serials.add(key)
            previous = _prior_events(db, activity_id, serial)
            if previous:
                warnings.append({"row": index, "message": "La serie ya tiene historial; debe confirmarse como un evento nuevo.",
                                 "same_day": any(item["work_date"] == normalized["work_date"] for item in previous)})
            person = db.execute("SELECT name,username FROM users WHERE id=?", (normalized["responsible_id"],)).fetchone()
            summary[(normalized["responsible_id"], person["name"], person["username"])] += normalized["quantity"]
            valid.append(payload)
        except ApiError as error:
            errors.append({"row": index, "message": error.message})
    with _transaction(db):
        old = db.execute("SELECT * FROM import_jobs WHERE activity_id=? AND fingerprint=?", (activity_id, fingerprint)).fetchone()
        if old:
            if old["status"] == "confirmado":
                result = json.loads(old["result_json"] or "{}")
                return {"preview_id": old["id"], "rows_count": len(rows), "valid_count": result.get("imported", 0),
                        "errors": [], "warnings": [], "summary": result.get("summary", []), "already_imported": True}
            # Otro supervisor puede previsualizar el mismo archivo, pero debe poseer el trabajo al confirmar.
            preview_id = old["id"]
            db.execute("UPDATE import_jobs SET actor_id=?,filename=?,rows_json=?,status=?,result_json=? WHERE id=?",
                       (user["id"], filename, _json(rows), "preparado" if not errors else "con_errores",
                        _json({"errors": errors, "warnings": warnings}), preview_id))
        else:
            preview_id = uuid.uuid4().hex
            db.execute("""INSERT INTO import_jobs(id,actor_id,activity_id,filename,fingerprint,rows_json,status,result_json,created_at)
                          VALUES(?,?,?,?,?,?,?,?,?)""", (preview_id, user["id"], activity_id, filename, fingerprint,
                          _json(rows), "preparado" if not errors else "con_errores", _json({"errors": errors, "warnings": warnings}), now()))
    return {"preview_id": preview_id, "rows_count": len(rows), "valid_count": len(valid), "errors": errors, "warnings": warnings,
            "summary": [{"responsible_id": person_id, "responsible_name": f"{name} ({code})", "quantity": qty}
                        for (person_id, name, code), qty in sorted(summary.items())], "already_imported": False}


def _confirm_import(db, user, data):
    _manager(user)
    preview_id = _text(data.get("preview_id"), "Importación", 64, True)
    with _transaction(db):
        job = db.execute("SELECT * FROM import_jobs WHERE id=?", (preview_id,)).fetchone()
        if not job:
            raise ApiError("La vista previa no existe.", 404)
        if job["actor_id"] != user["id"]:
            raise ApiError("Solo quien previsualizó esta carga puede confirmarla.", 403)
        if job["status"] == "confirmado":
            result = json.loads(job["result_json"] or "{}")
            return {"ok": True, "imported": result.get("imported", 0), "already_imported": True}
        if job["status"] != "preparado":
            raise ApiError("Corrige los errores del archivo antes de confirmar.", 400)
        rows = json.loads(job["rows_json"])
        staged = []
        for index, row in enumerate(rows, 2):
            try:
                payload = _row_payload(db, user, job["activity_id"], row)
                payload["operation_id"] = f"import:{preview_id}:{index}"
                payload["confirm_reentry"] = data.get("confirm_reentry") is True
                staged.append(payload)
            except ApiError as error:
                raise ApiError(f"Fila {index}: {error.message}", 409) from None
        summary = Counter()
        for payload in staged:
            saved = _save_event(db, user, payload, import_id=preview_id)
            event = saved["record"]
            summary[(event["responsible_id"], event["responsible_name"], event["responsible_username"])] += event["quantity"]
        result = {"imported": len(staged), "summary": [{"responsible_id": person_id, "responsible_name": f"{name} ({code})", "quantity": qty}
                  for (person_id, name, code), qty in summary.items()]}
        db.execute("UPDATE import_jobs SET status='confirmado',result_json=?,confirmed_at=? WHERE id=?", (_json(result), now(), preview_id))
        audit(db, user, "importacion", preview_id, "confirmar", after={"activity_id": job["activity_id"], "filename": job["filename"], **result})
    return {"ok": True, "imported": len(staged)}


def export_rows(db, user, query):
    rows = _events(db, user, query)
    headers = ["ID", "Fecha de trabajo", "Mes", "Año", "Actividad", "Versión", "Cantidad", "Unidad", "Serie",
               "SAP", "Marca / modelo", "Voltaje", "Condición técnica", "Condición visual", "Nuevo / recuperado", "Resultado de reutilización",
               "Código del responsable", "Responsable", "Código del capturador", "Registrado por", "Estado", "Revisión", "Observaciones", "Creado en"]
    standard_keys = {"serie", "sap", "marca", "voltaje", "condicion", "condicion_visual", "clasificacion", "resultado", "observaciones"}
    # Conserva campos añadidos a cualquier versión, con sus etiquetas históricas.
    # Dos campos homónimos de actividades distintas conservan columnas distintas.
    extra_columns = {}
    used_labels = set(headers)
    for event in reversed(rows):
        for field in event["fields"]:
            key = field["key"]
            if key in standard_keys:
                continue
            identity = (event["activity_id"], key, field["label"])
            if identity in extra_columns:
                continue
            label = f"{field['label']} · {event['activity_name']}"
            if label in used_labels:
                label += f" ({key}, v{event['activity_version']})"
            while label in used_labels:
                label += "_"
            used_labels.add(label)
            extra_columns[identity] = label
    headers.extend(extra_columns.values())
    quality_columns = any("desviacion_pct" in event["data"] for event in rows)
    if quality_columns:
        headers.extend(["Desviación calculada (%)", "Fuera de tolerancia"])
    values = []
    for event in reversed(rows):
        data = event["data"]
        value_row = [event["id"], event["work_date"], event["work_date"][5:7], event["work_date"][:4],
                       event["activity_name"], event["activity_version"], event["quantity"], event["unit"],
                       data.get("serie", ""), data.get("sap", ""), data.get("marca", ""), data.get("voltaje", ""),
                       data.get("condicion", ""), data.get("condicion_visual", ""), data.get("clasificacion", ""),
                       data.get("resultado", ""), event["responsible_username"], event["responsible_name"],
                       event["recorded_by_username"], event["recorded_by_name"], event["state"],
                       event["revision"], data.get("observaciones", ""), event["created_at"]]
        event_keys = {(event["activity_id"], field["key"], field["label"]) for field in event["fields"]}
        for identity in extra_columns:
            value = data.get(identity[1], "") if identity in event_keys else ""
            if isinstance(value, bool):
                value = "Sí" if value else "No"
            value_row.append(value)
        if quality_columns:
            value_row.extend([data.get("desviacion_pct", ""), "Sí" if data.get("fuera_tolerancia") is True else "No" if data.get("fuera_tolerancia") is False else ""])
        values.append(value_row)
    context = []
    if query.get("desde") or query.get("hasta"):
        context.append(f"Período: {query.get('desde') or 'inicio'} a {query.get('hasta') or 'actualidad'}")
    for key, label in (("activity_id", "Actividad"), ("activity_name", "Nombre histórico de actividad"), ("responsible_id", "Responsable"), ("sap", "SAP"),
                       ("voltage", "Voltaje"), ("condition", "Condición"), ("brand", "Marca"), ("model", "Modelo"), ("meter", "Serie"), ("state", "Estado"),
                       ("metric", "Indicador"), ("unit", "Unidad"), ("failure", "Fallo informado"), ("voltage_missing", "Sin voltaje informado"), ("search", "Búsqueda")):
        if query.get(key):
            maximum = {"failure": 1500, "search": 200}.get(key, 150)
            context.append(f"{label}: {_text(query[key], label, maximum)}")
    context.append(f"Generado: {now()}")
    title = "Laboratorio de Medidas — Control de Producción | " + " · ".join(context)
    return {"headers": headers, "rows": values, "title": title}


def _audit_entries(db, user, query):
    _manager(user)
    limit = _integer(query.get("limit", 200), "Límite de auditoría", 1, 1000)
    rows = db.execute("""SELECT a.*,u.name AS actor_name FROM audit_entries a LEFT JOIN users u ON u.id=a.actor_id
                         ORDER BY a.id DESC LIMIT ?""", (limit,)).fetchall()
    return {"entries": [{"id": row["id"], "actor_name": row["actor_name"] or "Sistema", "entity": row["entity"],
                          "entity_id": row["entity_id"], "action": row["action"], "reason": row["reason"],
                          "created_at": row["created_at"], "before": json.loads(row["before_json"]) if row["before_json"] else None,
                          "after": json.loads(row["after_json"]) if row["after_json"] else None} for row in rows]}


def handle_get(db, user, path, query):
    if path == "/api/actividades":
        return _activities(db, user)
    if path == "/api/sap":
        return operational.sap_items(db)
    if path in {"/api/eventos", "/api/registros"}:
        return _list_events(db, user, query)
    if path == "/api/detalle":
        return _detail(db, user, query)
    match = re.fullmatch(r"/api/eventos/(\d+)", path)
    if match:
        if user["role"] == "visitante":
            raise ApiError("La cuenta visitante no tiene acceso al detalle de registros.", 403)
        event = _event(db, int(match.group(1)))
        if user["role"] not in MANAGERS and event["responsible_id"] != user["id"]:
            raise ApiError("Solo puedes consultar tu propia producción.", 403)
        return {"record": event}
    if path == "/api/historial":
        return _history(db, user, query)
    if path == "/api/dashboard":
        if phase2.enabled(db) and user["role"]=="tecnico" and query.get("activity_id"):phase2.access(db,user,query["activity_id"],"panel")
        return _dashboard(db, user, query)
    if path == "/api/recepciones":
        return {"receipts": _receipts(db, user, query)}
    if path == "/api/metas":
        return {"goals": _goals(db, user, query)}
    if path == "/api/auditoria":
        return _audit_entries(db, user, query)
    return operational.handle_get(db, user, path, query)


def handle_post(db, user, path, data):
    if not isinstance(data, dict):
        raise ApiError("Se esperaba un objeto de datos.")
    if path == "/api/actividades":
        if phase2.enabled(db):phase2.f.administrator(user)
        return _save_activity(db, user, data)
    if path == "/api/sap":
        if phase2.enabled(db):
            with _transaction(db):return phase2.save_article(db,user,data)
        return _save_sap(db, user, data)
    if path in {"/api/eventos", "/api/registros"}:
        with _transaction(db):
            return _save_event(db, user, data)
    if path == "/api/metas":
        return _save_goal(db, user, data)
    if path == "/api/import/preview":
        return _preview_import(db, user, data)
    if path == "/api/import/confirm":
        return _confirm_import(db, user, data)
    match = re.fullmatch(r"/api/eventos/(\d+)/(corregir|anular|restaurar)", path)
    if match:
        event_id = int(match.group(1))
        if match.group(2) == "corregir":
            return _correct_event(db, user, event_id, data)
        return _state_event(db, user, event_id, data, restore=match.group(2) == "restaurar")
    return operational.handle_post(db, user, path, data)
