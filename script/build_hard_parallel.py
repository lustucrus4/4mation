"""Complète les puzzles difficiles en parallèle."""

from __future__ import annotations

import json
import multiprocessing as mp
import random
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "script"))

from script.build_puzzle_pack import (  # noqa: E402
    COUNTS,
    HUMAN,
    OUTPUT,
    OPP,
    _engine_from_history,
    _extract_line,
    _human_can_force_win,
    _random_setup,
    _save_pack,
    _validate_puzzle,
    memo_force,
)


def _find_hard_batch(seed: int, target_count: int = 2, max_attempts: int = 800) -> List[Dict[str, Any]]:
    random.seed(seed)
    memo_force.clear()
    found: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for _ in range(max_attempts):
        if len(found) >= target_count:
            break
        setup = _random_setup(10, 22)
        if not setup:
            continue
        engine = _engine_from_history(setup)
        if not _human_can_force_win(engine, 8):
            continue
        line = _extract_line(engine, 8)
        if line is None or not _validate_puzzle(setup, line, 8):
            continue
        sig = json.dumps({"h": setup, "l": line}, sort_keys=True)
        if sig in seen:
            continue
        seen.add(sig)
        found.append(
            {
                "difficulty": "hard",
                "human_moves": 8,
                "title": "",
                "theme": "Victoire forcée",
                "history": setup,
                "player_to_move": HUMAN,
                "line": line,
            }
        )
    return found


def main() -> None:
    existing: List[Dict[str, Any]] = []
    if OUTPUT.is_file():
        existing = [p for p in json.loads(OUTPUT.read_text(encoding="utf-8")) if p["difficulty"] != "hard"]

    need = COUNTS["hard"]
    collected: List[Dict[str, Any]] = []
    seen: set[str] = set()
    seed_base = 8800
    round_idx = 0

    while len(collected) < need and round_idx < 40:
        seeds = [seed_base + round_idx * 16 + i for i in range(8)]
        with mp.Pool(processes=8) as pool:
            batches = pool.starmap(
                _find_hard_batch,
                [(s, 2, 600) for s in seeds],
            )
        for batch in batches:
            for item in batch:
                sig = json.dumps({"h": item["history"], "l": item["line"]}, sort_keys=True)
                if sig in seen:
                    continue
                seen.add(sig)
                collected.append(item)
                print(f"[hard] {len(collected)}/{need}", flush=True)
                if len(collected) >= need:
                    break
        round_idx += 1

    if len(collected) < need:
        raise RuntimeError(f"Seulement {len(collected)}/{need} puzzles difficiles")

    for i, puzzle in enumerate(collected[:need], start=1):
        puzzle["id"] = f"hard-{i:02d}"
        puzzle["title"] = f"Difficile #{i}"

    pack = existing + collected[:need]
    _save_pack(pack)
    print(f"OK — {len(pack)} puzzles → {OUTPUT}", flush=True)


if __name__ == "__main__":
    mp.freeze_support()
    main()
