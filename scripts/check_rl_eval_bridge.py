"""Vérifie que le pont d'évaluation RL transmet bien la position au daemon.

Le trainer RL joue contre un bot Python (`eval_minimax.py`). Deux pannes silencieuses
sont possibles et rendent toute mesure fausse :

1. la position n'est pas transmise (le bot joue depuis un autre plateau) : ses coups
   deviennent illégaux, `session.apply` échoue et le trainer compte une *nulle* ;
2. le bot ne répond rien : même effet.

Ce contrôle envoie des positions de référence au bot, en mode `move` (un processus par
coup) et en mode `daemon` (processus persistant), et exige :

- que le coup renvoyé soit légal d'après le moteur de jeu Python ;
- que les deux modes renvoient le même coup (le daemon ne doit pas dériver).

    python scripts/check_rl_eval_bridge.py --bot level_5 --bot level_3
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "script"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from game.game_engine import GameEngine  # noqa: E402

DAEMON = ROOT / "script" / "rl_rust" / "eval_minimax.py"


def snapshot(engine: GameEngine) -> Dict[str, Any]:
    state = engine.get_state()
    last = state.last_move_position
    return {
        "board": [[int(v) for v in row] for row in state.board],
        "current_player": int(state.current_player),
        "last_move": [int(last[0]), int(last[1])] if last else None,
    }


def reference_positions() -> List[Tuple[GameEngine, Dict[str, Any], str]]:
    """Positions de contrôle : début de partie, milieu de partie, position forcée."""
    positions: List[Tuple[GameEngine, Dict[str, Any], str]] = []

    engine = GameEngine()
    engine.reset()
    for index in range(6):
        engine.step(engine.get_valid_actions()[0])
        positions.append((copy.deepcopy(engine), snapshot(engine), f"ligne-gauche-{index}"))

    scripted = GameEngine()
    scripted.reset()
    for move in ((3, 3), (2, 3), (3, 4), (4, 4), (2, 4), (1, 5), (3, 2)):
        scripted.step(move)
    positions.append((copy.deepcopy(scripted), snapshot(scripted), "centre-conteste"))

    corner = GameEngine()
    corner.reset()
    for move in ((0, 0), (1, 1), (0, 1), (2, 2)):
        corner.step(move)
    positions.append((copy.deepcopy(corner), snapshot(corner), "coin"))

    return positions


def query_move(bot_id: str, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Un processus Python par coup (mode `move`)."""
    proc = subprocess.run(
        [sys.executable, "-u", str(DAEMON), "move"],
        input=json.dumps(dict(request, bot_id=bot_id)),
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(ROOT),
        timeout=300,
    )
    if not proc.stdout.strip():
        return {"error": f"sans réponse (code {proc.returncode}) {proc.stderr.strip()[:200]}"}
    return json.loads(proc.stdout.strip().splitlines()[-1])


class Daemon:
    """Processus persistant (mode `daemon`)."""

    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, "-u", str(DAEMON), "daemon"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(ROOT),
            text=True,
            encoding="utf-8",
        )

    def query(self, bot_id: str, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(json.dumps(dict(request, bot_id=bot_id)) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            return {"error": "daemon mort"}
        return json.loads(line)

    def close(self) -> None:
        if self.proc.stdin:
            self.proc.stdin.close()
        self.proc.wait(timeout=30)


def main() -> int:
    parser = argparse.ArgumentParser(description="Contrôle du pont d'évaluation RL")
    parser.add_argument("--bot", action="append", default=[], help="bot à contrôler (répétable)")
    args = parser.parse_args()
    bots = args.bot or ["level_5", "level_3"]

    anomalies = 0
    daemon = Daemon()
    try:
        for bot_id in bots:
            for index, (engine, request, label) in enumerate(reference_positions()):
                legal = [(int(a), int(b)) for a, b in engine.get_valid_actions()]
                direct = query_move(bot_id, request)
                streamed = daemon.query(bot_id, request)

                for mode, resp in (("move", direct), ("daemon", streamed)):
                    if resp is None or "error" in resp:
                        print(f"[{bot_id}] {label} : mode {mode} en échec -> {resp}")
                        anomalies += 1
                        continue
                    move = (int(resp["row"]), int(resp["col"]))
                    if move not in legal:
                        print(
                            f"[{bot_id}] {label} #{index} : mode {mode} renvoie {move}, "
                            f"illégal (ex. {legal[:3]}…)"
                        )
                        anomalies += 1

                if direct and streamed and "error" not in direct and "error" not in streamed:
                    a = (int(direct["row"]), int(direct["col"]))
                    b = (int(streamed["row"]), int(streamed["col"]))
                    if a != b:
                        print(f"[{bot_id}] {label} #{index} : move={a} vs daemon={b}")
                        anomalies += 1
            print(f"[{bot_id}] {len(reference_positions())} positions contrôlées")
    finally:
        daemon.close()

    if anomalies:
        print(f"ÉCHEC : {anomalies} anomalie(s)")
        return 1
    print("OK : pont d'évaluation fiable (coups légaux et cohérents dans les deux modes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
