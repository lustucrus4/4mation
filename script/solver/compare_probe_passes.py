"""Compare plusieurs passes de la sonde d'ouverture et conclut sur leur fiabilité.

Pourquoi ce script existe
-------------------------
La sonde profonde (`probe_opening_proof.py`) chiffre les 10 premiers coups par une
recherche à budget de temps. Question légitime : ces chiffres sont-ils assez stables
pour qu'on publie un *classement* des ouvertures dans les cours ?

Mesure faite le 2026-09-25 : non. Sur les ouvertures jouées deux fois, le score change
de signe entre un budget de 90 s et un budget de 600 s (ex. `1,2` : -42 puis +5), et
l'ordre du classement est entièrement rebattu. Ce script reproduit cette comparaison à
partir des données déjà sur disque : il ne lance **aucun** calcul de moteur.

Entrées acceptées
-----------------
- un JSON de sonde (clé `ouvertures`, entrées `ouverture` + `score`) ;
- un journal texte de sonde au format `` `l,c` | meilleure réponse [...] | score N | ...``
  (les redirections PowerShell sont en UTF-16 et passent parfois par la page de code
  console : on décode les deux, on répare le mojibake courant, et on ne lit que la
  partie ASCII qui porte les scores).

Sortie
------
Un JSON consommé par `extract_opening_theory.py` et `build_lessons.py` pour expliquer
honnêtement la limite, plutôt que de publier un classement qui ne tient pas.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent  # racine du projet 4mation
OUT_DEFAULT = ROOT / "script" / "solver" / "probe_runs" / "stability.json"

# Le mojibake vient d'un texte UTF-8 relu en page de code console (CP850/CP437).
MOJIBAKE = {
    "\u251c\u00ae": "é",
    "\u251c\u00a8": "è",
    "\u251c\u00e1": "à",
    "\u251c\u00a2": "â",
    "\u251c\u00aa": "ê",
    "\u251c\u00af": "ï",
    "\u251c\u00a7": "ç",
    "\u251c\u00b4": "ô",
    "\u251c\u00b9": "ù",
    "\u251c\u00bb": "û",
}

SCORE_LINE = re.compile(r"`(\d),(\d)`")
SCORE_VALUE = re.compile(r"score\s+(-?\d+)")
DEPTH_VALUE = re.compile(r"profondeur\s+(\d+)")
BUDGET_VALUE = re.compile(r"\|\s*([\d.]+)\s*s")


def _repair(text: str) -> str:
    for bad, good in MOJIBAKE.items():
        text = text.replace(bad, good)
    return text


def _decode_log(raw: bytes) -> str:
    """Décode un journal de sonde quel que soit l'encodage de la redirection."""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw.decode("utf-16", errors="replace")
    else:
        text = raw.decode("utf-8", errors="replace")
    if "\x00" in text:
        text = raw.decode("utf-16-le", errors="replace")
    text = text.replace("\x00", "").replace("\r", "")
    return _repair(text)


def parse_source(path: Path) -> Dict[Tuple[int, int], Dict[str, int]]:
    """Scores d'une passe, indexés par ouverture."""
    raw = path.read_bytes()
    out: Dict[Tuple[int, int], Dict[str, int]] = {}

    if path.suffix.lower() == ".json":
        payload = json.loads(_decode_log(raw))
        for row in payload.get("ouvertures") or []:
            ouv = row.get("ouverture")
            if not ouv or row.get("erreur"):
                continue
            key = (int(ouv[0]), int(ouv[1]))
            entry = {"score": int(row["score"])}
            if row.get("profondeur") is not None:
                entry["profondeur"] = int(row["profondeur"])
            out[key] = entry
        return out

    text = _decode_log(raw)
    for m in SCORE_LINE.finditer(text):
        fenetre = text[m.end() : m.end() + 200]
        sc = SCORE_VALUE.search(fenetre)
        if not sc:
            continue
        key = (int(m.group(1)), int(m.group(2)))
        entry = {"score": int(sc.group(1))}
        dep = DEPTH_VALUE.search(fenetre)
        if dep:
            entry["profondeur"] = int(dep.group(1))
        bud = BUDGET_VALUE.search(fenetre)
        if bud:
            entry["budget_s"] = float(bud.group(1))
        out[key] = entry
    return out


def _cell(ouv: Optional[List[int]]) -> str:
    return f"({ouv[0]}, {ouv[1]})" if ouv else "?"


def build_report(sources: List[Tuple[str, Path]]) -> Dict:
    passes = []
    data: Dict[str, Dict[Tuple[int, int], Dict[str, int]]] = {}
    for label, path in sources:
        scores = parse_source(path)
        data[label] = scores
        budgets = sorted({v.get("budget_s") for v in scores.values() if v.get("budget_s")})
        passes.append(
            {
                "label": label,
                "source": str(path),
                "ouvertures_mesurees": len(scores),
                "budget_s": budgets[0] if len(budgets) == 1 else None,
            }
        )

    labels = [p["label"] for p in passes]
    communes = sorted(set.intersection(*(set(d) for d in data.values()))) if data else []

    ouvertures = []
    for key in communes:
        valeurs = {lab: data[lab][key]["score"] for lab in labels}
        mini, maxi = min(valeurs.values()), max(valeurs.values())
        signes = {1 if v > 0 else -1 if v < 0 else 0 for v in valeurs.values()}
        ecart = maxi - mini
        ouvertures.append(
            {
                "ouverture": [key[0], key[1]],
                "scores": valeurs,
                "min": mini,
                "max": maxi,
                "ecart": ecart,
                # Un simple changement de signe autour de zéro (±7 points) n'est pas une
                # instabilité : c'est le bruit normal d'une position équilibrée. On ne
                # parle d'instabilité que si l'amplitude dépasse le seuil de lecture de
                # ±20 points utilisé par le calibrage.
                "verdict_inverse": len(signes) > 1,
                "instable": ecart >= 20,
                "profondeurs": {
                    lab: data[lab][key].get("profondeur") for lab in labels
                },
            }
        )

    def classement(lab: str) -> List[List]:
        rows = sorted(data[lab].items(), key=lambda kv: kv[1]["score"])
        return [[list(k), v["score"]] for k, v in rows]

    classements = {lab: classement(lab) for lab in labels}
    ordre_identique = None
    if len(labels) >= 2:
        ordre_identique = all(
            [o for o, _ in classements[lab] if o in [list(k) for k in communes]]
            == [o for o, _ in classements[labels[0]] if o in [list(k) for k in communes]]
            for lab in labels[1:]
        )

    instables = [o for o in ouvertures if o["instable"]]
    inverses = [o for o in ouvertures if o["verdict_inverse"]]
    if not ouvertures:
        verdict = "aucune ouverture mesurée par au moins deux passes : rien à conclure"
    elif instables or ordre_identique is False:
        verdict = (
            "les scores ne sont pas reproductibles : "
            f"{len(instables)} ouverture(s) sur {len(ouvertures)} varient de plus de 20 points "
            f"entre deux passes ({len(inverses)} changent même de signe) et l'ordre du "
            "classement change. Aucun classement ne doit être publié ; seule la valeur "
            "prouvée du centre est enseignable."
        )
    else:
        verdict = "scores stables entre ces passes sur les ouvertures communes"

    return {
        "genere_le": datetime.now().isoformat(timespec="seconds"),
        "passes": passes,
        "ouvertures": ouvertures,
        "classements": classements,
        "ordre_identique": ordre_identique,
        "verdict": verdict,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--passe",
        action="append",
        required=True,
        metavar="LABEL=CHEMIN",
        help="Une passe à comparer (répétable, au moins deux pour conclure)",
    )
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    args = ap.parse_args()

    sources: List[Tuple[str, Path]] = []
    for spec in args.passe:
        label, _, raw_path = spec.partition("=")
        sources.append((label.strip(), Path(raw_path.strip())))

    report = build_report(sources)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for p in report["passes"]:
        print(f"passe « {p['label']} » : {p['ouvertures_mesurees']} ouverture(s) — {p['source']}")
    print()
    print("ouverture | " + " | ".join(p["label"] for p in report["passes"]) + " | écart | verdict")
    for o in report["ouvertures"]:
        scores = " | ".join(str(o["scores"][p["label"]]) for p in report["passes"])
        if o["instable"]:
            flag = "INSTABLE"
        elif o["verdict_inverse"]:
            flag = "signe seul"
        else:
            flag = "-"
        print(f"  {_cell(o['ouverture'])}   | {scores} | {o['ecart']} | {flag}")
    print()
    print("verdict :", report["verdict"])
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
