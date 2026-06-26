#!/usr/bin/env python3
"""
Helper Python pour RL Rust — coups Minimax et imitation bootstrap.

Usage:
  py eval_minimax.py move          # stdin JSON → stdout JSON {row, col}
  py eval_minimax.py imitate --games 300 --depth 7  # stdout JSONL features
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "script"
for p in (str(ROOT), str(SCRIPT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np
from game.game_engine import GameEngine
from game_tree.optimized_minimax import OptimizedMinimaxAdvisor
from api.services.bot_registry import BotRegistry

bot_registry = BotRegistry()


def _board_from_json(rows: List[List[int]]) -> np.ndarray:
    return np.array(rows, dtype=np.int8)


def _last_move(data: dict) -> Optional[Tuple[int, int]]:
    lm = data.get("last_move")
    if lm is None:
        return None
    return (int(lm[0]), int(lm[1]))


def _engine_from_request(data: dict) -> GameEngine:
    board = _board_from_json(data["board"])
    player = int(data.get("current_player", 1))
    engine = GameEngine()
    engine.board = board.copy()
    engine.current_player = player
    lm = _last_move(data)
    if lm is not None:
        engine.last_move = lm
    return engine


def cmd_move() -> None:
    raw = sys.stdin.read()
    data = json.loads(raw)
    bot_id = data.get("bot_id", "level_5")
    engine = _engine_from_request(data)
    move = bot_registry.choose_move(bot_id, engine)
    if move is None:
        valid = engine.get_valid_actions()
        move = valid[0] if valid else (0, 0)
    print(json.dumps({"row": int(move[0]), "col": int(move[1])}))


def _move_features(board: np.ndarray, mv: Tuple[int, int], player: int, last_move) -> List[float]:
    """Mirror simplifié des features Rust (12 dims)."""
    opponent = 3 - player
    r, c = mv
    size = board.shape[0]
    test = board.copy()
    test[r, c] = player

    def is_win(b, mv2, p):
        row, col = mv2
        tb = b.copy()
        tb[row, col] = p
        for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
            cnt = 1
            for step in (1, -1):
                rr, cc = row, col
                for _ in range(3):
                    rr += dr * step
                    cc += dc * step
                    if 0 <= rr < size and 0 <= cc < size and tb[rr, cc] == p:
                        cnt += 1
                    else:
                        break
            if cnt >= 4:
                return True
        return False

    win_now = 1.0 if is_win(board, mv, player) else 0.0
    block = 1.0 if is_win(board, mv, opponent) else 0.0
    center = (size - 1) / 2.0
    dist = ((r - center) ** 2 + (c - center) ** 2) ** 0.5 / (center * 2**0.5)
    friends = enemies = 0
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            nr, nc = r + dr, c + dc
            if 0 <= nr < size and 0 <= nc < size:
                cell = board[nr, nc]
                if cell == player:
                    friends += 1
                elif cell != 0:
                    enemies += 1
    empty = int(np.sum(board == 0))
    fill = 1.0 - empty / (size * size)
    player_sign = 1.0 if player == 1 else -1.0
    return [
        win_now,
        block,
        1.0 - dist,
        friends / 8.0,
        enemies / 8.0,
        0.5,
        0.5,
        0.0,
        0.0,
        fill,
        player_sign,
        0.0,
    ]


def cmd_imitate(games: int, depth: int) -> None:
    advisor = OptimizedMinimaxAdvisor(depth=depth, use_iterative_deepening=True)
    rng = random.Random(42)

    for g in range(games):
        engine = GameEngine()
        while not engine.is_terminal():
            valid = engine.get_valid_actions()
            if not valid:
                break
            state = engine.get_state()
            last = None
            if state.action_history:
                _, lr, lc = state.action_history[-1]
                last = (int(lr), int(lc))
            try:
                analysis = advisor.analyze_position(
                    state.board,
                    current_player=int(state.current_player),
                    last_move=last,
                    include_move_scores=False,
                )
                best = analysis.get("best_move")
                if best:
                    mv = (int(best[0]), int(best[1]))
                    if mv in valid:
                        feats = _move_features(state.board, mv, int(state.current_player), last)
                        print(
                            json.dumps(
                                {
                                    "features": feats,
                                    "target_move_idx": 0,
                                    "legal_count": len(valid),
                                }
                            ),
                            flush=True,
                        )
                        engine.step(mv)
                        continue
            except Exception:
                pass
            mv = rng.choice(valid)
            feats = _move_features(state.board, mv, int(state.current_player), last)
            print(
                json.dumps(
                    {"features": feats, "target_move_idx": 0, "legal_count": len(valid)}
                ),
                flush=True,
            )
            engine.step(mv)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("move")
    p_im = sub.add_parser("imitate")
    p_im.add_argument("--games", type=int, default=300)
    p_im.add_argument("--depth", type=int, default=7)
    args = parser.parse_args()

    if args.cmd == "move":
        cmd_move()
    elif args.cmd == "imitate":
        cmd_imitate(args.games, args.depth)


if __name__ == "__main__":
    main()
