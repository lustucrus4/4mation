//! Lecture des statistiques solveur depuis SQLite (équivalent SolverProgressService + WorkQueueService).

use anyhow::{Context, Result};
use super::engine::EngineControl;
use super::process;
use rusqlite::{Connection, OptionalExtension};
use serde::Serialize;
use serde_json::Value;
use std::path::{Path, PathBuf};

const RATE_WINDOWS_SEC: [i64; 3] = [60, 120, 300];
const CLAIM_TIMEOUT_SEC: i64 = 300;
const LOCAL_API_VERSION: i32 = 1;
pub const MAX_EMPTY_LEVELS: [i64; 5] = [12, 20, 30, 40, 49];
/// Plafond de stockage visé (miroir de `local_engine::MAX_DB_BYTES`).
pub const MAX_DB_BYTES: i64 = 5 * 1024 * 1024 * 1024;

/// Taille totale de la base sur disque (fichier principal + WAL + SHM), en octets.
fn db_size_bytes(db_path: &Path) -> i64 {
    let mut total = 0i64;
    let base = db_path.display().to_string();
    for suffix in ["", "-wal", "-shm"] {
        if let Ok(meta) = std::fs::metadata(format!("{base}{suffix}")) {
            total += meta.len() as i64;
        }
    }
    total
}

#[derive(Debug, Serialize)]
pub struct SolverStatusPayload {
    pub success: bool,
    pub total_positions_solved: i64,
    pub total_positions_target: Option<i64>,
    pub total_queued: i64,
    pub progress_percent: Option<f64>,
    pub progress_unknown: bool,
    pub max_empty: Option<i64>,
    pub max_empty_level_idx: Option<i64>,
    pub max_empty_levels: Vec<i64>,
    pub phase_label: String,
    pub positions_per_second: f64,
    pub eta_seconds: Option<i64>,
    pub solver_running: bool,
    pub status: String,
    pub started_at: Option<String>,
    pub last_update: Option<String>,
    pub current_phase: String,
    pub recent_positions: Vec<RecentPosition>,
    pub db_path: String,
    pub db_available: bool,
    // Suivi du poids de la base et de la cible 5 Go.
    pub db_size_bytes: i64,
    pub db_size_limit_bytes: i64,
    pub db_fill_percent: f64,
    pub db_eta_seconds: Option<i64>,
    pub est_total_positions: Option<i64>,
    // Cases vides des grilles en cours de calcul.
    pub current_empty_min: Option<i64>,
    pub current_empty_max: Option<i64>,
    pub in_progress: i64,
}

#[derive(Debug, Serialize)]
pub struct RecentPosition {
    pub hash: String,
    pub board: Value,
    pub current_player: Option<i32>,
    pub last_move: Option<MoveCoord>,
    pub best_move: Option<MoveCoord>,
    pub result: String,
    pub win_rate: f64,
    pub solved_at: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct MoveCoord {
    pub row: i32,
    pub col: i32,
}

#[derive(Debug, Serialize)]
pub struct WorkStatsPayload {
    pub success: bool,
    pub pending: i64,
    pub in_progress: i64,
    pub done_in_queue: i64,
    pub solved: i64,
    pub active_workers: Vec<ActiveWorker>,
    pub active_worker_count: usize,
    pub claim_timeout_sec: i64,
}

#[derive(Debug, Serialize)]
pub struct ActiveWorker {
    pub worker_id: String,
    pub positions_in_progress: i64,
    pub last_claim: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct HealthPayload {
    pub ok: bool,
    pub db_path: String,
    pub db_exists: bool,
    pub local_controls: bool,
    pub local_api_version: i32,
}

#[derive(Debug, Serialize)]
pub struct ProcessStatusPayload {
    pub success: bool,
    pub running: bool,
    pub process_name: &'static str,
    pub status_label: String,
}

fn open_conn(db_path: &Path) -> Result<Connection> {
    let conn = Connection::open(db_path).with_context(|| format!("ouverture {db_path:?}"))?;
    conn.execute_batch(
        "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA busy_timeout=10000;",
    )?;
    Ok(conn)
}

fn phase_label(phase: &str) -> String {
    match phase {
        "endgame" => "Fin de partie".into(),
        "midgame" => "Milieu de partie".into(),
        "opening" => "Ouverture".into(),
        "complet" => "Complet".into(),
        "full" => "Exploration".into(),
        other => other.to_string(),
    }
}

fn rate_from_db(conn: &Connection) -> f64 {
    for window in RATE_WINDOWS_SEC {
        let cnt: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM positions WHERE solved_at >= datetime('now', ?)",
                [format!("-{window} seconds")],
                |r| r.get(0),
            )
            .unwrap_or(0);
        if cnt > 0 {
            return cnt as f64 / window as f64;
        }
    }
    0.0
}

fn workers_active(conn: &Connection) -> bool {
    conn.query_row(
        "SELECT COUNT(*) FROM work_queue
         WHERE status = 'in_progress'
           AND claimed_at >= datetime('now', '-300 seconds')",
        [],
        |r| r.get::<_, i64>(0),
    )
    .map(|n| n > 0)
    .unwrap_or(false)
}

fn db_recently_updated(conn: &Connection, max_age_sec: i64) -> bool {
    let updated: Option<String> = conn
        .query_row(
            "SELECT updated_at FROM solver_progress WHERE id = 1",
            [],
            |r| r.get(0),
        )
        .optional()
        .ok()
        .flatten();
    let Some(updated) = updated else {
        return false;
    };
    let age: f64 = conn
        .query_row(
            "SELECT (julianday('now') - julianday(?)) * 86400",
            [&updated],
            |r| r.get(0),
        )
        .unwrap_or(f64::MAX);
    age <= max_age_sec as f64
}

fn stale_age_seconds(conn: &Connection, last_update: &Option<String>) -> Option<f64> {
    let ts = last_update.as_ref()?;
    conn.query_row(
        "SELECT (julianday('now') - julianday(?)) * 86400",
        [ts],
        |r| r.get(0),
    )
    .ok()
}

fn recent_from_db(conn: &Connection) -> Vec<RecentPosition> {
    let mut stmt = match conn.prepare(
        "SELECT hash, result, win_rate, best_move_row, best_move_col,
                board_blob, board_json, current_player, pos_last_move_row, pos_last_move_col, solved_at
         FROM positions
         WHERE (board_blob IS NOT NULL OR board_json IS NOT NULL)
         ORDER BY solved_at DESC
         LIMIT 20",
    ) {
        Ok(s) => s,
        Err(_) => return Vec::new(),
    };

    let rows = stmt.query_map([], |row| {
        Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, f64>(2)?,
            row.get::<_, Option<i32>>(3)?,
            row.get::<_, Option<i32>>(4)?,
            row.get::<_, Option<Vec<u8>>>(5)?,
            row.get::<_, Option<String>>(6)?,
            row.get::<_, Option<i32>>(7)?,
            row.get::<_, Option<i32>>(8)?,
            row.get::<_, Option<i32>>(9)?,
            row.get::<_, Option<String>>(10)?,
        ))
    });

    let Ok(rows) = rows else {
        return Vec::new();
    };

    let mut out = Vec::new();
    for row in rows.flatten() {
        let (
            hash,
            result,
            win_rate,
            bmr,
            bmc,
            board_blob,
            board_json,
            current_player,
            lmr,
            lmc,
            solved_at,
        ) = row;
        let board: Value = if let Some(b) = board_blob.as_deref().filter(|b| !b.is_empty()) {
            crate::game::board_to_value(&crate::game::board_from_blob(b))
        } else if let Some(s) = board_json.as_deref().filter(|s| !s.is_empty()) {
            serde_json::from_str(s).unwrap_or(Value::Null)
        } else {
            Value::Null
        };
        let best_move = bmr
            .filter(|&r| r >= 0)
            .map(|row| MoveCoord {
                row,
                col: bmc.unwrap_or(-1),
            });
        let last_move = lmr
            .filter(|&r| r >= 0)
            .map(|row| MoveCoord {
                row,
                col: lmc.unwrap_or(-1),
            });
        out.push(RecentPosition {
            hash,
            board,
            current_player,
            last_move,
            best_move,
            result,
            win_rate,
            solved_at,
        });
    }
    out
}

pub fn get_solver_status(
    db_path: &Path,
    solver_in_process: bool,
    engine_control: Option<&EngineControl>,
) -> SolverStatusPayload {
    let db_available = db_path.exists();
    let db_path_str = db_path.display().to_string();

    if !db_available {
        return SolverStatusPayload {
            success: true,
            total_positions_solved: 0,
            total_positions_target: None,
            total_queued: 0,
            progress_percent: None,
            progress_unknown: true,
            max_empty: None,
            max_empty_level_idx: None,
            max_empty_levels: MAX_EMPTY_LEVELS.to_vec(),
            phase_label: phase_label("full"),
            positions_per_second: 0.0,
            eta_seconds: None,
            solver_running: engine_control.map(|c| c.is_running()).unwrap_or(solver_in_process),
            status: if engine_control.map(|c| c.is_running()).unwrap_or(solver_in_process) {
                "en_cours".into()
            } else {
                "pause".into()
            },
            started_at: None,
            last_update: None,
            current_phase: "full".into(),
            recent_positions: Vec::new(),
            db_path: db_path_str,
            db_available: false,
            db_size_bytes: 0,
            db_size_limit_bytes: MAX_DB_BYTES,
            db_fill_percent: 0.0,
            db_eta_seconds: None,
            est_total_positions: None,
            current_empty_min: None,
            current_empty_max: None,
            in_progress: 0,
        };
    }

    let conn = match open_conn(db_path) {
        Ok(c) => c,
        Err(_) => {
            return SolverStatusPayload {
                success: true,
                total_positions_solved: 0,
                total_positions_target: None,
                total_queued: 0,
                progress_percent: None,
                progress_unknown: true,
                max_empty: None,
                max_empty_level_idx: None,
                max_empty_levels: MAX_EMPTY_LEVELS.to_vec(),
                phase_label: phase_label("full"),
                positions_per_second: 0.0,
                eta_seconds: None,
                solver_running: engine_control.map(|c| c.is_running()).unwrap_or(false),
                status: "pause".into(),
                started_at: None,
                last_update: None,
                current_phase: "full".into(),
                recent_positions: Vec::new(),
                db_path: db_path_str,
                db_available: true,
                db_size_bytes: db_size_bytes(db_path),
                db_size_limit_bytes: MAX_DB_BYTES,
                db_fill_percent: (100.0 * db_size_bytes(db_path) as f64 / MAX_DB_BYTES as f64)
                    .min(100.0),
                db_eta_seconds: None,
                est_total_positions: None,
                current_empty_min: None,
                current_empty_max: None,
                in_progress: 0,
            };
        }
    };

    let positions_count: i64 = conn
        .query_row("SELECT COUNT(*) FROM positions", [], |r| r.get(0))
        .unwrap_or(0);
    let pending_count: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM work_queue WHERE status = 'pending'",
            [],
            |r| r.get(0),
        )
        .unwrap_or(0);

    let row = conn
        .query_row(
            "SELECT total_solved, total_queued, current_phase, started_at,
                    solver_running, updated_at, total_target, progress_percent,
                    current_max_empty, max_empty_level_idx
             FROM solver_progress WHERE id = 1",
            [],
            |r| {
                Ok((
                    r.get::<_, Option<i64>>(0)?,
                    r.get::<_, Option<i64>>(1)?,
                    r.get::<_, Option<String>>(2)?,
                    r.get::<_, Option<String>>(3)?,
                    r.get::<_, Option<i64>>(4)?,
                    r.get::<_, Option<String>>(5)?,
                    r.get::<_, Option<i64>>(6)?,
                    r.get::<_, Option<f64>>(7)?,
                    r.get::<_, Option<i64>>(8)?,
                    r.get::<_, Option<i64>>(9)?,
                ))
            },
        )
        .optional()
        .ok()
        .flatten();

    let (db_solved, db_queued, db_phase, db_started, db_running_flag, db_updated, db_target, _db_progress, db_max_empty, db_level_idx) =
        if let Some(r) = row {
            let cached_solved = r.0.unwrap_or(0);
            (
                positions_count.max(cached_solved),
                pending_count,
                r.2.unwrap_or_else(|| "full".into()),
                r.3,
                r.4.unwrap_or(0) != 0,
                r.5,
                r.6,
                r.7,
                r.8,
                r.9,
            )
        } else {
            (
                positions_count,
                pending_count,
                "full".into(),
                None,
                false,
                None,
                None,
                None,
                None,
                None,
            )
        };

    let workers = workers_active(&conn);
    let db_rate = rate_from_db(&conn);
    let db_recent = db_recently_updated(&conn, 300);

    let engine_active = engine_control.map(|c| c.is_running()).unwrap_or(false);
    let running = engine_active || (!solver_in_process && (db_running_flag || workers));
    let started_at = db_started.clone();
    let mut last_update = db_updated.clone();
    if (workers || db_recent) && db_updated.is_some() {
        last_update = db_updated;
    }

    let stale_age = stale_age_seconds(&conn, &last_update);

    let total_target = db_target;
    let progress_unknown = total_target.is_none();
    let progress = if progress_unknown {
        None
    } else if let Some(target) = total_target {
        if target > 0 {
            Some((100.0 * db_solved as f64 / target as f64).min(100.0))
        } else {
            None
        }
    } else {
        None
    };

    let rate = (db_rate * 100.0).round() / 100.0;

    let eta = if !progress_unknown && rate > 0.0 {
        total_target.and_then(|target| {
            if db_solved < target {
                Some(((target - db_solved) as f64 / rate) as i64)
            } else {
                None
            }
        })
    } else {
        None
    };

    let status = if running {
        if db_queued == 0 && rate == 0.0 {
            "en_veille"
        } else if stale_age.is_some_and(|a| a > 60.0) {
            "calcul_long"
        } else {
            "en_cours"
        }
    } else if !progress_unknown && total_target.is_some_and(|t| db_solved >= t) {
        "termine"
    } else if db_solved > 0 {
        if stale_age.is_some_and(|a| a <= 90.0) {
            "rechargement"
        } else {
            "pause"
        }
    } else {
        "pause"
    };

    let recent_positions = recent_from_db(&conn);
    let phase_display = phase_label(&db_phase);

    // Poids de la base et projection vers le plafond 5 Go.
    let db_size = db_size_bytes(db_path);
    let db_fill = (100.0 * db_size as f64 / MAX_DB_BYTES as f64).min(100.0);
    let bytes_per_pos = if positions_count > 0 {
        db_size as f64 / positions_count as f64
    } else {
        0.0
    };
    let est_total_positions = if bytes_per_pos > 0.0 {
        Some((MAX_DB_BYTES as f64 / bytes_per_pos) as i64)
    } else {
        None
    };
    let db_eta_seconds = if rate > 0.0 && bytes_per_pos > 0.0 && db_size < MAX_DB_BYTES {
        let remaining_pos = (MAX_DB_BYTES as f64 - db_size as f64) / bytes_per_pos;
        Some((remaining_pos / rate) as i64)
    } else {
        None
    };

    // Cases vides des grilles en cours de calcul (repli sur le prochain pending).
    let (mut ce_min, mut ce_max): (Option<i64>, Option<i64>) = conn
        .query_row(
            "SELECT MIN(empty_cells), MAX(empty_cells) FROM work_queue WHERE status='in_progress'",
            [],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )
        .unwrap_or((None, None));
    if ce_min.is_none() {
        ce_min = conn
            .query_row(
                "SELECT MIN(empty_cells) FROM work_queue WHERE status='pending'",
                [],
                |r| r.get(0),
            )
            .ok()
            .flatten();
        ce_max = ce_max.or(ce_min);
    }
    let in_progress: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM work_queue WHERE status='in_progress'",
            [],
            |r| r.get(0),
        )
        .unwrap_or(0);

    SolverStatusPayload {
        success: true,
        total_positions_solved: db_solved,
        total_positions_target: total_target,
        total_queued: db_queued,
        progress_percent: progress.map(|p| (p * 10000.0).round() / 10000.0),
        progress_unknown: progress.is_none(),
        max_empty: db_max_empty.or(Some(MAX_EMPTY_LEVELS[0])),
        max_empty_level_idx: db_level_idx.or(Some(0)),
        max_empty_levels: MAX_EMPTY_LEVELS.to_vec(),
        phase_label: phase_display,
        positions_per_second: rate,
        eta_seconds: eta,
        solver_running: running,
        status: status.into(),
        started_at,
        last_update,
        current_phase: db_phase,
        recent_positions,
        db_path: db_path_str,
        db_available: true,
        db_size_bytes: db_size,
        db_size_limit_bytes: MAX_DB_BYTES,
        db_fill_percent: (db_fill * 100.0).round() / 100.0,
        db_eta_seconds,
        est_total_positions,
        current_empty_min: ce_min,
        current_empty_max: ce_max,
        in_progress,
    }
}

fn reclaim_stale(conn: &Connection) {
    let _ = conn.execute(
        "UPDATE work_queue
         SET status = 'pending', worker_id = NULL, claimed_at = NULL
         WHERE status = 'in_progress'
           AND claimed_at IS NOT NULL
           AND claimed_at < datetime('now', ?)",
        [format!("-{CLAIM_TIMEOUT_SEC} seconds")],
    );
}

pub fn get_work_stats(db_path: &Path) -> WorkStatsPayload {
    let empty = WorkStatsPayload {
        success: true,
        pending: 0,
        in_progress: 0,
        done_in_queue: 0,
        solved: 0,
        active_workers: Vec::new(),
        active_worker_count: 0,
        claim_timeout_sec: CLAIM_TIMEOUT_SEC,
    };

    if !db_path.exists() {
        return empty;
    }

    let conn = match open_conn(db_path) {
        Ok(c) => c,
        Err(_) => return empty,
    };

    reclaim_stale(&conn);
    let _ = conn.execute("COMMIT", []).ok();

    let pending = conn
        .query_row(
            "SELECT COUNT(*) FROM work_queue WHERE status = 'pending'",
            [],
            |r| r.get(0),
        )
        .unwrap_or(0);
    let in_progress = conn
        .query_row(
            "SELECT COUNT(*) FROM work_queue WHERE status = 'in_progress'",
            [],
            |r| r.get(0),
        )
        .unwrap_or(0);
    let done_queue = conn
        .query_row(
            "SELECT COUNT(*) FROM work_queue WHERE status = 'done'",
            [],
            |r| r.get(0),
        )
        .unwrap_or(0);
    let solved = conn
        .query_row("SELECT COUNT(*) FROM positions", [], |r| r.get(0))
        .unwrap_or(0);

    let cutoff = format!("-{CLAIM_TIMEOUT_SEC} seconds");
    let mut stmt = match conn.prepare(
        "SELECT worker_id, COUNT(*) AS cnt, MAX(claimed_at) AS last_claim
         FROM work_queue
         WHERE status = 'in_progress'
           AND worker_id IS NOT NULL
           AND claimed_at >= datetime('now', ?)
         GROUP BY worker_id
         ORDER BY last_claim DESC",
    ) {
        Ok(s) => s,
        Err(_) => {
            return WorkStatsPayload {
                solved,
                pending,
                in_progress,
                done_in_queue: done_queue,
                ..empty
            };
        }
    };

    let rows = stmt.query_map([&cutoff], |row| {
        Ok(ActiveWorker {
            worker_id: row.get(0)?,
            positions_in_progress: row.get(1)?,
            last_claim: row.get(2)?,
        })
    });

    let active_workers: Vec<ActiveWorker> = match rows {
        Ok(iter) => iter.filter_map(Result::ok).collect(),
        Err(_) => Vec::new(),
    };

    WorkStatsPayload {
        success: true,
        pending,
        in_progress,
        done_in_queue: done_queue,
        solved,
        active_worker_count: active_workers.len(),
        active_workers,
        claim_timeout_sec: CLAIM_TIMEOUT_SEC,
    }
}

pub fn get_health(db_path: &Path) -> HealthPayload {
    HealthPayload {
        ok: true,
        db_path: db_path.display().to_string(),
        db_exists: db_path.exists(),
        local_controls: true,
        local_api_version: LOCAL_API_VERSION,
    }
}

pub fn get_process_status(
    solver_in_process: bool,
    engine_control: Option<&EngineControl>,
) -> ProcessStatusPayload {
    let running = if let Some(ctrl) = engine_control {
        ctrl.is_running()
    } else if solver_in_process {
        false
    } else {
        process::is_solver_running()
    };
    ProcessStatusPayload {
        success: true,
        running,
        process_name: process::SOLVER_PROCESS_NAME,
        status_label: if running {
            "actif".into()
        } else {
            "arrêté".into()
        },
    }
}

pub fn resolve_web_dir() -> PathBuf {
    let candidates = [
        PathBuf::from("script/solver_rust/web"),
        PathBuf::from("web"),
    ];
    for c in &candidates {
        if c.is_dir() {
            return c.clone();
        }
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(parent) = exe.parent() {
            if let Ok(p) = parent.join("../../web").canonicalize() {
                if p.is_dir() {
                    return p;
                }
            }
        }
    }
    PathBuf::from("script/solver_rust/web")
}
