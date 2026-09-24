"""Client persistant du moteur Rust `4mation-engine`.

Le moteur parle un protocole « une requête JSON par ligne sur stdin, une réponse
JSON par ligne sur stdout ». Il garde sa table de transposition entre les requêtes :
il doit donc tourner dans un processus **persistant**, et surtout pas être relancé
à chaque coup.

Le service est volontairement tolérant : si le binaire n'est pas présent (serveur
qui n'a pas compilé le crate) ou s'il tombe, `is_available()` renvoie False et les
appelants retombent sur le Minimax Python existant. Le moteur n'est jamais un point
de rupture du site.

Configuration par variables d'environnement :

| Variable | Défaut | Rôle |
|----------|--------|------|
| `ENGINE_BIN` | `script/solver_rust/target/release/4mation-engine[.exe]` | Binaire du moteur |
| `ENGINE_TABLEBASE` | `script/solver/data/tablebase.db` | Tablebase SQLite |
| `ENGINE_TT_MB` | `192` | Taille de la table de transposition (par worker) |
| `ENGINE_DEPTH` | `18` | Profondeur par défaut |
| `ENGINE_TIME_MS` | `1200` | Budget temps par défaut |
| `ENGINE_TIMEOUT_S` | `30` | Délai maximal d'attente d'une réponse |
| `ENGINE_DISABLED` | — | `1` pour ne jamais démarrer le moteur |
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import queue
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _default_binary() -> Path:
    override = os.environ.get("ENGINE_BIN")
    if override:
        return Path(override)
    name = "4mation-engine.exe" if os.name == "nt" else "4mation-engine"
    return REPO_ROOT / "script" / "solver_rust" / "target" / "release" / name


def _default_tablebase() -> Path:
    return Path(
        os.environ.get("ENGINE_TABLEBASE")
        or REPO_ROOT / "script" / "solver" / "data" / "tablebase.db"
    )


def board_to_lists(board: Any) -> List[List[int]]:
    """Convertit un plateau numpy en listes Python sérialisables en JSON."""
    return [[int(cell) for cell in row] for row in board]


def _move_to_list(move: Optional[Sequence[int]]) -> Optional[List[int]]:
    if move is None:
        return None
    row, col = move[0], move[1]
    return [int(row), int(col)]


class EngineClient:
    """Un processus moteur partagé, requêtes sérialisées par un verrou."""

    def __init__(
        self,
        binary: Optional[Path] = None,
        tablebase: Optional[Path] = None,
        tt_mb: Optional[int] = None,
        default_depth: Optional[int] = None,
        default_time_ms: Optional[int] = None,
        timeout_s: Optional[float] = None,
    ) -> None:
        self.binary = Path(binary) if binary else _default_binary()
        self.tablebase = Path(tablebase) if tablebase else _default_tablebase()
        self.tt_mb = int(tt_mb if tt_mb is not None else os.environ.get("ENGINE_TT_MB", 192))
        self.default_depth = int(
            default_depth if default_depth is not None else os.environ.get("ENGINE_DEPTH", 18)
        )
        self.default_time_ms = int(
            default_time_ms
            if default_time_ms is not None
            else os.environ.get("ENGINE_TIME_MS", 1200)
        )
        self.timeout_s = float(
            timeout_s if timeout_s is not None else os.environ.get("ENGINE_TIMEOUT_S", 30)
        )
        self.disabled = _env_flag("ENGINE_DISABLED")

        self._lock = threading.Lock()
        self._proc: Optional[subprocess.Popen] = None
        self._reader: Optional[threading.Thread] = None
        self._pending: "queue.Queue[Optional[str]]" = queue.Queue()
        self._broken = False
        self._started_once = False

    # ------------------------------------------------------------------ état

    def is_available(self) -> bool:
        """Vrai si le moteur peut être utilisé dans ce processus."""
        if self.disabled or self._broken:
            return False
        return self.binary.exists()

    def _command(self) -> List[str]:
        cmd = [
            str(self.binary),
            "--tt-mb",
            str(max(16, self.tt_mb)),
            "--depth",
            str(self.default_depth),
            "--time-ms",
            str(self.default_time_ms),
        ]
        if self.tablebase.exists():
            cmd += ["--tb", str(self.tablebase)]
        return cmd

    # ------------------------------------------------------------- processus

    def _reader_loop(self, proc: subprocess.Popen, sink: "queue.Queue[Optional[str]]") -> None:
        """Vide stdout en continu : le moteur ne bloque jamais sur un tube plein."""
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                sink.put(line)
        except Exception:
            pass
        finally:
            sink.put(None)

    def _ensure_process(self) -> Optional[subprocess.Popen]:
        if self.disabled or self._broken:
            return None
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        if not self.binary.exists():
            if not self._started_once:
                logger.info(
                    "Moteur Rust absent (%s) : repli sur le Minimax Python", self.binary
                )
                self._started_once = True
            return None

        sink: "queue.Queue[Optional[str]]" = queue.Queue()
        try:
            proc = subprocess.Popen(
                self._command(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                bufsize=1,
                cwd=str(REPO_ROOT),
            )
        except Exception as exc:
            logger.warning("Démarrage du moteur Rust impossible : %s", exc)
            self._broken = True
            return None

        self._proc = proc
        self._pending = sink
        self._reader = threading.Thread(
            target=self._reader_loop, args=(proc, sink), name="4mation-engine-stdout", daemon=True
        )
        self._reader.start()
        self._started_once = True
        logger.info("Moteur Rust démarré : %s", " ".join(self._command()))
        return proc

    def _stop_locked(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            if proc.poll() is None:
                if proc.stdin is not None:
                    proc.stdin.write('{"type":"quit"}\n')
                    proc.stdin.flush()
                proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def close(self) -> None:
        with self._lock:
            self._stop_locked()

    # -------------------------------------------------------------- requêtes

    def request(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Envoie une requête et renvoie la réponse, ou None si le moteur est muet."""
        with self._lock:
            proc = self._ensure_process()
            if proc is None or proc.stdin is None:
                return None
            sink = self._pending
            try:
                proc.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
                proc.stdin.flush()
            except Exception as exc:
                logger.warning("Écriture vers le moteur échouée : %s", exc)
                self._stop_locked()
                return None

            try:
                line = sink.get(timeout=self.timeout_s)
            except queue.Empty:
                logger.warning(
                    "Moteur sans réponse après %.0f s : processus arrêté", self.timeout_s
                )
                self._stop_locked()
                return None

            if line is None:
                logger.warning("Moteur terminé sans réponse")
                self._stop_locked()
                return None
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Réponse moteur illisible : %s", line[:200])
                return None

    def _payload(
        self,
        board: Any,
        current_player: int,
        last_move: Optional[Sequence[int]],
        depth: Optional[int],
        time_ms: Optional[int],
        exact: bool,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "board": board_to_lists(board),
            "current_player": int(current_player),
            "last_move": _move_to_list(last_move),
            "depth": int(depth if depth is not None else self.default_depth),
            "time_ms": int(time_ms if time_ms is not None else self.default_time_ms),
        }
        if exact:
            payload["exact"] = True
        return payload

    def best_move(
        self,
        board: Any,
        current_player: int,
        last_move: Optional[Sequence[int]] = None,
        depth: Optional[int] = None,
        time_ms: Optional[int] = None,
    ) -> Optional[Tuple[int, int]]:
        """Meilleur coup pour le joueur au trait, ou None (moteur indisponible)."""
        if not self.is_available():
            return None
        response = self.request(
            self._payload(board, current_player, last_move, depth, time_ms, exact=False)
        )
        if not response:
            return None
        move = response.get("best_move")
        if isinstance(move, (list, tuple)) and len(move) >= 2:
            return (int(move[0]), int(move[1]))
        return None

    def analyze(
        self,
        board: Any,
        current_player: int,
        last_move: Optional[Sequence[int]] = None,
        depth: Optional[int] = None,
        time_ms: Optional[int] = None,
        exact: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Analyse complète (scores de tous les coups si `exact`), ou None."""
        if not self.is_available():
            return None
        return self.request(
            self._payload(board, current_player, last_move, depth, time_ms, exact=exact)
        )


_client: Optional[EngineClient] = None
_client_lock = threading.Lock()


def get_engine_client() -> EngineClient:
    """Singleton du client moteur (un processus par worker)."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = EngineClient()
                atexit.register(_client.close)
    return _client
