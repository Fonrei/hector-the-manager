#!/usr/bin/env python3
"""Lance les tests d'Hector the Manager.

Usage :
    python3 run_tests.py ../Hector_the_Manager_v1.9.3.html
    python3 run_tests.py ../Hector_the_Manager_v1.9.3.html --chrome "/chemin/vers/chrome"

Les options supplementaires sont passees a pytest (ex. -k write pour ne lancer
que les tests dont le nom contient "write", ou -v pour le detail).
"""
import pathlib
import sys

try:
    import pytest
    import playwright  # noqa: F401
except ImportError:
    sys.exit("Il manque pytest ou playwright. Installe-les avec :\n"
             "    python3 -m pip install pytest playwright\n"
             "    python3 -m playwright install chromium")

if len(sys.argv) < 2 or sys.argv[1].startswith("-"):
    sys.exit(__doc__)

here = pathlib.Path(__file__).resolve().parent
html = pathlib.Path(sys.argv[1]).expanduser().resolve()
sys.exit(pytest.main([str(here), "-q", "--tb=short", "--hector", str(html), *sys.argv[2:]]))
