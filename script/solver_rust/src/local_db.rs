//! Mode local — claim/submit directement sur SQLite (sans réseau).

use anyhow::{Context, Result};
use rusqlite::{params, Connection};
use serde_json::Value;
use std::path::Path;
use tracing::info;

use crate::api_client::{ClaimedPosition, LastMove, SubmitPayload};

const MAX_CLAIM_BATCH: usize = 50;

pub struct LocalDb {
    path: String,
}

impl LocalDb {
    pub fn open(path: &Path) -> Result<Self> {
        let path_str = path
            .to_str()
            .context("chemin DB invalide")?
            .to_string();
        let conn = Connection::open(&path_str)?;
        conn.execute_batch(
            "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA busy_timeout=10000;",
        )?;
        info!("Base locale ouverte : {}", path_str);
        Ok(Self { path: path_str })
    }

    fn conn(&self) -> Result<Connection> {
        let conn = Connection::open(&self.path)?;
        conn.busy_timeout(std::time::Duration::from_secs(10))?;
        Ok(conn)
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

    pub fn submit(&self, payload: &SubmitPayload) -> Result<()> {
        let conn = self.conn()?;
        conn.execute("BEGIN IMMEDIATE", [])?;

        let board_str = serde_json::to_string(&payload.board_json)?;
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

        conn.execute(
            "INSERT OR REPLACE INTO positions
             (hash, result, win_rate, best_move_row, best_move_col, depth_remaining,
              board_json, current_player, pos_last_move_row, pos_last_move_col, solved_at)
             VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,CURRENT_TIMESTAMP)",
            params![
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
            ],
        )?;

        conn.execute(
            "UPDATE work_queue SET status='done', worker_id=COALESCE(worker_id,?1),
             claimed_at=COALESCE(claimed_at,CURRENT_TIMESTAMP) WHERE hash=?2",
            params![payload.worker_id, payload.hash],
        )?;

        let total: i64 = conn.query_row("SELECT COUNT(*) FROM positions", [], |r| r.get(0))?;
        conn.execute(
            "INSERT INTO solver_progress (id, total_solved, updated_at)
             VALUES (1, ?1, CURRENT_TIMESTAMP)
             ON CONFLICT(id) DO UPDATE SET total_solved=excluded.total_solved, updated_at=CURRENT_TIMESTAMP",
            [total],
        )?;

        conn.execute("COMMIT", [])?;
        Ok(())
    }

    pub fn submit_batch(&self, payloads: &[SubmitPayload]) -> Result<(usize, usize)> {
        let mut ok = 0usize;
        let mut fail = 0usize;
        for p in payloads {
            match self.submit(p) {
                Ok(()) => ok += 1,
                Err(e) => {
                    fail += 1;
                    tracing::warn!("submit local échoué {} : {}", p.hash, e);
                }
            }
        }
        Ok((ok, fail))
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
