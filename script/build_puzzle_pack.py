"""
Génère le pack de 30 puzzles (10 × 3 / 5 / 8 coups gagnants pour le joueur 1).

Usage:
    cd 4mation
    set PYTHONPATH=.;script
    python script/build_puzzle_pack.py
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "script"))

from game.game_engine import GameEngine

OUTPUT = ROOT / "api" / "data" / "puzzles.json"
HUMAN = 1
OPP = 2
TARGETS = {"easy": 3, "medium": 5, "hard": 8}
COUNTS = {"easy": 10, "medium": 10, "hard": 10}


def _engine_from_history(history: List[Dict[str, int]]) -> GameEngine:
    engine = GameEngine()
    engine.reset()
    for h in history:
        engine.step((int(h["row"]), int(h["col"])))
    return engine


def _history_moves(engine: GameEngine) -> List[Dict[str, int]]:
    return [
        {"player": int(e["player"]), "row": int(e["row"]), "col": int(e["col"])}
        for e in engine.get_move_history()
    ]


def _snapshot(engine: GameEngine) -> Dict[str, Any]:
    return engine.to_snapshot()


def _restore(snap: Dict[str, Any]) -> GameEngine:
    return GameEngine.from_snapshot(snap)


memo_force: Dict[Tuple[Any, ...], bool] = {}


def _engine_key(engine: GameEngine) -> Tuple[Any, ...]:
    state = engine.get_state()
    board = tuple(tuple(int(c) for c in row) for row in state.board.tolist())
    last = state.last_move_position
    last_key = (int(last[0]), int(last[1])) if last is not None else None
    winner = state.winner
    return (
        board,
        int(state.current_player),
        last_key,
        bool(state.is_terminal),
        int(winner) if winner is not None else -1,
    )


def _human_can_force_win(engine: GameEngine, human_moves_left: int) -> bool:
    key = (_engine_key(engine), human_moves_left)
    if key in memo_force:
        return memo_force[key]

    if engine.is_terminal():
        result = engine.get_winner() == HUMAN
        memo_force[key] = result
        return result
    valid = engine.get_valid_actions()
    if not valid:
        result = engine.get_winner() == HUMAN
        memo_force[key] = result
        return result

    cp = int(engine.get_current_player())
    if cp == HUMAN:
        if human_moves_left <= 0:
            memo_force[key] = False
            return False
        for move in valid:
            snap = _snapshot(engine)
            _, ok, _ = engine.step(move)
            if not ok:
                continue
            if engine.is_terminal():
                if engine.get_winner() == HUMAN:
                    memo_force[key] = True
                    return True
            elif _human_can_force_win(engine, human_moves_left - 1):
                memo_force[key] = True
                return True
            engine = _restore(snap)
        memo_force[key] = False
        return False

    for move in valid:
        snap = _snapshot(engine)
        _, ok, _ = engine.step(move)
        if not ok:
            continue
        if engine.is_terminal():
            if engine.get_winner() != HUMAN:
                memo_force[key] = False
                return False
            engine = _restore(snap)
            continue
        if not _human_can_force_win(engine, human_moves_left):
            engine = _restore(snap)
            memo_force[key] = False
            return False
        engine = _restore(snap)
    memo_force[key] = True
    return True


def _extract_line(engine: GameEngine, human_moves_left: int) -> Optional[List[Dict[str, int]]]:
    if engine.is_terminal():
        return [] if engine.get_winner() == HUMAN else None
    valid = engine.get_valid_actions()
    if not valid:
        return None

    cp = int(engine.get_current_player())
    if cp == HUMAN:
        if human_moves_left <= 0:
            return None
        ordered = sorted(valid, key=lambda m: (m[0], m[1]))
        random.shuffle(ordered)
        for move in ordered:
            snap = _snapshot(engine)
            _, ok, _ = engine.step(move)
            if not ok:
                continue
            if engine.is_terminal() and engine.get_winner() == HUMAN:
                return [{"player": HUMAN, "row": move[0], "col": move[1]}]
            tail = _extract_line(engine, human_moves_left - 1)
            if tail is not None:
                return [{"player": HUMAN, "row": move[0], "col": move[1]}] + tail
            engine = _restore(snap)
        return None

    best_line: Optional[List[Dict[str, int]]] = None
    ordered = sorted(valid, key=lambda m: (m[0], m[1]))
    random.shuffle(ordered)
    for move in ordered:
        snap = _snapshot(engine)
        _, ok, _ = engine.step(move)
        if not ok:
            continue
        if engine.is_terminal() and engine.get_winner() != HUMAN:
            engine = _restore(snap)
            continue
        tail = _extract_line(engine, human_moves_left)
        if tail is not None:
            candidate = [{"player": OPP, "row": move[0], "col": move[1]}] + tail
            if best_line is None or len(tail) > len(best_line):
                best_line = candidate
        engine = _restore(snap)
    return best_line


def _count_human_moves_in_line(line: List[Dict[str, int]]) -> int:
    return sum(1 for m in line if int(m["player"]) == HUMAN)


def _validate_puzzle(setup: List[Dict[str, int]], line: List[Dict[str, int]], target: int) -> bool:
    engine = _engine_from_history(setup)
    if engine.is_terminal() or int(engine.get_current_player()) != HUMAN:
        return False
    if _count_human_moves_in_line(line) != target:
        return False
    if not _human_can_force_win(engine, target):
        return False

    work = _engine_from_history(setup)
    for mv in line:
        if work.is_terminal():
            return False
        if int(work.get_current_player()) != int(mv["player"]):
            return False
        move = (int(mv["row"]), int(mv["col"]))
        if move not in work.get_valid_actions():
            return False
        work.step(move)
    return work.is_terminal() and work.get_winner() == HUMAN


def _random_setup(min_plies: int = 4, max_plies: int = 14) -> List[Dict[str, int]]:
    engine = GameEngine()
    engine.reset()
    plies = random.randint(min_plies, max_plies)
    for _ in range(plies):
        if engine.is_terminal():
            break
        valid = engine.get_valid_actions()
        if not valid:
            break
        engine.step(random.choice(valid))
    if engine.is_terminal() or int(engine.get_current_player()) != HUMAN:
        return []
    return _history_moves(engine)


def _try_add_puzzle(
    pack: List[Dict[str, Any]],
    seen: set[str],
    difficulty: str,
    target: int,
    setup: List[Dict[str, int]],
    line: List[Dict[str, int]],
) -> None:
    sig = json.dumps({"h": setup, "l": line}, sort_keys=True)
    if sig in seen:
        return
    seen.add(sig)
    found = sum(1 for p in pack if p["difficulty"] == difficulty) + 1
    pack.append(
        {
            "id": f"{difficulty}-{found:02d}",
            "difficulty": difficulty,
            "human_moves": target,
            "title": f"{'Facile' if difficulty == 'easy' else 'Intermédiaire' if difficulty == 'medium' else 'Difficile'} #{found}",
            "theme": "Victoire forcée",
            "history": setup,
            "player_to_move": HUMAN,
            "line": line,
        }
    )
    print(f"[{difficulty}] {found}/{COUNTS[difficulty]}", flush=True)


def _save_pack(pack: List[Dict[str, Any]]) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8")


def generate_pack(
    *,
    seed: int = 2026,
    max_attempts: int = 50000,
    only: str | None = None,
    existing: List[Dict[str, Any]] | None = None,
) -> List[Dict[str, Any]]:
    pack: List[Dict[str, Any]] = list(existing or [])
    seen: set[str] = set()
    for p in pack:
        seen.add(json.dumps({"h": p["history"], "l": p["line"]}, sort_keys=True))

    targets = {only: TARGETS[only]} if only else TARGETS
    attempt_budget = max_attempts if only != "hard" else 250000

    for difficulty, target in targets.items():
        min_plies = 4 if difficulty == "easy" else 6 if difficulty == "medium" else 10
        max_plies = 12 if difficulty == "easy" else 16 if difficulty == "medium" else 22
        found = 0
        attempts = 0

        for seed_offset in range(24 if difficulty == "hard" else 12):
            if found >= COUNTS[difficulty]:
                break
            random.seed(seed + seed_offset * 991)
            memo_force.clear()
            while found < COUNTS[difficulty] and attempts < attempt_budget:
                attempts += 1
                if difficulty == "hard" and attempts % 20 == 0:
                    print(f"[{difficulty}] recherche… {attempts} essais, {found}/{COUNTS[difficulty]}", flush=True)
                setup = _random_setup(min_plies, max_plies)
                if not setup:
                    continue
                engine = _engine_from_history(setup)
                if not _human_can_force_win(engine, target):
                    continue
                line = _extract_line(engine, target)
                if line is None or not _validate_puzzle(setup, line, target):
                    continue
                before = found
                _try_add_puzzle(pack, seen, difficulty, target, setup, line)
                found = sum(1 for p in pack if p["difficulty"] == difficulty)
                if found > before:
                    _save_pack(pack)

        if found < COUNTS[difficulty]:
            raise RuntimeError(f"Seulement {found}/{COUNTS[difficulty]} pour {difficulty}")
    return pack


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Génère le pack de puzzles 4mation")
    parser.add_argument("--only", choices=["easy", "medium", "hard"], help="Générer une seule difficulté")
    parser.add_argument("--merge", action="store_true", help="Compléter puzzles.json existant")
    args = parser.parse_args()

    existing: List[Dict[str, Any]] | None = None
    if args.merge and OUTPUT.is_file():
        existing = json.loads(OUTPUT.read_text(encoding="utf-8"))
        if args.only:
            existing = [p for p in existing if p["difficulty"] != args.only]

    pack = generate_pack(only=args.only, existing=existing)
    _save_pack(pack)
    print(f"OK — {len(pack)} puzzles → {OUTPUT}", flush=True)


if __name__ == "__main__":
    main()
