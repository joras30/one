"""Pruebas de archivos de intercambio usando únicamente datos ficticios."""
from __future__ import annotations

import csv
import importlib.util
import io
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch
import zipfile
from xml.etree import ElementTree as ET

APP_DIR = Path(__file__).resolve().parents[1] / 'APLICACION_ACTUAL'
sys.path.insert(0, str(APP_DIR))
import documents

MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def xlsx_fixture(sheet_xml, *, shared_strings=None, extra_files=None, external=False, date1904=False):
    """Un libro mínimo válido sin depender de Excel ni paquetes instalados."""
    output = io.BytesIO()
    types = ('<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="xml" ContentType="application/xml"/>'
             '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
             '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
             '</Types>')
    workbook = (f'<workbook xmlns="{MAIN}" xmlns:r="{REL}">'
                f'<workbookPr date1904="{int(date1904)}"/>'
                '<sheets><sheet name="Datos" sheetId="1" r:id="rId1"/></sheets></workbook>')
    workbook_rels = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                     f'<Relationship Id="rId1" Type="{REL}/worksheet" Target="worksheets/sheet1.xml"/>')
    if shared_strings is not None:
        workbook_rels += f'<Relationship Id="rId2" Type="{REL}/sharedStrings" Target="sharedStrings.xml"/>'
    if external:
        workbook_rels += f'<Relationship Id="rId3" Type="{REL}/externalLink" TargetMode="External" Target="https://example.invalid/datos.xlsx"/>'
    workbook_rels += '</Relationships>'
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', types)
        z.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml', workbook)
        z.writestr('xl/_rels/workbook.xml.rels', workbook_rels)
        z.writestr('xl/worksheets/sheet1.xml', sheet_xml)
        if shared_strings is not None:
            z.writestr('xl/sharedStrings.xml', shared_strings)
        for name, data in (extra_files or {}).items():
            z.writestr(name, data)
    return output.getvalue()


def inline_sheet(headers, rows):
    root = ET.Element(f'{{{MAIN}}}worksheet')
    data = ET.SubElement(root, f'{{{MAIN}}}sheetData')
    for index, values in enumerate([headers, *rows], 1):
        row = ET.SubElement(data, f'{{{MAIN}}}row', {'r': str(index)})
        for column, value in enumerate(values):
            cell = ET.SubElement(row, f'{{{MAIN}}}c', {'r': f'{chr(65+column)}{index}', 't': 'inlineStr'})
            text = ET.SubElement(ET.SubElement(cell, f'{{{MAIN}}}is'), f'{{{MAIN}}}t')
            text.text = str(value)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


class HeaderAndCsvTests(unittest.TestCase):
    def test_spanish_headers_map_to_canonical_fields(self):
        aliases = {
            ' Fecha de trabajo ': 'work_date',
            'Código de empleado': 'responsible',
            'Número de medidor': 'serie',
            'Código SAP': 'sap',
            'Marca / modelo': 'marca',
            'Tensión': 'voltaje',
            'Condición técnica': 'condicion',
        }
        for heading, expected in aliases.items():
            with self.subTest(heading=heading):
                self.assertEqual(documents.normalize_header(heading), expected)

    def test_csv_delimiters_and_bom_preserve_identifiers(self):
        for delimiter in [',', ';', '\t']:
            text = io.StringIO()
            writer = csv.writer(text, delimiter=delimiter)
            writer.writerow(['Fecha de trabajo', 'Código de empleado', 'Número de medidor', 'Código SAP'])
            writer.writerow(['2026-10-22', '90001', '00000123', '001003913'])
            result = documents.read_table('prueba.csv', ('\ufeff' + text.getvalue()).encode('utf-8'))
            with self.subTest(delimiter=delimiter):
                self.assertEqual(result, [{'work_date': '2026-10-22', 'responsible': '90001', 'serie': '00000123', 'sap': '001003913'}])

    def test_csv_export_neutralizes_formulas(self):
        values = ['=2+2', '+SUM(A1:A2)', '-2+3', '@SUM(A1)', '  =HYPERLINK("demo")', 'Observación común']
        blob = documents.write_csv(['observaciones'], [[value] for value in values])
        self.assertTrue(blob.startswith(b'\xef\xbb\xbf'))
        table = list(csv.reader(io.StringIO(blob.decode('utf-8-sig')), delimiter=';'))
        if len(table[0]) != 1:
            self.fail('La exportación de una columna cambió su estructura')
        exported = [row[0] for row in table[1:]]
        self.assertEqual(len(exported), len(values))
        for value in exported[:-1]:
            self.assertTrue(value.startswith("'"), value)
        self.assertEqual(exported[-1], 'Observación común')

    def test_duplicate_canonical_headers_are_rejected(self):
        with self.assertRaises(ValueError):
            documents.read_table('duplicados.csv', b'serie;numero_medidor\n0001;0002\n')

    def test_unknown_file_extension_is_rejected(self):
        with self.assertRaises(ValueError):
            documents.read_table('archivo.exe', b'serie\n0001\n')


class XlsxTests(unittest.TestCase):
    def test_writer_roundtrip_preserves_text_without_formulas(self):
        headers = ['serie', 'sap', 'observaciones']
        rows = [['00000123', '001003913', '=SUM(1,2)'], ['00000000', '000000001', '+2']]
        blob = documents.write_xlsx(headers, rows, title='Revisión técnica')
        self.assertEqual(documents.read_table('resultado.xlsx', blob), [dict(zip(headers, row)) for row in rows])
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            self.assertIsNone(z.testzip())
            for name in z.namelist():
                if name.startswith('xl/worksheets/') and name.endswith('.xml'):
                    root = ET.fromstring(z.read(name))
                    self.assertEqual(root.findall(f'.//{{{MAIN}}}f'), [], 'Los valores de texto no deben convertirse a fórmulas')

    @unittest.skipUnless(importlib.util.find_spec('openpyxl'), 'openpyxl no es requisito de ejecución')
    def test_writer_opens_in_independent_xlsx_reader(self):
        import openpyxl
        blob = documents.write_xlsx(['serie', 'sap'], [['0000123', '001003913']], title='Producción')
        book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=False)
        try:
            rows = list(book.worksheets[0].iter_rows(values_only=True))
            self.assertIn(('0000123', '001003913'), rows)
        finally:
            book.close()

    def test_shared_strings_inline_and_numeric_integer(self):
        strings = f'<sst xmlns="{MAIN}"><si><t>serie</t></si><si><t>sap</t></si><si><t>cantidad</t></si></sst>'
        sheet = f'''<worksheet xmlns="{MAIN}"><sheetData>
        <row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="s"><v>2</v></c></row>
        <row r="2"><c r="A2" t="inlineStr"><is><t>0000123</t></is></c><c r="B2"><v>1003913.0</v></c><c r="C2"><v>12.0</v></c></row>
        </sheetData></worksheet>'''
        result = documents.read_table('mixto.xlsx', xlsx_fixture(sheet, shared_strings=strings))
        self.assertEqual(result, [{'serie': '0000123', 'sap': '1003913', documents.normalize_header('cantidad'): '12'}])

    def test_blank_cells_keep_column_position(self):
        sheet = f'''<worksheet xmlns="{MAIN}"><sheetData>
        <row r="1"><c r="A1" t="inlineStr"><is><t>serie</t></is></c><c r="B1" t="inlineStr"><is><t>sap</t></is></c><c r="C1" t="inlineStr"><is><t>marca</t></is></c></row>
        <row r="2"><c r="A2" t="inlineStr"><is><t>0000456</t></is></c><c r="C2" t="inlineStr"><is><t>MARCA DEMO</t></is></c></row>
        </sheetData></worksheet>'''
        self.assertEqual(documents.read_table('huecos.xlsx', xlsx_fixture(sheet)), [{'serie': '0000456', 'sap': '', 'marca': 'MARCA DEMO'}])

    def test_formula_cells_rejected_instead_of_evaluated(self):
        sheet = f'''<worksheet xmlns="{MAIN}"><sheetData>
        <row r="1"><c r="A1" t="inlineStr"><is><t>serie</t></is></c></row>
        <row r="2"><c r="A2"><f>1+1</f><v>2</v></c></row>
        </sheetData></worksheet>'''
        with self.assertRaises(ValueError):
            documents.read_table('formulas.xlsx', xlsx_fixture(sheet))

    def test_external_relationships_rejected(self):
        sheet = inline_sheet(['serie'], [['0000123']])
        with self.assertRaises(ValueError):
            documents.read_table('externo.xlsx', xlsx_fixture(sheet, external=True))

    def test_macro_payload_rejected_even_under_xlsx_extension(self):
        sheet = inline_sheet(['serie'], [['0000123']])
        with self.assertRaises(ValueError):
            documents.read_table('macro.xlsx', xlsx_fixture(sheet, extra_files={'xl/vbaProject.bin': b'not a real macro'}))

    def test_invalid_xlsx_reports_value_error(self):
        with self.assertRaises(ValueError):
            documents.read_table('roto.xlsx', b'Esto no es un archivo de Excel')

    def test_duplicate_xlsx_headers_are_rejected(self):
        blob = xlsx_fixture(inline_sheet(['Serie', 'Número de medidor'], [['0001', '0002']]))
        with self.assertRaises(ValueError):
            documents.read_table('duplicados.xlsx', blob)


class ImportLimitsAndDateTests(unittest.TestCase):
    def test_configured_row_limit_applies_to_csv_and_xlsx(self):
        csv_data = b'serie\n0001\n0002\n'
        excel_data = xlsx_fixture(inline_sheet(['serie'], [['0001'], ['0002']]))
        with patch.object(documents, 'MAX_ROWS', 1):
            for filename, content in [('limite.csv', csv_data), ('limite.xlsx', excel_data)]:
                with self.subTest(filename=filename), self.assertRaises(ValueError):
                    documents.read_table(filename, content)

    def test_zip_uncompressed_limit_is_checked_before_reading_xml(self):
        content = xlsx_fixture(inline_sheet(['serie'], [['0001']]))
        with patch.object(documents, 'MAX_UNCOMPRESSED_BYTES', 100):
            with self.assertRaises(ValueError):
                documents.read_table('limite.xlsx', content)

    def test_input_and_column_limits(self):
        with patch.object(documents, 'MAX_INPUT_BYTES', 10):
            with self.assertRaises(ValueError):
                documents.read_table('grande.csv', b'serie\n00000000000001\n')
        with patch.object(documents, 'MAX_COLUMNS', 2):
            with self.assertRaises(ValueError):
                documents.read_table('ancho.csv', b'serie;sap;marca\n0001;1003913;DEMO\n')

    def test_xml_document_type_and_entity_are_rejected(self):
        unsafe = f'''<?xml version="1.0"?>
        <!DOCTYPE worksheet [<!ENTITY dato SYSTEM "https://example.invalid/dato">]>
        <worksheet xmlns="{MAIN}"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>&dato;</t></is></c></row></sheetData></worksheet>'''
        with self.assertRaises(ValueError):
            documents.read_table('entidad.xlsx', xlsx_fixture(unsafe))

    def test_day_first_csv_and_excel_1904_dates_are_iso(self):
        csv_rows = documents.read_table('fechas.csv', b'Fecha de trabajo;serie\n22/10/2026;0000123\n')
        self.assertEqual(csv_rows[0]['work_date'], '2026-10-22')
        styles = f'''<styleSheet xmlns="{MAIN}"><cellXfs count="2"><xf numFmtId="0"/><xf numFmtId="14"/></cellXfs></styleSheet>'''
        sheet = f'''<worksheet xmlns="{MAIN}"><sheetData>
        <row r="1"><c r="A1" t="inlineStr"><is><t>work_date</t></is></c><c r="B1" t="inlineStr"><is><t>serie</t></is></c></row>
        <row r="2"><c r="A2" s="1"><v>0</v></c><c r="B2" t="inlineStr"><is><t>0000123</t></is></c></row>
        </sheetData></worksheet>'''
        result = documents.read_table('fechas.xlsx', xlsx_fixture(sheet, extra_files={'xl/styles.xml': styles}, date1904=True))
        self.assertEqual(result, [{'work_date': '1904-01-01', 'serie': '0000123'}])


class PdfAndTemplateTests(unittest.TestCase):
    def test_pdf_is_paginated_and_has_consistent_xref(self):
        rows = [[str(index), 'Revisión técnica', 'Medidor de prueba'] for index in range(1, 201)]
        blob = documents.write_pdf(['ID', 'Actividad', 'Detalle'], rows, title='Producción y revisión')
        self.assertTrue(blob.startswith(b'%PDF-'))
        self.assertTrue(blob.rstrip().endswith(b'%%EOF'))
        self.assertGreater(len(re.findall(rb'/Type\s*/Page\b', blob)), 1)
        self.assertIn(b'Revisi\xf3n', blob)
        xref = re.search(rb'startxref\s+(\d+)\s+%%EOF', blob)
        self.assertIsNotNone(xref)
        self.assertEqual(blob[int(xref.group(1)):int(xref.group(1))+4], b'xref')

    def test_import_templates_include_traceability_fields(self):
        for activity in ('revision', 'sellado'):
            with self.subTest(activity=activity):
                columns = documents.template_columns(activity)
                self.assertEqual(len(columns), len(set(columns)))
                for required in ('work_date', 'responsible', 'serie', 'sap', 'marca', 'voltaje'):
                    self.assertIn(required, columns)
        self.assertIn('condicion', documents.template_columns('revision'))
        self.assertIn('clasificacion', documents.template_columns('sellado'))

    def test_unknown_template_is_rejected(self):
        with self.assertRaises(ValueError):
            documents.template_columns('actividad-inventada')


if __name__ == '__main__':
    unittest.main()
