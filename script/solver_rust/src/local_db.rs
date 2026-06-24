//! Persistance SQLite locale — schéma partagé, exploration et résolution sans réseau.

use anyhow::{Context, Result};
use rusqlite::{params, Connection};
use serde_json::Value;
use std::collections::HashSet;
use std::path::Path;
use tracing::info;

use crate::game::Position;
use crate::game::Board;
use crate::work::{ClaimedPosition, LastMove, SubmitPayload};

const SCHEMA_SQL: &str = r#"
CREATE TABLE IF NOT EXISTS positions (
    hash TEXT PRIMARY KEY,
    result TEXT NOT NULL,
    win_rate REAL NOT NULL,
    best_move_row INTEGER,
    best_move_col INTEGER,
    depth_remaining INTEGER,
    solved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS opening_book (
    hash TEXT PRIMARY KEY,
    result TEXT NOT NULL,
    win_rate REAL NOT NULL,
    best_move_row INTEGER,
    best_move_col INTEGER,
    ply INTEGER NOT NULL,
    solved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS solver_progress (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    total_queued INTEGER DEFAULT 0,
    total_solved INTEGER DEFAULT 0,
    last_hash TEXT,
    started_at TIMESTAMP,
    current_phase TEXT DEFAULT 'full',
    solver_running INTEGER DEFAULT 0,
    total_target INTEGER,
    progress_percent REAL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS work_queue (
    hash TEXT PRIMARY KEY,
    board_json TEXT NOT NULL,
    player INTEGER NOT NULL,
    last_move_row INTEGER,
    last_move_col INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    worker_id TEXT,
    claimed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_positions_depth ON positions(depth_remaining);
CREATE INDEX IF NOT EXISTS idx_positions_solved_at ON positions(solved_at);
CREATE INDEX IF NOT EXISTS idx_opening_ply ON opening_book(ply);
CREATE INDEX IF NOT EXISTS idx_work_queue_status ON work_queue(status);
CREATE INDEX IF NOT EXISTS idx_work_queue_claimed ON work_queue(claimed_at);
"#;

const MIGRATIONS: &[&str] = &[
    "ALTER TABLE positions ADD COLUMN board_json TEXT",
    "ALTER TABLE positions ADD COLUMN current_player INTEGER",
    "ALTER TABLE positions ADD COLUMN pos_last_move_row INTEGER",
    "ALTER TABLE positions ADD COLUMN pos_last_move_col INTEGER",
    "ALTER TABLE solver_progress ADD COLUMN started_at TIMESTAMP",
    "ALTER TABLE solver_progress ADD COLUMN current_phase TEXT DEFAULT 'full'",
    "ALTER TABLE solver_progress ADD COLUMN solver_running INTEGER DEFAULT 0",
    "ALTER TABLE solver_progress ADD COLUMN total_target INTEGER",
    "ALTER TABLE solver_progress ADD COLUMN progress_percent REAL DEFAULT 0",
    "CREATE INDEX IF NOT EXISTS idx_positions_solved_at ON positions(solved_at)",
];

/// Aligné sur SOLVER_MAX_CLAIM_BATCH côté API (défaut 500).
pub const MAX_CLAIM_BATCH: usize = 500;

pub struct LocalDb {
    path: String,
}

impl LocalDb {
    pub fn open(path: &Path) -> Result<Self> {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).ok();
        }
        let path_str = path
            .to_str()
            .context("chemin DB invalide")?
            .to_string();
        let db = Self { path: path_str };
        db.init_schema()?;
        info!("Base locale ouverte : {}", db.path);
        Ok(db)
    }

    fn conn(&self) -> Result<Connection> {
        let conn = Connection::open(&self.path)?;
        conn.execute_batch(
            "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA busy_timeout=10000;
             PRAGMA cache_size=-128000; PRAGMA temp_store=MEMORY;",
        )?;
        Ok(conn)
    }

    pub fn init_schema(&self) -> Result<()> {
        let conn = self.conn()?;
        conn.execute_batch(SCHEMA_SQL)?;
        for sql in MIGRATIONS {
            let _ = conn.execute_batch(sql);
        }
        conn.execute(
            "INSERT OR IGNORE INTO solver_progress (id, solver_running) VALUES (1, 0)",
            [],
        )?;
        conn.execute(
            "UPDATE solver_progress SET solver_running=1, started_at=COALESCE(started_at,CURRENT_TIMESTAMP), updated_at=CURRENT_TIMESTAMP WHERE id=1",
            [],
        )?;
        Ok(())
    }

    pub fn known_hashes_full(&self) -> Result<HashSet<String>> {
        let conn = self.conn()?;
        let mut known = HashSet::new();
        let mut stmt = conn.prepare("SELECT hash FROM positions")?;
        let rows = stmt.query_map([], |row| row.get::<_, String>(0))?;
        for h in rows {
            known.insert(h?.to_lowercase());
        }
        let mut stmt = conn.prepare(
            "SELECT hash FROM work_queue WHERE status IN ('pending', 'in_progress', 'done')",
        )?;
        let rows = stmt.query_map([], |row| row.get::<_, String>(0))?;
        for h in rows {
            known.insert(h?.to_lowercase());
        }
        Ok(known)
    }

    pub fn count_pending(&self) -> Result<i64> {
        let conn = self.conn()?;
        let n: i64 = conn.query_row(
            "SELECT COUNT(*) FROM work_queue WHERE status='pending'",
            [],
            |r| r.get(0),
        )?;
        Ok(n)
    }

    pub fn count_solved(&self) -> Result<i64> {
        let conn = self.conn()?;
        let n: i64 = conn.query_row("SELECT COUNT(*) FROM positions", [], |r| r.get(0))?;
        Ok(n)
    }

    pub fn load_seed_positions(&self, limit: usize) -> Result<Vec<Position>> {
        let conn = self.conn()?;
        let mut stmt = conn.prepare(
            "SELECT board_json, current_player, pos_last_move_row, pos_last_move_col
             FROM positions WHERE board_json IS NOT NULL
             ORDER BY depth_remaining ASC LIMIT ?",
        )?;
        let rows = stmt.query_map([limit as i64], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, i32>(1)?,
                row.get::<_, Option<i32>>(2)?,
                row.get::<_, Option<i32>>(3)?,
            ))
        })?;

        let mut out = Vec::new();
        for row in rows {
            let (board_json, player, lmr, lmc) = row?;
            let board: Board = crate::game::parse_board(
                &serde_json::from_str(&board_json).unwrap_or(Value::Null),
            );
            let lm = lmr
                .filter(|&r| r >= 0)
                .map(|r| (r as usize, lmc.unwrap_or(-1).max(0) as usize));
            out.push((board, player as i8, lm));
        }
        Ok(out)
    }

    pub fn bulk_insert_queue(&self, positions: &[(String, String, i8, i32, i32)]) -> Result<usize> {
        if positions.is_empty() {
            return Ok(0);
        }
        let conn = self.conn()?;
        conn.execute("BEGIN IMMEDIATE", [])?;
        let mut inserted = 0usize;
        {
            let mut stmt = conn.prepare(
                "INSERT OR IGNORE INTO work_queue
                 (hash, board_json, player, last_move_row, last_move_col, status)
                 VALUES (?1, ?2, ?3, ?4, ?5, 'pending')",
            )?;
            for (hash, board_json, player, lmr, lmc) in positions {
                let changes = stmt.execute(params![
                    hash,
                    board_json,
                    *player as i32,
                    lmr,
                    lmc
                ])?;
                inserted += changes;
            }
        }
        let pending: i64 = conn.query_row(
            "SELECT COUNT(*) FROM work_queue WHERE status='pending'",
            [],
            |r| r.get(0),
        )?;
        conn.execute(
            "INSERT INTO solver_progress (id, total_queued, updated_at)
             VALUES (1, ?1, CURRENT_TIMESTAMP)
             ON CONFLICT(id) DO UPDATE SET total_queued=excluded.total_queued, updated_at=CURRENT_TIMESTAMP",
            [pending],
        )?;
        conn.execute("COMMIT", [])?;
        Ok(inserted)
    }

    pub fn claim(&self, worker_id: &str, count: usize) -> Result<Vec<ClaimedPosition>> {
        let count = count.clamp(1, MAX_CLAIM_BATCH);
        let conn = self.conn()?;
        conn.execute("BEGIN IMMEDIATE", [])?;

        let mut stmt = conn.prepare(
            "SELECT hash, board_json, player, last_move_row, last_move_col
             FROM work_queue WHERE status = 'pending'
             ORDER BY created_at ASC LIMIT ?",
        )?;
        let rows: Vec<(String, String, i32, Option<i32>, Option<i32>)> = stmt
            .query_map([count as i64], |row| {
                Ok((
                    row.get(0)?,
                    row.get(1)?,
                    row.get(2)?,
                    row.get(3)?,
                    row.get(4)?,
                ))
            })?
            .collect::<Result<Vec<_>, _>>()?;

        let mut claimed = Vec::with_capacity(rows.len());
        for (hash, board_json, player, lmr, lmc) in rows {
            conn.execute(
                "UPDATE work_queue SET status='in_progress', worker_id=?1, claimed_at=CURRENT_TIMESTAMP
                 WHERE hash=?2 AND status='pending'",
                params![worker_id, hash],
            )?;
            let board: Value = serde_json::from_str(&board_json).unwrap_or(Value::Null);
            let last_move = lmr
                .filter(|&r| r >= 0)
                .map(|r| LastMove {
                    row: r,
                    col: lmc.unwrap_or(-1),
                });
            claimed.push(ClaimedPosition {
                hash,
                board_json: board,
                player,
                last_move,
            });
        }
        conn.execute("COMMIT", [])?;
        Ok(claimed)
    }

    pub fn submit_bulk(&self, payloads: &[SubmitPayload]) -> Result<(usize, usize)> {
        if payloads.is_empty() {
            return Ok((0, 0));
        }
        let conn = self.conn()?;
        conn.execute("BEGIN IMMEDIATE", [])?;

        let mut ok = 0usize;
        let mut fail = 0usize;

        {
            let mut pos_stmt = conn.prepare(
                "INSERT OR REPLACE INTO positions
                 (hash, result, win_rate, best_move_row, best_move_col, depth_remaining,
                  board_json, current_player, pos_last_move_row, pos_last_move_col, solved_at)
                 VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,CURRENT_TIMESTAMP)",
            )?;
            let mut wq_stmt = conn.prepare(
                "UPDATE work_queue SET status='done', worker_id=COALESCE(worker_id,?1),
                 claimed_at=COALESCE(claimed_at,CURRENT_TIMESTAMP) WHERE hash=?2",
            )?;

            for payload in payloads {
                let board_str = match serde_json::to_string(&payload.board_json) {
                    Ok(s) => s,
                    Err(e) => {
                        tracing::warn!("sérialisation board {} : {}", payload.hash, e);
                        fail += 1;
                        continue;
                    }
                };
                let (br, bc) = payload
                    .best_move
                    .as_ref()
                    .map(|m| (m.row, m.col))
                    .unwrap_or((-1, -1));
                let (lmr, lmc) = payload
                    .last_move
                    .as_ref()
                    .map(|m| (m.row, m.col))
                    .unwrap_or((-1, -1));

                if pos_stmt
                    .execute(params![
                        payload.hash,
                        payload.result.to_string(),
                        payload.win_rate,
                        br,
                        bc,
                        payload.depth_remaining as i64,
                        board_str,
                        payload.player,
                        lmr,
                        lmc,
                    ])
                    .is_err()
                {
                    fail += 1;
                    continue;
                }
                let _ = wq_stmt.execute(params![payload.worker_id, payload.hash]);
                ok += 1;
            }
        }

        let total: i64 = conn.query_row("SELECT COUNT(*) FROM positions", [], |r| r.get(0))?;
        conn.execute(
            "INSERT INTO solver_progress (id, total_solved, updated_at)
             VALUES (1, ?1, CURRENT_TIMESTAMP)
             ON CONFLICT(id) DO UPDATE SET total_solved=excluded.total_solved, updated_at=CURRENT_TIMESTAMP",
            [total],
        )?;
        conn.execute("COMMIT", [])?;
        Ok((ok, fail))
    }

    pub fn submit_batch(&self, payloads: &[SubmitPayload]) -> Result<(usize, usize)> {
        self.submit_bulk(payloads)
    }

    pub fn release(&self, worker_id: &str, hash: &str) -> Result<()> {
        let conn = self.conn()?;
        conn.execute(
            "UPDATE work_queue SET status='pending', worker_id=NULL, claimed_at=NULL
             WHERE hash=?1 AND status='in_progress' AND worker_id=?2",
            params![hash, worker_id],
        )?;
        Ok(())
    }
}
