"""Verifie la presence des artefacts lus par build_lessons.py.

Sert a savoir si une regeneration des lecons reproduit le contenu actuel ou si elle
remplacerait des sections chiffrees par des textes de repli.
"""

from __future__ import annotations

from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
SOLVER = RACINE / "script" / "solver"

ARTEFACTS = [
    ("sonde profonde (preuve_profonde.json)", SOLVER / "preuve_profonde.json"),
    ("theorie du livre (opening_theory.json)", SOLVER / "opening_theory.json"),
    ("motifs de finales (final_patterns.json)", SOLVER / "final_patterns.json"),
    ("preuve du centre (forced_win_33.json)", SOLVER / "forced_win_33.json"),
    ("stabilite de la sonde (probe_runs/stability.json)", SOLVER / "probe_runs" / "stability.json"),
    ("schema 33 (schema_33_defenses.json)", SOLVER / "schema_33_defenses.json"),
    ("schema 00 (schema_00_defenses.json)", SOLVER / "schema_00_defenses.json"),
]

manquants = 0
for nom, chemin in ARTEFACTS:
    if chemin.exists():
        taille = chemin.stat().st_size
        print(f"  OK      {nom:<52} {taille:>10,} octets")
    else:
        manquants += 1
        print(f"  ABSENT  {nom:<52}")

print()
if manquants:
    print(
        f"{manquants} artefact(s) manquant(s) : regenerer les lecons remplacerait les "
        "sections chiffrees correspondantes par des textes de repli."
    )
else:
    print("Tous les artefacts sont presents : une regeneration reproduit le contenu.")
