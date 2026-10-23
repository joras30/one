"""Run the standard suites and expose actionable failures in GitHub annotations."""
from pathlib import Path
import sys
import unittest


def annotation(text):
    return str(text).replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')


def main():
    root = Path(__file__).resolve().parents[1]
    suites = {'http': root / 'APLICACION_ACTUAL/tests', 'domain': root / 'tests'}
    if len(sys.argv) != 2 or sys.argv[1] not in suites:
        raise SystemExit('Usage: python tests/run_ci.py http|domain')
    suite = unittest.defaultTestLoader.discover(str(suites[sys.argv[1]]))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    summary = (f'Python {sys.version.split()[0]} / {sys.platform}: {result.testsRun} pruebas; '
               f'{len(result.failures)} fallos; {len(result.errors)} errores; {len(result.skipped)} omitidas.')
    print('::notice title=Resultados de pruebas::' + annotation(summary), flush=True)
    for test, detail in [*result.failures, *result.errors]:
        # Test fixtures contain synthetic data only. Avoid relying on access to
        # private log downloads when an owner reviews a public workflow run.
        message = test.id() + '\n' + detail[-12000:]
        print('::error title=Prueba automatizada fallida::' + annotation(message), flush=True)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()
