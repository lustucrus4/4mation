"""Inventaire des schémas dans les leçons.

Compte, pour chaque leçon, les sections qui portent un schéma et liste celles qui n'en
ont pas — sert à mesurer la couverture avant d'en ajouter.
"""

from __future__ import annotations

import json
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
FICHIER = RACINE / "api" / "content" / "lessons_engine.json"

donnees = json.loads(FICHIER.read_text(encoding="utf-8"))
lecons = donnees["lessons"] if isinstance(donnees, dict) and "lessons" in donnees else donnees

print(f"Type racine : {type(donnees).__name__} | lecons : {len(lecons)}")
print()

total_sections = 0
total_schemas = 0
for lecon in lecons:
    sections = lecon.get("sections", [])
    avec = [s for s in sections if s.get("diagram")]
    total_sections += len(sections)
    total_schemas += len(avec)
    print(
        f"  {lecon['id']:<24} niveau={lecon.get('level', '?'):<14} "
        f"sections={len(sections):<3} schemas={len(avec)}"
    )

print()
print(f"TOTAL : {total_schemas} schemas pour {total_sections} sections")
print()
print("--- sections SANS schema ---")
for lecon in lecons:
    for i, section in enumerate(lecon.get("sections", [])):
        if not section.get("diagram"):
            print(f"  {lecon['id']:<24} #{i} : {section['heading']}")

print()
print("--- cles d'un schema existant ---")
for lecon in lecons:
    for section in lecon.get("sections", []):
        if section.get("diagram"):
            d = section["diagram"]
            print(f"  {sorted(d.keys())}  (board {len(d['board'])}x{len(d['board'][0])})")
            print(f"  caption: {d.get('caption')}")
            print(f"  highlights: {d.get('highlights') is not None}")
            break
    else:
        continue
    break
