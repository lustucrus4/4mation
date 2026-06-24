#!/usr/bin/env python3
"""
Worker solveur distribué — claim → résolution rétrograde → submit.

Optimisations :
- Session HTTP keep-alive (requests) avec repli urllib
- Submit par lot (submit-batch) quand disponible
- Réutilisation du RetrogradeSolver par batch
"""

from __future__ import annotations

import argparse
import http.client
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
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "script"
if str(SCRIPT) not in sys.path:
    sys.path.insert(0, str(SCRIPT))

from solver.retrograde_solver import RetrogradeSolver

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("distributed_worker")

DEFAULT_API = "https://api-4mation.lab211.fr"
IDLE_SLEEP_SEC = 5.0
STATS_INTERVAL_SEC = 30.0
API_TIMEOUT_SEC = float(os.environ.get("SOLVER_API_TIMEOUT", "120"))
API_MAX_RETRIES = int(os.environ.get("SOLVER_API_RETRIES", "4"))
API_RETRY_BASE_SLEEP = float(os.environ.get("SOLVER_API_RETRY_BASE_SLEEP", "0.5"))
API_RETRY_MAX_SLEEP = float(os.environ.get("SOLVER_API_RETRY_MAX_SLEEP", "2.0"))


class HttpClient:
    """Client HTTP avec connexion persistante (requests) ou repli urllib."""

    def __init__(self, token: Optional[str]) -> None:
        self._token = token
        self._session: Optional["requests.Session"] = None
        if _HAS_REQUESTS:
            session = requests.Session()
            retry = Retry(
                total=API_MAX_RETRIES,
                backoff_factor=API_RETRY_BASE_SLEEP,
                status_forcelist=(502, 503, 504),
                allowed_methods=["GET", "POST"],
            )
            adapter = HTTPAdapter(pool_connections=4, pool_maxsize=8, max_retries=retry)
            session.mount("https://", adapter)
            session.mount("http://", adapter)
            self._session = session

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._token:
            headers["X-Solver-Worker-Token"] = self._token
        return headers

    def post(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self._session is not None:
            resp = self._session.post(
                url,
                json=payload,
                headers=self._headers(),
                timeout=API_TIMEOUT_SEC,
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")
            return resp.json() if resp.text else {}

        return _urllib_post(url, payload, self._token)


def _is_retryable_api_error(exc: BaseException) -> bool:
    if isinstance(
        exc,
        (
            ConnectionResetError,
            ConnectionAbortedError,
            BrokenPipeError,
            TimeoutError,
            http.client.RemoteDisconnected,
        ),
    ):
        return True
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if reason is None:
            return True
        if isinstance(
            reason,
            (
                ConnectionResetError,
                ConnectionAbortedError,
                BrokenPipeError,
                TimeoutError,
                http.client.RemoteDisconnected,
            ),
        ):
            return True
        if isinstance(reason, OSError):
            if getattr(reason, "winerror", None) in (10054, 10053):
                return True
            if getattr(reason, "errno", None) in (104, 32, 54):
                return True
        msg = str(reason).lower()
        return "remote end closed" in msg or "connection reset" in msg
    return False


def _urllib_post(
    url: str,
    payload: Dict[str, Any],
    token: Optional[str],
) -> Dict[str, Any]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["X-Solver-Worker-Token"] = token
    data = json.dumps(payload).encode("utf-8")

    last_exc: Optional[BaseException] = None
    for attempt in range(API_MAX_RETRIES):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=API_TIMEOUT_SEC) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
        except Exception as exc:
            last_exc = exc
            if attempt + 1 >= API_MAX_RETRIES or not _is_retryable_api_error(exc):
                break
            sleep_sec = min(API_RETRY_BASE_SLEEP * (2**attempt), API_RETRY_MAX_SLEEP)
            time.sleep(sleep_sec)

    assert last_exc is not None
    raise last_exc


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
    solver: RetrogradeSolver,
) -> Optional[Dict[str, Any]]:
    board = np.array(pos["board_json"], dtype=np.int8)
    player = int(pos.get("player", 1))
    last_move = _parse_last_move(pos.get("last_move"))

    solver.clear_cache()
    solver.begin_position()
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


def _submit_batch(
    http: HttpClient,
    submit_url: str,
    submit_batch_url: str,
    worker_id: str,
    results: List[Dict[str, Any]],
) -> Tuple[int, int]:
    if not results:
        return 0, 0

    for r in results:
        r["worker_id"] = worker_id

    try:
        resp = http.post(
            submit_batch_url,
            {"worker_id": worker_id, "results": results},
        )
        if resp.get("success"):
            return int(resp.get("submitted", len(results))), int(resp.get("failed", 0))
    except RuntimeError as exc:
        if "404" not in str(exc):
            logger.warning("submit-batch échoué (%s) — repli unitaire", exc)

    ok = 0
    fail = 0
    for result in results:
        sub = http.post(submit_url, result)
        if sub.get("success"):
            ok += 1
        else:
            fail += 1
    return ok, fail


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
    base = api_url.rstrip("/")
    claim_url = f"{base}/api/solver/work/claim"
    submit_url = f"{base}/api/solver/work/submit"
    submit_batch_url = f"{base}/api/solver/work/submit-batch"
    release_url = f"{base}/api/solver/work/release"

    http = HttpClient(token)
    solver = RetrogradeSolver(max_empty=max_empty, position_timeout_sec=position_timeout_sec)

    solved_count = 0
    failed_count = 0
    last_stats = time.monotonic()
    last_idle_log = 0.0

    transport = "requests+keep-alive" if _HAS_REQUESTS else "urllib"
    logger.info("Worker %s démarré (HTTP: %s)", worker_id, transport)

    while True:
        if max_iterations is not None and solved_count >= max_iterations:
            logger.info("[%s] Limite %d atteinte — arrêt", worker_id, max_iterations)
            break
        try:
            resp = http.post(
                claim_url,
                {"worker_id": worker_id, "count": claim_batch},
            )
            if not resp.get("success"):
                logger.warning("[%s] Claim échoué : %s", worker_id, resp.get("error"))
                time.sleep(IDLE_SLEEP_SEC)
                continue

            positions: List[Dict[str, Any]] = resp.get("positions") or []
            if not positions:
                now = time.monotonic()
                if now - last_idle_log >= 60.0:
                    logger.info(
                        "[%s] En attente — file API vide",
                        worker_id,
                    )
                    last_idle_log = now
                time.sleep(IDLE_SLEEP_SEC)
                continue

            batch_results: List[Dict[str, Any]] = []
            release_hashes: List[str] = []

            for pos in positions:
                try:
                    result = _solve_position(pos, solver)
                    if result is None:
                        failed_count += 1
                        release_hashes.append(str(pos.get("hash", "")))
                        continue
                    batch_results.append(result)
                except Exception as exc:
                    failed_count += 1
                    logger.exception("[%s] Erreur position : %s", worker_id, exc)

            for h in release_hashes:
                if not h:
                    continue
                try:
                    http.post(release_url, {"worker_id": worker_id, "hash": h})
                except Exception as rel_exc:
                    logger.warning("[%s] Release échoué : %s", worker_id, rel_exc)

            if batch_results:
                ok, fail = _submit_batch(
                    http, submit_url, submit_batch_url, worker_id, batch_results
                )
                solved_count += ok
                failed_count += fail
                logger.info(
                    "[%s] Batch — %d soumis, %d échecs (total=%d)",
                    worker_id,
                    ok,
                    fail,
                    solved_count,
                )

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
    parser.add_argument("--claim-batch", type=int, default=int(os.environ.get("SOLVER_CLAIM_BATCH", "10")))
    parser.add_argument("--token", default=os.environ.get("SOLVER_WORKER_TOKEN", ""))
    parser.add_argument("--max-iterations", type=int, default=None, help="Test : N itérations par worker")
    args = parser.parse_args()

    token = args.token.strip() or None
    logger.info(
        "Démarrage — api=%s, workers=%d, batch=%d, max_empty=%d, timeout=%.0fs, http=%s",
        args.api_url,
        args.workers,
        args.claim_batch,
        args.max_empty,
        args.position_timeout,
        "requests" if _HAS_REQUESTS else "urllib",
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
