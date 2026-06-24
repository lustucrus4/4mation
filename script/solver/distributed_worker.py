#!/usr/bin/env python3
"""
Worker solveur distribué — claim → résolution rétrograde → submit.

Usage:
    python script/solver/distributed_worker.py \\
        --api-url https://api-4mation.lab211.fr \\
        --workers 16
"""

from __future__ import annotations

import argparse
import json
import logging
import multiprocessing as mp
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "script"
if str(SCRIPT) not in sys.path:
    sys.path.insert(0, str(SCRIPT))

from solver.retrograde_solver import RetrogradeSolver

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("distributed_worker")

DEFAULT_API = "https://api-4mation.lab211.fr"
IDLE_SLEEP_SEC = 5.0
STATS_INTERVAL_SEC = 30.0


def _api_request(
    method: str,
    url: str,
    payload: Optional[Dict[str, Any]] = None,
    token: Optional[str] = None,
    timeout: float = 60.0,
) -> Dict[str, Any]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["X-Solver-Worker-Token"] = token
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def _parse_last_move(raw: Any) -> Optional[tuple[int, int]]:
    if not raw or not isinstance(raw, dict):
        return None
    row = raw.get("row")
    col = raw.get("col")
    if row is None or int(row) < 0:
        return None
    return int(row), int(col if col is not None else -1)


def _solve_position(
    pos: Dict[str, Any],
    max_empty: int,
    position_timeout_sec: float,
) -> Optional[Dict[str, Any]]:
    board = np.array(pos["board_json"], dtype=np.int8)
    player = int(pos.get("player", 1))
    last_move = _parse_last_move(pos.get("last_move"))

    solver = RetrogradeSolver(max_empty=max_empty, position_timeout_sec=position_timeout_sec)
    solved = solver.solve_position(board, player, last_move)
    if solved is None:
        return None

    best_move = None
    if solved.best_move:
        best_move = {"row": solved.best_move[0], "col": solved.best_move[1]}

    return {
        "hash": pos["hash"],
        "result": solved.result,
        "win_rate": solved.win_rate,
        "best_move": best_move,
        "depth_remaining": solved.depth_remaining,
        "board_json": pos["board_json"],
        "player": player,
        "last_move": pos.get("last_move"),
    }


def worker_loop(
    api_url: str,
    worker_index: int,
    max_empty: int,
    position_timeout_sec: float,
    token: Optional[str],
    claim_batch: int,
    max_iterations: Optional[int] = None,
) -> None:
    hostname = socket.gethostname()
    worker_id = f"{hostname}-{os.getpid()}-{worker_index}"
    claim_url = f"{api_url.rstrip('/')}/api/solver/work/claim"
    submit_url = f"{api_url.rstrip('/')}/api/solver/work/submit"
    release_url = f"{api_url.rstrip('/')}/api/solver/work/release"

    solved_count = 0
    failed_count = 0
    last_stats = time.monotonic()

    logger.info("Worker %s démarré", worker_id)

    while True:
        if max_iterations is not None and solved_count >= max_iterations:
            logger.info("[%s] Limite %d atteinte — arrêt", worker_id, max_iterations)
            break
        try:
            resp = _api_request(
                "POST",
                claim_url,
                {"worker_id": worker_id, "count": claim_batch},
                token=token,
            )
            if not resp.get("success"):
                logger.warning("[%s] Claim échoué : %s", worker_id, resp.get("error"))
                time.sleep(IDLE_SLEEP_SEC)
                continue

            positions: List[Dict[str, Any]] = resp.get("positions") or []
            if not positions:
                time.sleep(IDLE_SLEEP_SEC)
                continue

            for pos in positions:
                try:
                    result = _solve_position(pos, max_empty, position_timeout_sec)
                    if result is None:
                        failed_count += 1
                        logger.warning("[%s] Résolution impossible %s", worker_id, pos.get("hash", "")[:10])
                        try:
                            _api_request(
                                "POST",
                                release_url,
                                {"worker_id": worker_id, "hash": pos.get("hash")},
                                token=token,
                            )
                        except Exception as rel_exc:
                            logger.warning("[%s] Release échoué : %s", worker_id, rel_exc)
                        continue
                    result["worker_id"] = worker_id
                    sub = _api_request("POST", submit_url, result, token=token)
                    if sub.get("success"):
                        solved_count += 1
                        logger.info(
                            "[%s] ✓ %s → %s (total=%d)",
                            worker_id,
                            pos.get("hash", "")[:10],
                            result["result"],
                            solved_count,
                        )
                    else:
                        failed_count += 1
                        logger.warning("[%s] Submit échoué : %s", worker_id, sub.get("error"))
                except Exception as exc:
                    failed_count += 1
                    logger.exception("[%s] Erreur position : %s", worker_id, exc)

        except Exception as exc:
            logger.warning("[%s] Erreur boucle : %s", worker_id, exc)
            time.sleep(IDLE_SLEEP_SEC)

        now = time.monotonic()
        if now - last_stats >= STATS_INTERVAL_SEC:
            logger.info("[%s] Stats — résolues=%d, échecs=%d", worker_id, solved_count, failed_count)
            last_stats = now


def run_workers(
    api_url: str,
    num_workers: int,
    max_empty: int,
    position_timeout_sec: float,
    token: Optional[str],
    claim_batch: int,
    max_iterations: Optional[int],
) -> None:
    if num_workers <= 1:
        worker_loop(
            api_url, 0, max_empty, position_timeout_sec, token, claim_batch, max_iterations
        )
        return

    processes: List[mp.Process] = []
    for i in range(num_workers):
        p = mp.Process(
            target=worker_loop,
            args=(
                api_url,
                i,
                max_empty,
                position_timeout_sec,
                token,
                claim_batch,
                max_iterations,
            ),
            daemon=True,
        )
        p.start()
        processes.append(p)
        logger.info("Processus worker %d lancé (pid=%s)", i, p.pid)

    try:
        while any(p.is_alive() for p in processes):
            time.sleep(1.0)
    except KeyboardInterrupt:
        logger.info("Arrêt demandé — fermeture des workers")
        for p in processes:
            p.terminate()
        for p in processes:
            p.join(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser(description="Worker solveur distribué 4mation")
    parser.add_argument("--api-url", default=os.environ.get("SOLVER_API_URL", DEFAULT_API))
    parser.add_argument("--workers", type=int, default=int(os.environ.get("SOLVER_WORKERS", "4")))
    parser.add_argument("--max-empty", type=int, default=int(os.environ.get("TABLEBASE_MAX_EMPTY", "49")))
    parser.add_argument("--position-timeout", type=float, default=30.0)
    parser.add_argument("--claim-batch", type=int, default=1)
    parser.add_argument("--token", default=os.environ.get("SOLVER_WORKER_TOKEN", ""))
    parser.add_argument("--max-iterations", type=int, default=None, help="Test : N itérations par worker")
    args = parser.parse_args()

    token = args.token.strip() or None
    logger.info(
        "Démarrage — api=%s, workers=%d, max_empty=%d, timeout=%.0fs",
        args.api_url,
        args.workers,
        args.max_empty,
        args.position_timeout,
    )

    run_workers(
        args.api_url,
        args.workers,
        args.max_empty,
        args.position_timeout,
        token,
        args.claim_batch,
        args.max_iterations,
    )


if __name__ == "__main__":
    mp.freeze_support()
    main()
