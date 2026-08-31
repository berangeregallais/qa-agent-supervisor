"""La présence de ce fichier ajoute la racine du projet à sys.path (comme
dans maisoncarmenta-qa). On ajoute EN PLUS le projet cible
`maisoncarmenta-qa` lui-même, pour que les tests générés dans
tests/generated/ puissent faire `from pages.home_page import HomePage` en
réutilisant directement ses Page Objects, sans dupliquer aucun code.
"""

import sys
from pathlib import Path

TARGET_PROJECT = Path(__file__).resolve().parent.parent / "maisoncarmenta-qa"
if TARGET_PROJECT.exists() and str(TARGET_PROJECT) not in sys.path:
    sys.path.insert(0, str(TARGET_PROJECT))
