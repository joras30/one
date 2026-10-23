"""Intercambio V6: modelo separado y actas completas, con datos ficticios."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'APLICACION_ACTUAL'))
import documents


class V6DocumentsTests(unittest.TestCase):
    def test_official_templates_roundtrip_brand_model_and_calibration(self):
        for activity in ('revision', 'sellado'):
            with self.subTest(activity=activity):
                headers = documents.template_columns(activity)
                sample = {'work_date': '2026-10-23', 'responsible': '009001', 'serie': '0000123',
                          'marca': 'Marca ficticia', 'modelo': 'Modelo 001', 'sap': '001003913',
                          'sap_config_id': 'configuracion-prueba', 'valor_referencia': '100',
                          'valor_medido': '99.5', 'tolerancia_pct': '1'}
                values = [[sample.get(key, '') for key in headers]]
                for extension, writer in (('csv', documents.write_csv), ('xlsx', documents.write_xlsx)):
                    result = documents.read_table('plantilla.' + extension, writer(headers, values))
                    self.assertEqual(result[0]['marca'], 'Marca ficticia')
                    self.assertEqual(result[0]['modelo'], 'Modelo 001')
                    self.assertEqual(result[0]['serie'], '0000123')
                    self.assertEqual(result[0]['sap'], '001003913')
                    if activity == 'revision':
                        self.assertEqual(result[0]['valor_medido'], '99.5')

    def test_certificate_exports_every_delivery_and_its_frozen_hash(self):
        certificate = {'id': 1, 'number': 'ACTA-FICTICIA-001', 'created_at': '2026-10-23T12:00:00Z',
                       'hash': 'ab' * 32,
                       'snapshot': {'process': 'PROC-FICTICIO-001', 'received': 300,
                                    'deliveries': [{'work_date': '2026-10-23', 'quantity': 1,
                                                   'serie': f'000SERIE{i:04d}'} for i in range(300)]}}
        headers, rows, title = documents.certificate_table(certificate)
        report = documents.write_pdf(headers, rows, title)
        self.assertTrue(report.startswith(b'%PDF-'))
        self.assertIn(b'ACTA-FICTICIA-001', report)
        self.assertIn(('ab' * 32).encode(), report)
        self.assertIn(b'000SERIE0000', report)
        self.assertIn(b'000SERIE0299', report)

    def test_incomplete_certificate_is_rejected(self):
        with self.assertRaises(ValueError):
            documents.certificate_table({'number': 'FICTICIO'})


if __name__ == '__main__':
    unittest.main()
