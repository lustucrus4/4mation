"""Verifie les chiffres cites dans les lecons ecrites a la main.

Le texte des lecons affirme des nombres (« 68 fenetres de 4 », poids heuristiques). Un
chiffre faux se lit comme un fait : on les recalcule ici depuis la definition.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "script"))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.check_learn_diagrams import FENETRES, TAILLE  # noqa: E402

compte = {
    "horizontales": sum(1 for cells in FENETRES if cells[0][0] == cells[1][0]),
    "verticales": sum(1 for cells in FENETRES if cells[0][1] == cells[1][1]),
}
compte["diagonales"] = len(FENETRES) - compte["horizontales"] - compte["verticales"]

print(f"Taille du plateau : {TAILLE}x{TAILLE}")
for nom, valeur in compte.items():
    print(f"  fenetres {nom:<13} : {valeur}")
print(f"  TOTAL fenetres de 4  : {len(FENETRES)}")
print()
print("Lecons qui citent un nombre de fenetres :")
from api.routes.learn import LESSONS  # noqa: E402

for lecon in LESSONS:
    for section in lecon["sections"]:
        if "fenêtre" in section["body"] and "68" in section["body"]:
            print(f"  {lecon['id']} / {section['heading']} : annonce 68, calcule {len(FENETRES)}")
