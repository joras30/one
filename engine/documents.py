"""Documentos de producción, usando exclusivamente la biblioteca estándar.

XLSX/CSV conservan el texto original (incluidos códigos con ceros iniciales).
Los libros importados no ejecutan fórmulas, macros ni enlaces. El PDF usa la
fuente incorporada Helvetica/WinAnsi: admite el español; caracteres fuera de
CP1252 se representan con ``?``. Excel/CSV mantienen el Unicode completo.
"""
from __future__ import annotations

import csv
import io
import math
import posixpath
import re
import stat
import textwrap
import unicodedata
import zipfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath
from typing import Iterable, Sequence
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 32 * 1024 * 1024
MAX_ROWS = 10_000
MAX_COLUMNS = 100
MAX_CELL_CHARACTERS = 10_000
MAX_ZIP_ENTRIES = 500
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_XML_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


def _plain(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        text = value.isoformat(timespec="seconds")
    elif isinstance(value, date):
        text = value.isoformat()
    else:
        text = str(value)
    if len(text) > MAX_CELL_CHARACTERS:
        raise ValueError(f"Un valor supera el máximo de {MAX_CELL_CHARACTERS} caracteres.")
    if _XML_CONTROL.search(text):
        raise ValueError("Un valor contiene caracteres de control no admitidos.")
    return text


def normalize_header(value: str) -> str:
    """Convierte nombres humanos y canónicos a las claves de importación."""
    text = unicodedata.normalize("NFKD", _plain(value).strip().lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    aliases = {
        "fecha": "work_date", "fecha_trabajo": "work_date",
        "fecha_de_trabajo": "work_date", "fecha_ejecucion": "work_date",
        "fecha_de_ejecucion": "work_date", "fecha_revision": "work_date",
        "fecha_sellado": "work_date", "fecha_de_sellado": "work_date",
        "codigo_empleado": "responsible", "codigo_de_empleado": "responsible",
        "cod_empleado": "responsible", "empleado": "responsible",
        "usuario": "responsible", "responsable": "responsible",
        "responsable_codigo": "responsible", "tecnico": "responsible",
        "revisado_por": "responsible", "sellado_por": "responsible",
        "numero_medidor": "serie", "numero_de_medidor": "serie",
        "numero_serie": "serie", "numero_de_serie": "serie",
        "codigo_medidor": "serie", "codigo_de_medidor": "serie",
        "medidor": "serie", "meter": "serie", "serial": "serie",
        "codigo_sap": "sap", "cod_sap": "sap", "material_sap": "sap",
        "marca_modelo": "marca", "marca_y_modelo": "marca",
        "brand": "marca", "brand_model": "marca", "model": "modelo",
        "tension": "voltaje", "nivel_tension": "voltaje",
        "nivel_de_tension": "voltaje", "voltage": "voltaje",
        "condicion_tecnica": "condicion", "condicion_encontrada": "condicion",
        "condicion_principal": "condicion", "condition": "condicion",
        "tipo_medidor": "clasificacion", "nuevo_recuperado": "clasificacion",
        "origen": "clasificacion", "procedencia": "clasificacion",
        "resultado_revision": "resultado", "resultado_de_revision": "resultado",
        "configuracion_sap": "sap_config_id", "id_configuracion_sap": "sap_config_id",
        "tipo_de_inspeccion": "tipo_inspeccion", "falla": "fallo",
        "valor_de_referencia": "valor_referencia", "referencia": "valor_referencia",
        "valor_de_medicion": "valor_medido", "medicion": "valor_medido",
        "tolerancia_porcentual": "tolerancia_pct", "tolerancia": "tolerancia_pct",
        "observacion": "observaciones", "notas": "observaciones", "notes": "observaciones",
        "quantity": "quantity", "cantidad": "quantity",
    }
    return aliases.get(text, text)


def _table(headers: Sequence, rows: Iterable[Sequence]) -> tuple[list[str], list[list]]:
    names = [_plain(x) for x in headers]
    if not names or len(names) > MAX_COLUMNS or any(not name.strip() for name in names):
        raise ValueError(f"La tabla necesita entre 1 y {MAX_COLUMNS} columnas con nombre.")
    result = []
    for row in rows:
        values = list(row)
        if len(values) != len(names):
            raise ValueError("La cantidad de valores no coincide con las columnas de la tabla.")
        if len(result) >= MAX_ROWS:
            raise ValueError(f"El archivo supera el máximo de {MAX_ROWS} filas; reduzca el período.")
        for value in values:
            _plain(value)
        result.append(values)
    return names, result


def _safe_csv(value) -> str:
    text = _plain(value)
    if text.lstrip()[:1] in ("=", "+", "-", "@"):
        return "'" + text
    return text


def write_csv(headers: Sequence, rows: Iterable[Sequence], title: str = "Producción") -> bytes:
    """CSV UTF-8 con BOM, separado por punto y coma y fórmulas neutralizadas."""
    names, values = _table(headers, rows)
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow([_safe_csv(x) for x in names])
    writer.writerows([_safe_csv(x) for x in row] for row in values)
    return output.getvalue().encode("utf-8-sig")


def _column(index: int) -> str:
    name = ""
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def _inline_cell(ref: str, value, style: int = 0) -> str:
    return (f'<c r="{ref}" s="{style}" t="inlineStr"><is>'
            f'<t xml:space="preserve">{escape(_plain(value))}</t></is></c>')


def write_xlsx(headers: Sequence, rows: Iterable[Sequence], title: str = "Producción") -> bytes:
    """Libro OOXML válido: strings literales, códigos textuales y cantidades numéricas."""
    names, values = _table(headers, rows)
    title = _plain(title) or "Producción"
    sheet_name = re.sub(r"[\[\]:*?/\\]", " ", title)[:31].strip(" '") or "Producción"
    body = ['<row r="1" ht="30" customHeight="1">']
    body.extend(_inline_cell(f"{_column(i)}1", name, 1) for i, name in enumerate(names, 1))
    body.append("</row>")
    identity = {"serie", "sap", "responsible", "id", "codigo", "numero_orden"}
    for ri, row in enumerate(values, 2):
        body.append(f'<row r="{ri}">')
        for ci, value in enumerate(row, 1):
            ref = f"{_column(ci)}{ri}"
            key = normalize_header(names[ci - 1])
            if key not in identity and isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
                if not math.isfinite(value):
                    raise ValueError("La tabla contiene un número no válido.")
                body.append(f'<c r="{ref}" s="2" t="n"><v>{escape(str(value))}</v></c>')
            elif isinstance(value, bool) and key not in identity:
                body.append(f'<c r="{ref}" s="2" t="b"><v>{int(value)}</v></c>')
            else:
                body.append(_inline_cell(ref, value))
        body.append("</row>")
    last = f"{_column(len(names))}{len(values) + 1}"
    widths = []
    for ci, name in enumerate(names):
        samples = [len(_plain(row[ci])) for row in values[:100]]
        width = min(55, max(14, len(name) + 3, min(45, max(samples, default=0)) + 2))
        widths.append(f'<col min="{ci+1}" max="{ci+1}" width="{width}" customWidth="1"/>')
    sheet = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             f'<worksheet xmlns="{NS}"><dimension ref="A1:{last}"/>'
             '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" '
             'activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
             '<sheetFormatPr defaultRowHeight="18"/><cols>' + "".join(widths) + '</cols>'
             '<sheetData>' + "".join(body) + f'</sheetData><autoFilter ref="A1:{last}"/>'
             '<pageMargins left="0.3" right="0.3" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>'
             '<pageSetup orientation="landscape" paperSize="9" fitToWidth="1" fitToHeight="0"/>'
             '</worksheet>')
    styles = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="{NS}">
<fonts count="2"><font><sz val="11"/><color rgb="FF243653"/><name val="Calibri"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font></fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF10274D"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="3"><xf numFmtId="49" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"><alignment vertical="top" wrapText="1"/></xf><xf numFmtId="49" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"><alignment vertical="center" wrapText="1"/></xf><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"><alignment vertical="top"/></xf></cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>'''
    created = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    parts = {
        "[Content_Types].xml": '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>''',
        "_rels/.rels": f'''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{PACKAGE_REL_NS}"><Relationship Id="rId1" Type="{REL_NS}/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="{REL_NS}/extended-properties" Target="docProps/app.xml"/></Relationships>''',
        "xl/workbook.xml": f'''<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="{NS}" xmlns:r="{REL_NS}"><bookViews><workbookView/></bookViews><sheets><sheet name="{escape(sheet_name, {chr(34): '&quot;'})}" sheetId="1" r:id="rId1"/></sheets></workbook>''',
        "xl/_rels/workbook.xml.rels": f'''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{PACKAGE_REL_NS}"><Relationship Id="rId1" Type="{REL_NS}/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="{REL_NS}/styles" Target="styles.xml"/></Relationships>''',
        "xl/styles.xml": styles,
        "xl/worksheets/sheet1.xml": sheet,
        "docProps/core.xml": f'''<?xml version="1.0" encoding="UTF-8"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>{escape(title)}</dc:title><dc:creator>Laboratorio de Medidas — Control de Producción</dc:creator><dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created></cp:coreProperties>''',
        "docProps/app.xml": '''<?xml version="1.0" encoding="UTF-8"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>Laboratorio de Medidas</Application></Properties>''',
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            archive.writestr(name, content.encode("utf-8"))
    return output.getvalue()


def _date_value(text: str) -> str:
    stripped = text.strip()
    for fmt in ("%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(stripped, fmt).date().isoformat()
        except ValueError:
            pass
    if re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", stripped):
        try:
            return datetime.fromisoformat(stripped.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            pass
    return text


def _records(matrix: Iterable[Sequence]) -> list[dict[str, str]]:
    names = None
    width = 0
    result = []
    for raw in matrix:
        row = [_plain(x) for x in raw]
        if not any(cell.strip() for cell in row):
            continue
        if names is None:
            while row and not row[-1].strip():
                row.pop()
            width = len(row)
            if not width or width > MAX_COLUMNS:
                raise ValueError(f"El archivo admite como máximo {MAX_COLUMNS} columnas.")
            names = [normalize_header(x) for x in row]
            if any(not x for x in names):
                raise ValueError("Todas las columnas de la tabla deben tener encabezado.")
            if len(set(names)) != len(names):
                raise ValueError("Hay encabezados duplicados o equivalentes en el archivo.")
            continue
        if len(row) > width and any(cell.strip() for cell in row[width:]):
            raise ValueError("Una fila contiene valores fuera de las columnas con encabezado.")
        row = (row + [""] * width)[:width]
        values = dict(zip(names, row))
        if "work_date" in values:
            values["work_date"] = _date_value(values["work_date"])
        if len(result) >= MAX_ROWS:
            raise ValueError(f"El archivo supera el máximo de {MAX_ROWS} filas.")
        result.append(values)
    if names is None:
        raise ValueError("El archivo está vacío o no tiene encabezados.")
    return result


def _read_csv(content: bytes) -> list[dict[str, str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("cp1252")
        except UnicodeDecodeError as error:
            raise ValueError("No se pudo leer el CSV; guárdelo con codificación UTF-8.") from error
    if _XML_CONTROL.search(text):
        raise ValueError("El CSV contiene caracteres de control no admitidos.")
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
        delimiter = dialect.delimiter
    except csv.Error:
        first = text.splitlines()[0] if text.splitlines() else ""
        delimiter = max((",", ";", "\t"), key=first.count) if any(c in first for c in ",;\t") else ";"
    try:
        return _records(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True))
    except csv.Error as error:
        raise ValueError("El formato del CSV no es válido; revise comillas y separadores.") from error


def _xml(archive: zipfile.ZipFile, name: str):
    try:
        raw = archive.read(name)
    except (KeyError, zipfile.BadZipFile, RuntimeError) as error:
        raise ValueError("El libro Excel no contiene una estructura válida.") from error
    if re.search(br"<!\s*(DOCTYPE|ENTITY)\b", raw, re.I):
        raise ValueError("El libro contiene definiciones XML no admitidas.")
    try:
        return ET.fromstring(raw)
    except ET.ParseError as error:
        raise ValueError("El libro Excel contiene XML no válido.") from error


def _date_styles(archive: zipfile.ZipFile) -> set[int]:
    if "xl/styles.xml" not in archive.namelist():
        return set()
    styles = _xml(archive, "xl/styles.xml")
    custom = {int(x.get("numFmtId", "0")): x.get("formatCode", "")
              for x in styles.findall(f"{{{NS}}}numFmts/{{{NS}}}numFmt")}
    date_ids = set(range(14, 23)) | set(range(27, 37)) | {45, 46, 47} | set(range(50, 59))
    indexes = set()
    for index, xf in enumerate(styles.findall(f"{{{NS}}}cellXfs/{{{NS}}}xf")):
        numfmt = int(xf.get("numFmtId", "0"))
        code = re.sub(r'"[^"]*"|\\.|\[[^]]*\]', "", custom.get(numfmt, "")).lower()
        if numfmt in date_ids or re.search(r"[ydhms]", code):
            indexes.add(index)
    return indexes


def _number(text: str) -> str:
    try:
        value = Decimal(text)
        if not value.is_finite():
            raise ValueError("El libro contiene un número no válido.")
        if abs(value.adjusted()) > 1000:
            raise ValueError("El libro contiene un número fuera del rango admitido.")
        return str(int(value)) if value == value.to_integral_value() else format(value.normalize(), "f")
    except InvalidOperation as error:
        raise ValueError("El libro contiene un número no válido.") from error


def _excel_date(value: str, epoch1904: bool) -> str:
    try:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError()
        # Excel conserva un 29/02/1900 ficticio: ajustar únicamente días anteriores.
        adjusted = number + (1 if not epoch1904 and 0 < number < 60 else 0)
        epoch = datetime(1904, 1, 1) if epoch1904 else datetime(1899, 12, 30)
        converted = epoch + timedelta(days=adjusted)
        if converted.time() == datetime.min.time():
            return converted.date().isoformat()
        return converted.isoformat(timespec="seconds")
    except (ValueError, OverflowError) as error:
        raise ValueError("El libro contiene una fecha fuera del rango admitido.") from error


def _read_xlsx(content: bytes, sheet_name=None, raw_matrix=False, strict_text_ids=False) -> list[dict[str, str]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except (zipfile.BadZipFile, OSError) as error:
        raise ValueError("El archivo no es un libro XLSX válido.") from error
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ZIP_ENTRIES or sum(x.file_size for x in infos) > MAX_UNCOMPRESSED_BYTES:
            raise ValueError("El libro Excel es demasiado grande al descomprimirlo.")
        names = [x.filename for x in infos]
        if len(set(names)) != len(names):
            raise ValueError("El libro contiene archivos internos duplicados.")
        for info in infos:
            path = PurePosixPath(info.filename)
            if (path.is_absolute() or ".." in path.parts or "\\" in info.filename
                    or stat.S_ISLNK(info.external_attr >> 16) or info.flag_bits & 1):
                raise ValueError("El libro contiene rutas o archivos internos no admitidos.")
            if "vbaproject" in info.filename.lower() or "externallinks/" in info.filename.lower():
                raise ValueError("No se admiten macros ni vínculos externos en la importación.")
            if info.filename.endswith(".rels"):
                relationships = _xml(archive, info.filename)
                if any(r.get("TargetMode", "").lower() == "external" for r in relationships):
                    raise ValueError("No se admiten vínculos externos en la importación.")
        types = _xml(archive, "[Content_Types].xml")
        if any("macroenabled" in item.get("ContentType", "").lower()
               or "vba" in item.get("ContentType", "").lower() for item in types):
            raise ValueError("No se admiten macros en la importación.")
        workbook = _xml(archive, "xl/workbook.xml")
        sheets = workbook.findall(f"{{{NS}}}sheets/{{{NS}}}sheet")
        if not sheets:
            raise ValueError("El libro Excel no tiene hojas para importar.")
        selected = sheets[0] if sheet_name is None else next((sheet for sheet in sheets if sheet.get("name", "").casefold() == sheet_name.casefold()), None)
        if selected is None:
            raise ValueError("No existe la hoja solicitada: " + str(sheet_name))
        rel_id = selected.get(f"{{{REL_NS}}}id")
        rels = _xml(archive, "xl/_rels/workbook.xml.rels")
        relationship = next((r for r in rels if r.get("Id") == rel_id), None)
        if relationship is None or not relationship.get("Type", "").endswith("/worksheet"):
            raise ValueError("La primera hoja del libro debe ser una tabla de datos.")
        target = relationship.get("Target", "")
        if ":" in target or "\\" in target or "?" in target or "#" in target:
            raise ValueError("El libro contiene una referencia de hoja no admitida.")
        target = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
        if not target.startswith("xl/") or ".." in PurePosixPath(target).parts:
            raise ValueError("El libro contiene una referencia de hoja no admitida.")
        strings = []
        if "xl/sharedStrings.xml" in names:
            shared = _xml(archive, "xl/sharedStrings.xml")
            for si in shared.findall(f"{{{NS}}}si"):
                strings.append(_plain("".join(t.text or "" for t in si.iter(f"{{{NS}}}t"))))
                if len(strings) > (MAX_ROWS + 1) * MAX_COLUMNS:
                    raise ValueError("El libro contiene demasiados valores de texto.")
        try:
            date_styles = _date_styles(archive)
        except (ValueError, TypeError) as error:
            raise ValueError("El libro contiene formatos de celda no válidos.") from error
        props = workbook.find(f"{{{NS}}}workbookPr")
        epoch1904 = props is not None and props.get("date1904", "0").lower() in ("1", "true")
        worksheet = _xml(archive, target)
        if worksheet.find(f".//{{{NS}}}f") is not None:
            raise ValueError("El libro contiene fórmulas; conviértalas a valores antes de importar.")
        matrix = []
        identity_columns=set()
        for row in worksheet.findall(f"{{{NS}}}sheetData/{{{NS}}}row"):
            values = {}
            next_index = 0
            for cell in row.findall(f"{{{NS}}}c"):
                ref = cell.get("r", "")
                if ref:
                    match = re.fullmatch(r"([A-Za-z]+)[1-9][0-9]*", ref)
                    if not match:
                        raise ValueError("El libro contiene una referencia de celda no válida.")
                    ci = 0
                    for char in match.group(1).upper():
                        ci = ci * 26 + ord(char) - 64
                    ci -= 1
                else:
                    ci = next_index
                next_index = ci + 1
                if ci >= MAX_COLUMNS:
                    raise ValueError(f"El archivo admite como máximo {MAX_COLUMNS} columnas.")
                if ci in values:
                    raise ValueError("El libro contiene celdas duplicadas.")
                typ = cell.get("t", "n")
                val = cell.find(f"{{{NS}}}v")
                raw = val.text if val is not None and val.text is not None else ""
                if strict_text_ids and ci in identity_columns and raw and typ in {"n","b"}:
                    raise ValueError(f"Celda {ref}: serie, sello o código guardado como número. Utiliza texto en la plantilla para conservar ceros iniciales.")
                if typ == "inlineStr":
                    text = "".join(t.text or "" for t in cell.iter(f"{{{NS}}}t"))
                elif typ == "s":
                    try:
                        index = int(raw)
                        if index < 0:
                            raise IndexError()
                        text = strings[index]
                    except (ValueError, IndexError) as error:
                        raise ValueError("El libro contiene una referencia de texto no válida.") from error
                elif typ == "e":
                    raise ValueError("El libro contiene celdas con errores; corríjalas antes de importar.")
                elif typ == "b":
                    text = "true" if raw == "1" else "false"
                elif typ in ("str", "d") or not raw:
                    text = raw
                elif typ == "n":
                    try:
                        is_date = int(cell.get("s", "0")) in date_styles
                    except ValueError as error:
                        raise ValueError("El libro contiene un estilo de celda no válido.") from error
                    text = _excel_date(raw, epoch1904) if is_date else _number(raw)
                else:
                    raise ValueError("El libro contiene un tipo de celda no admitido.")
                values[ci] = _plain(text)
            if values:
                if strict_text_ids and not identity_columns:
                    identity_columns={ci for ci,value in values.items() if normalize_header(value) in {"serie","sap","articulo_sap","sello_1","sello_2","responsible","numero_de_empleado"}}
                matrix.append([values.get(index, "") for index in range(max(values) + 1)])
                if len(matrix) > MAX_ROWS + 1:
                    raise ValueError(f"El archivo supera el máximo de {MAX_ROWS} filas.")
        return matrix if raw_matrix else _records(matrix)


def read_table(filename: str, content: bytes, strict_text_ids=False) -> list[dict[str, str]]:
    """Lee la primera tabla sin evaluar fórmulas ni ejecutar contenido activo."""
    if not isinstance(content, bytes):
        raise ValueError("El contenido del archivo no es válido.")
    if not content or len(content) > MAX_INPUT_BYTES:
        raise ValueError("El archivo está vacío o supera el máximo de 8 MiB.")
    extension = PurePosixPath(str(filename).replace("\\", "/")).suffix.lower()
    if extension == ".csv":
        return _read_csv(content)
    if extension == ".xlsx":
        try:
            return _read_xlsx(content, strict_text_ids=strict_text_ids)
        except (zipfile.BadZipFile, RuntimeError, OSError) as error:
            raise ValueError("No se pudo leer el libro XLSX; compruebe su integridad.") from error
    raise ValueError("Seleccione un archivo CSV o XLSX, sin macros.")


def template_columns(activity_id: str) -> list[str]:
    if activity_id == "revision":
        return ["work_date", "responsible", "serie", "marca", "modelo", "voltaje", "sap", "sap_config_id", "condicion",
                "clasificacion", "resultado", "tipo_inspeccion", "fallo", "valor_referencia", "valor_medido",
                "tolerancia_pct", "observaciones"]
    if activity_id == "sellado":
        return ["work_date", "responsible", "serie", "sap", "sap_config_id", "marca", "modelo", "voltaje", "clasificacion", "observaciones"]
    raise ValueError("Las plantillas de importación están disponibles para revisión técnica y sellado.")


def certificate_table(certificate: dict) -> tuple[list[str], list[list], str]:
    """Representar íntegra el acta persistida; no recalcular sus entregas al exportar."""
    if not isinstance(certificate, dict) or not isinstance(certificate.get("snapshot"), dict):
        raise ValueError("El acta no contiene un cierre verificable.")
    number = _plain(certificate.get("number") or certificate.get("id") or "")
    if not number or len(number) > 150:
        raise ValueError("El folio del acta no es válido.")
    rows = [["Folio", number], ["Fecha de emisión (UTC)", certificate.get("created_at", "")],
            ["SHA-256 del contenido certificado", certificate.get("hash", "")],
            ["Alcance", "Acta de cierre aprobada en el sistema. La huella verifica su contenido; no es una firma digital institucional."]]
    if "current" in certificate:
        rows.insert(1, ["Vigencia", "Cierre vigente" if certificate["current"] else "Acta histórica; no representa el cierre vigente de la orden"])
    labels = {"process": "Proceso", "order_number": "Número de orden", "sap": "Código SAP",
              "expected": "Total esperado", "received": "Total recibido", "pending": "Pendiente",
              "excess": "Excedente", "deliveries": "Entregas", "work_date": "Fecha de trabajo",
              "responsible_name": "Responsable técnico", "recorded_by_name": "Registrado por",
              "quantity": "Cantidad", "closed_by": "Cerrado por", "closed_at": "Fecha de cierre",
              "reason": "Motivo", "order": "Orden", "notes": "Observaciones", "state": "Estado"}

    def flatten(value, path):
        if isinstance(value, dict):
            for key, item in value.items():
                flatten(item, path + [labels.get(str(key), str(key))])
        elif isinstance(value, list):
            if not value:
                rows.append([" / ".join(path), "Sin elementos"])
            for index, item in enumerate(value, 1):
                flatten(item, path + [str(index)])
        else:
            detail = "Sí" if value is True else "No" if value is False else value
            rows.append([" / ".join(path), detail])
        if len(rows) > MAX_ROWS:
            raise ValueError("El acta supera el límite del reporte PDF; conserva su descarga JSON completa.")

    flatten(certificate["snapshot"], ["Contenido certificado"])
    return ["Campo certificado", "Valor"], rows, "Acta de cierre de lote — " + number


def _pdf_escape(text: str) -> bytes:
    return text.encode("cp1252", errors="replace").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def write_pdf(headers: Sequence, rows: Iterable[Sequence], title: str = "Producción") -> bytes:
    """PDF multipágina de detalle, con texto español WinAnsi y todos los campos.

Se presenta cada registro con etiquetas para evitar truncar tablas anchas.
No requiere fuentes del sistema, navegador ni bibliotecas externas.
"""
    names, values = _table(headers, rows)
    title = _plain(title) or "Producción"
    if len(title) > 500:
        raise ValueError("El título del reporte PDF supera el máximo de 500 caracteres.")
    title_lines = textwrap.wrap(title, width=52, replace_whitespace=True) or ["Producción"]
    lines = []
    for index, row in enumerate(values, 1):
        lines.append(f"Registro {index}")
        for name, value in zip(names, row):
            text = _plain(value).replace("\r\n", "\n").replace("\r", "\n")
            for part_index, part in enumerate(text.split("\n")):
                prefix = f"{name}: " if part_index == 0 else "  "
                lines.extend(textwrap.wrap(prefix + part, width=90, subsequent_indent="  ",
                                           replace_whitespace=True, break_long_words=True) or [prefix])
        lines.append("")
    if not lines:
        lines = ["No hay registros para los filtros seleccionados."]
    leading = 12
    page_height, page_width = 595, 842
    margin = 32
    header_space = 24 + len(title_lines) * 18
    per_page = max(10, int((page_height - margin * 2 - header_space - 20) // leading))
    pages = [lines[start:start + per_page] for start in range(0, len(lines), per_page)]
    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: f'<< /Type /Pages /Count {len(pages)} /Kids [ '.encode() +
           b" ".join(f"{4 + 2*i} 0 R".encode() for i in range(len(pages))) + b" ] >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    }
    santo_domingo = timezone(timedelta(hours=-4))
    timestamp = datetime.now(santo_domingo).strftime("%Y-%m-%d %H:%M UTC-04:00")
    for index, page in enumerate(pages):
        operations = [b"BT /F1 15 Tf 0.063 0.153 0.302 rg"]
        y = page_height - margin
        for line in title_lines:
            operations.append(f"1 0 0 1 {margin} {y} Tm (".encode() + _pdf_escape(line) + b") Tj")
            y -= 18
        operations.append(b"/F1 8 Tf 0.35 0.4 0.46 rg")
        operations.append(f"1 0 0 1 {margin} {y-1} Tm (".encode() +
                          _pdf_escape(f"Laboratorio de Medidas - {len(values)} registros - Generado {timestamp}") + b") Tj")
        operations.append(b"/F1 9 Tf 0.1 0.14 0.2 rg")
        y -= 25
        for line in page:
            operations.append(f"1 0 0 1 {margin} {y} Tm (".encode() + _pdf_escape(line) + b") Tj")
            y -= leading
        operations.append(b"/F1 8 Tf 0.35 0.4 0.46 rg")
        operations.append(f"1 0 0 1 {margin} 20 Tm (".encode() +
                          _pdf_escape(f"Página {index+1} de {len(pages)}") + b") Tj ET")
        stream = b"\n".join(operations)
        page_id, stream_id = 4 + 2 * index, 5 + 2 * index
        objects[page_id] = (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_width} {page_height}] "
                            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {stream_id} 0 R >>").encode()
        objects[stream_id] = f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"
    info_id = 4 + 2 * len(pages)
    objects[info_id] = b"<< /Title (" + _pdf_escape(title) + b") /Producer (Laboratorio de Medidas) >>"
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index in range(1, info_id + 1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode() + objects[index] + b"\nendobj\n")
    start_xref = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010} 00000 n \n".encode())
    output.extend((f"trailer\n<< /Size {len(offsets)} /Root 1 0 R /Info {info_id} 0 R >>\n"
                   f"startxref\n{start_xref}\n%%EOF\n").encode())
    return bytes(output)
