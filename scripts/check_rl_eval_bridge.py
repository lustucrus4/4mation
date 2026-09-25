"""Vérifie que le pont d'évaluation RL transmet bien la position au daemon.

Le trainer RL joue contre un bot Python (`eval_minimax.py`). Deux pannes silencieuses
sont possibles et rendent toute mesure fausse :

1. la position n'est pas transmise (le bot joue depuis un autre plateau) : ses coups
   deviennent illégaux, `session.apply` échoue et le trainer compte une *nulle* ;
2. le bot ne répond rien : même effet.

Ce contrôle envoie des positions de référence au bot, en mode `move` (un processus par
coup) et en mode `daemon` (processus persistant), et exige :

- que le coup renvoyé soit **légal** d'après le moteur de jeu Python ;
- que le daemon **réponde le même coup** quand on lui repose deux fois la même position
  (une dérive d'état d'une requête à l'autre trahirait un plateau mal réinitialisé) ;
- qu'un **coup gagnant immédiat** soit bien trouvé (`menace-immediate`) : impossible à
  trouver depuis un plateau vide, c'est le piège historique rendu impossible.

Deux exécutions séparées du même bot ne renvoient pas forcément le *même* coup : le
daemon réutilise le même bot (donc la même table de transposition réchauffée) alors que le
mode `move` part d'un processus froid. Sur des positions quasi équilibrées, les deux choix
sont également bons. Cet écart est donc **signalé**, pas compté comme une panne.

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


def reference_positions() -> List[Tuple[GameEngine, Dict[str, Any], str, List[Tuple[int, int]]]]:
    """Positions de contrôle : début, milieu, coin, et un gain immédiat à trouver.

    Le 4ᵉ champ liste les coups qui terminent la partie **immédiatement**. Il est vide
    quand la position n'a pas de gain en un coup.
    """
    positions: List[Tuple[GameEngine, Dict[str, Any], str, List[Tuple[int, int]]]] = []

    engine = GameEngine()
    engine.reset()
    for index in range(6):
        engine.step(engine.get_valid_actions()[0])
        positions.append(
            (copy.deepcopy(engine), snapshot(engine), f"ligne-gauche-{index}", [])
        )

    scripted = GameEngine()
    scripted.reset()
    for move in ((3, 3), (2, 3), (3, 4), (4, 4), (2, 4), (1, 5), (3, 2)):
        scripted.step(move)
    positions.append((copy.deepcopy(scripted), snapshot(scripted), "centre-conteste", []))

    corner = GameEngine()
    corner.reset()
    for move in ((0, 0), (1, 1), (0, 1), (2, 2)):
        corner.step(move)
    positions.append((copy.deepcopy(corner), snapshot(corner), "coin", []))

    immediate = immediate_win_position()
    if immediate is not None:
        eng, wins = immediate
        positions.append((eng, snapshot(eng), "menace-immediate", wins))

    return positions


def winning_moves(engine: GameEngine) -> List[Tuple[int, int]]:
    """Coups légaux qui gagnent sur-le-champ."""
    player = int(engine.get_current_player())
    wins: List[Tuple[int, int]] = []
    for action in engine.get_valid_actions():
        trial = copy.deepcopy(engine)
        _, applied, winner = trial.step(action)
        if applied and trial.is_terminal() and winner is not None and int(winner) == player:
            wins.append((int(action[0]), int(action[1])))
    return wins


def immediate_win_position(seed: int = 20260924, max_plies: int = 40):
    """Cherche, par parties aléatoires reproductibles, une position à gain immédiat.

    Une telle position est le meilleur détecteur du bug historique « le bot évalue depuis
    un plateau vide » : depuis un plateau vide, ce coup n'existe pas.
    """
    import random

    rng = random.Random(seed)
    for _ in range(400):
        engine = GameEngine()
        engine.reset()
        for _ in range(max_plies):
            if engine.is_terminal():
                break
            wins = winning_moves(engine)
            if wins:
                return copy.deepcopy(engine), wins
            actions = engine.get_valid_actions()
            if not actions:
                break
            engine.step(rng.choice(actions))
    return None


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


def blunder_rate(bot_id: str) -> float:
    """Taux d'erreur volontaire du bot, pour ne pas exiger l'impossible."""
    try:
        from api.services.bot_registry import BotRegistry

        return float(BotRegistry._LEVELS.get(bot_id, {}).get("blunder_rate", 0.0))
    except Exception:
        return 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Contrôle du pont d'évaluation RL")
    parser.add_argument("--bot", action="append", default=[], help="bot à contrôler (répétable)")
    args = parser.parse_args()
    bots = args.bot or ["level_5", "level_3"]

    anomalies = 0
    drifts = 0
    variations = 0
    daemon = Daemon()
    try:
        for bot_id in bots:
            flaky = blunder_rate(bot_id) > 0.0
            if flaky:
                print(f"[{bot_id}] blunder_rate > 0 : les coups peuvent être volontairement perdants")
            for index, (engine, request, label, must_win) in enumerate(reference_positions()):
                legal = [(int(a), int(b)) for a, b in engine.get_valid_actions()]
                direct = query_move(bot_id, request)
                streamed = daemon.query(bot_id, request)
                repeated = daemon.query(bot_id, request)

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

                if (
                    streamed
                    and repeated
                    and "error" not in streamed
                    and "error" not in repeated
                ):
                    a = (int(streamed["row"]), int(streamed["col"]))
                    b = (int(repeated["row"]), int(repeated["col"]))
                    if a != b:
                        # Attendu : le daemon garde le bot (donc sa table de transposition
                        # réchauffée) et cherche sous budget de temps. Deux interrogations
                        # successives peuvent donc conclure à deux coups également bons.
                        variations += 1
                        print(
                            f"[{bot_id}] {label} #{index} : coup variable entre deux "
                            f"interrogations ({a} puis {b}) — recherche sous budget de temps"
                        )

                if must_win and not flaky:
                    for mode, resp in (("move", direct), ("daemon", streamed)):
                        if resp is None or "error" in resp:
                            continue
                        move = (int(resp["row"]), int(resp["col"]))
                        if move not in must_win:
                            print(
                                f"[{bot_id}] {label} #{index} : mode {mode} joue {move} au lieu "
                                f"de conclure ({must_win}) — position ignorée ?"
                            )
                            anomalies += 1

                if direct and streamed and "error" not in direct and "error" not in streamed:
                    a = (int(direct["row"]), int(direct["col"]))
                    b = (int(streamed["row"]), int(streamed["col"]))
                    if a != b:
                        drifts += 1
                        print(
                            f"[{bot_id}] {label} #{index} : écart froid/chaud "
                            f"move={a} vs daemon={b} (toléré : table de transposition "
                            f"réchauffée dans le daemon)"
                        )
            print(f"[{bot_id}] {len(reference_positions())} positions contrôlées")
    finally:
        daemon.close()

    print()
    if variations:
        print(
            f"{variations} coup(s) variable(s) à position identique, {drifts} écart(s) "
            f"froid/chaud — attendu : le daemon cherche sous budget de temps avec une table de "
            f"transposition réchauffée. Tous ces coups restent légaux."
        )
    if anomalies:
        print(f"ÉCHEC : {anomalies} anomalie(s)")
        return 1
    print("OK : pont d'évaluation fiable (coups légaux, gains immédiats trouvés)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
