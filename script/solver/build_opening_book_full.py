#!/usr/bin/env python3
"""
Construction longue durée du livre d'ouverture 4mation (cible ~2 Go).

Même principe que l'endgame : boucle continue, heartbeat vers solver_progress +
solver_status.json, affichage sur la vue « Avancement solveur ».

Adossé à la tablebase existante (`positions`) : promotion exacte maximale, puis
estimations Minimax+MCTS profondes pour le reste.

Usage:
    python script/solver/build_opening_book_full.py [--db PATH] [--target-gb 2]
        [--fresh] [--max-ply 18]

Prérequis : arrêter le solveur Rust endgame pendant la construction (écriture SQLite).
Le dashboard local (port 8765) ou solver.html en prod affiche la progression.
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "script"
if str(SCRIPT) not in sys.path:
    sys.path.insert(0, str(SCRIPT))

from solver.build_opening_book import DEFAULT_DB, build_opening_book
from solver.db_schema import init_db
from solver.solver_status import (
    append_recent,
    position_entry,
    read_status,
    write_status,
)

# Cible de stockage du livre d'ouverture (octets).
DEFAULT_TARGET_BYTES = 2 * 1024 * 1024 * 1024
# Estimation initiale si pas encore assez d'entrées pour mesurer.
DEFAULT_BYTES_PER_ENTRY = 420.0

# Vagues successives : (max_ply, max_positions, refresh_estimates)
WAVES: List[tuple[int, int, bool]] = [
    (14, 80_000, False),
    (16, 200_000, False),
    (18, 400_000, False),
    (18, 600_000, True),
    (20, 800_000, True),
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("opening_book_full")


def _db_total_bytes(db_path: Path) -> int:
    total = db_path.stat().st_size if db_path.exists() else 0
    for suffix in ("-wal", "-shm"):
        p = Path(f"{db_path}{suffix}")
        if p.exists():
            total += p.stat().st_size
    return total


def _opening_book_table_bytes(conn) -> int:
    try:
        row = conn.execute(
            "SELECT SUM(pgsize) FROM dbstat WHERE name='opening_book'"
        ).fetchone()
        if row and row[0]:
            return int(row[0])
    except Exception:
        pass
    return 0


def _opening_book_count(conn) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM opening_book").fetchone()[0])


def _opening_exact_count(conn) -> int:
    return int(
        conn.execute("SELECT COUNT(*) FROM opening_book WHERE exact=1").fetchone()[0]
    )


def _estimate_bytes_per_entry(conn, fallback: float) -> float:
    count = _opening_book_count(conn)
    if count < 500:
        return fallback
    pages = _opening_book_table_bytes(conn)
    if pages > 0:
        return max(180.0, pages / count)
    return fallback


def _update_solver_progress(
    conn,
    *,
    total_solved: int,
    total_target: int,
    progress_percent: float,
    started_at: str,
    running: bool,
) -> None:
    conn.execute(
        """
        INSERT INTO solver_progress
        (id, total_queued, total_solved, last_hash, started_at, current_phase,
         solver_running, total_target, progress_percent, updated_at)
        VALUES (1, 0, ?, '', ?, 'opening_book', ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            total_queued=0,
            total_solved=excluded.total_solved,
            current_phase='opening_book',
            solver_running=excluded.solver_running,
            total_target=excluded.total_target,
            progress_percent=excluded.progress_percent,
            updated_at=CURRENT_TIMESTAMP
        """,
        (total_solved, started_at, 1 if running else 0, total_target, progress_percent),
    )


class OpeningBookProgress:
    """Publie l'avancement vers SQLite + solver_status.json."""

    def __init__(
        self,
        db_path: Path,
        target_bytes: int,
        progress_interval: float = 15.0,
    ) -> None:
        self.db_path = db_path
        self.target_bytes = target_bytes
        self.progress_interval = progress_interval
        self.started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.started_mono = time.monotonic()
        self.recent: list = list(read_status().get("recent_positions") or [])
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._last_publish = 0.0
        self._session_stored = 0
        self._session_start_count = 0
        self._bytes_per_entry = DEFAULT_BYTES_PER_ENTRY

    def start(self) -> None:
        conn = init_db(self.db_path)
        self._session_start_count = _opening_book_count(conn)
        self._bytes_per_entry = _estimate_bytes_per_entry(conn, DEFAULT_BYTES_PER_ENTRY)
        self._publish(conn, force=True, running=True)
        conn.close()
        self._heartbeat = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat.start()

    def stop(self, running: bool = False) -> None:
        self._stop.set()
        if hasattr(self, "_heartbeat"):
            self._heartbeat.join(timeout=3.0)
        conn = init_db(self.db_path)
        self._publish(conn, force=True, running=running)
        conn.close()

    def on_wave_progress(self, info: dict) -> None:
        with self._lock:
            self._session_stored += 1
            board = info.get("last_board")
            if board is not None and info.get("last_hash"):
                entry = position_entry(
                    hash_key=str(info["last_hash"]),
                    board=board,
                    current_player=int(info.get("last_player") or 1),
                    last_move=info.get("last_move"),
                    best_move=info.get("last_best"),
                    result=str(info.get("last_result") or "D"),
                    win_rate=float(info.get("last_win_rate") or 0.5),
                )
                self.recent = append_recent(self.recent, entry)
            now = time.monotonic()
            if now - self._last_publish < self.progress_interval:
                return
            conn = init_db(self.db_path)
            self._publish(conn, running=True)
            conn.close()
            self._last_publish = now

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(self.progress_interval):
            with self._lock:
                conn = init_db(self.db_path)
                self._publish(conn, running=True)
                conn.close()
                self._last_publish = time.monotonic()

    def _publish(self, conn, *, force: bool = False, running: bool = True) -> None:
        count = _opening_book_count(conn)
        exact = _opening_exact_count(conn)
        table_bytes = _opening_book_table_bytes(conn)
        if count >= 500 and table_bytes > 0:
            self._bytes_per_entry = max(180.0, table_bytes / count)

        fill_bytes = max(table_bytes, int(count * self._bytes_per_entry))
        fill_pct = min(100.0, 100.0 * fill_bytes / self.target_bytes)
        target_entries = max(1, int(self.target_bytes / self._bytes_per_entry))

        elapsed = max(time.monotonic() - self.started_mono, 0.001)
        session_added = count - self._session_start_count
        rate = session_added / elapsed if session_added > 0 else 0.0
        eta = None
        if rate > 0 and fill_bytes < self.target_bytes:
            remaining = (self.target_bytes - fill_bytes) / self._bytes_per_entry
            eta = int(remaining / rate)

        _update_solver_progress(
            conn,
            total_solved=count,
            total_target=target_entries,
            progress_percent=round(fill_pct, 4),
            started_at=self.started_at,
            running=running,
        )
        conn.commit()

        payload = {
            "solver_running": running,
            "started_at": self.started_at,
            "last_update": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "current_phase": "opening_book",
            "max_empty": None,
            "total_positions_solved": count,
            "total_positions_target": target_entries,
            "total_queued": 0,
            "progress_percent": round(fill_pct, 4),
            "progress_unknown": False,
            "positions_per_second": round(rate, 2),
            "eta_seconds": eta,
            "opening_book_exact": exact,
            "opening_book_bytes": fill_bytes,
            "opening_book_target_bytes": self.target_bytes,
            "db_size_limit_bytes": self.target_bytes,
            "db_fill_percent": round(fill_pct, 4),
            "recent_positions": self.recent,
        }
        write_status(payload)

        if force or self._session_stored % 50 == 0:
            logger.info(
                "Livre d'ouverture : %s entrées (exact=%s) — %.1f %% vers %.1f Go "
                "(%.2f entrées/s)",
                f"{count:,}".replace(",", " "),
                f"{exact:,}".replace(",", " "),
                fill_pct,
                self.target_bytes / 1e9,
                rate,
            )


def run_opening_book_full(
    db_path: Path,
    target_bytes: int = DEFAULT_TARGET_BYTES,
    fresh: bool = False,
    waves: Optional[List[tuple[int, int, bool]]] = None,
    progress_interval: float = 15.0,
) -> None:
    conn = init_db(db_path)
    if fresh:
        logger.info("Vidage de opening_book (--fresh)…")
        conn.execute("DELETE FROM opening_book")
        conn.commit()
    positions_tb = conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0]
    conn.close()
    logger.info(
        "Tablebase endgame : %s positions — le livre pourra promouvoir des exacts.",
        f"{positions_tb:,}".replace(",", " "),
    )

    progress = OpeningBookProgress(db_path, target_bytes, progress_interval)
    progress.start()
    stop_flag = {"stop": False}

    def _stop_check() -> bool:
        conn = init_db(db_path)
        table_bytes = _opening_book_table_bytes(conn)
        count = _opening_book_count(conn)
        conn.close()
        bpe = progress._bytes_per_entry
        fill = max(table_bytes, int(count * bpe))
        if fill >= target_bytes:
            stop_flag["stop"] = True
            return True
        return stop_flag["stop"]

    wave_list = waves or WAVES
    total_exact = 0
    total_est = 0

    try:
        for wave_idx, (max_ply, max_pos, refresh) in enumerate(wave_list):
            if _stop_check():
                break
            logger.info(
                "Vague %d/%d — ply≤%d, max=%s positions, refresh=%s",
                wave_idx + 1,
                len(wave_list),
                max_ply,
                f"{max_pos:,}".replace(",", " "),
                refresh,
            )
            n_exact, n_est = build_opening_book(
                db_path,
                max_ply=max_ply,
                max_positions=max_pos,
                refresh_estimates=refresh,
                verbose=True,
                quality="full",
                store_board=True,
                progress_hook=progress.on_wave_progress,
                stop_check=_stop_check,
                commit_every=10,
            )
            total_exact += n_exact
            total_est += n_est
            if _stop_check():
                logger.info("Cible de %.1f Go atteinte.", target_bytes / 1e9)
                break
    except KeyboardInterrupt:
        logger.info("Interruption utilisateur — sauvegarde en cours…")
    finally:
        progress.stop(running=False)

    conn = init_db(db_path)
    count = _opening_book_count(conn)
    exact = _opening_exact_count(conn)
    table_bytes = _opening_book_table_bytes(conn)
    conn.close()

    logger.info(
        "Terminé : %s entrées (exact=%s, estimé session=%s) — table opening_book ≈ %.2f Mo",
        f"{count:,}".replace(",", " "),
        f"{exact:,}".replace(",", " "),
        f"{total_est:,}".replace(",", " "),
        table_bytes / 1e6,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Construction longue durée du livre d'ouverture (~2 Go, dashboard live)"
    )
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument(
        "--target-gb",
        type=float,
        default=2.0,
        help="Cible de taille du livre d'ouverture en Go (défaut: 2)",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Vider opening_book avant de reconstruire",
    )
    parser.add_argument(
        "--max-ply",
        type=int,
        default=None,
        help="Limite une seule vague au ply indiqué (debug)",
    )
    parser.add_argument(
        "--max-positions",
        type=int,
        default=None,
        help="Avec --max-ply : nombre max de positions (défaut 100000)",
    )
    parser.add_argument(
        "--progress-interval",
        type=float,
        default=15.0,
        help="Heartbeat JSON / dashboard (secondes)",
    )
    args = parser.parse_args()

    target_bytes = int(args.target_gb * 1024 * 1024 * 1024)
    waves = None
    if args.max_ply is not None:
        waves = [(args.max_ply, args.max_positions or 100_000, False)]

    print(
        f"Construction livre d'ouverture FULL — cible {args.target_gb} Go, "
        f"dashboard solver_progress phase=opening_book"
    )
    run_opening_book_full(
        Path(args.db),
        target_bytes=target_bytes,
        fresh=args.fresh,
        waves=waves,
        progress_interval=args.progress_interval,
    )


if __name__ == "__main__":
    main()
