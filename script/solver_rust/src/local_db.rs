//! Persistance SQLite locale — schéma partagé, exploration et résolution sans réseau.

use anyhow::{Context, Result};
use rusqlite::{params, Connection};
use serde_json::Value;
use std::collections::HashSet;
use std::path::Path;
use tracing::info;

use crate::game::Board;
use crate::game::{
    board_from_blob, board_to_blob, board_to_value, empty_cells, parse_board, Position,
};
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
    empty_cells INTEGER,
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
    "ALTER TABLE solver_progress ADD COLUMN current_max_empty INTEGER",
    "ALTER TABLE solver_progress ADD COLUMN max_empty_level_idx INTEGER DEFAULT 0",
    "ALTER TABLE work_queue ADD COLUMN solve_attempts INTEGER DEFAULT 0",
    "ALTER TABLE work_queue ADD COLUMN empty_cells INTEGER",
    // Compaction : plateau stocké en BLOB (2 bits/cellule) au lieu de board_json TEXT.
    "ALTER TABLE positions ADD COLUMN board_blob BLOB",
    "ALTER TABLE positions ADD COLUMN empty_cells INTEGER",
    "ALTER TABLE work_queue ADD COLUMN board_blob BLOB",
    // Backfill du nombre de cases vides (= nombre de '0' dans board_json, valeurs 0/1/2).
    "UPDATE work_queue SET empty_cells = (LENGTH(board_json) - LENGTH(REPLACE(board_json, '0', ''))) WHERE empty_cells IS NULL AND board_json IS NOT NULL",
    "UPDATE positions SET empty_cells = (LENGTH(board_json) - LENGTH(REPLACE(board_json, '0', ''))) WHERE empty_cells IS NULL AND board_json IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_work_queue_empty ON work_queue(empty_cells)",
    "CREATE INDEX IF NOT EXISTS idx_positions_empty ON positions(empty_cells)",
    "CREATE INDEX IF NOT EXISTS idx_positions_solved_at ON positions(solved_at)",
];

/// Lot maximal de claim (aligné solve_batch turbo).
pub const MAX_CLAIM_BATCH: usize = 4096;
/// Seuil de cases vides au-delà duquel une position serait jugée « trop ouverte ».
/// Fixé à 49 (plateau entier) : on autorise la résolution jusqu'à l'ouverture complète.
/// La protection contre les positions vraiment indécidables reste `MAX_SOLVE_ATTEMPTS`
/// (abandon après N échecs), pas un plafond de cases vides.
pub const MAX_UNSOLVABLE_EMPTY: usize = 49;

/// Après ce nombre d'échecs, la position est marquée failed (plus re-claimée).
pub const MAX_SOLVE_ATTEMPTS: i32 = 8;

/// Décode le plateau en `Value` JSON depuis board_blob (prioritaire) ou board_json (repli).
fn decode_board_value(blob: Option<&[u8]>, json: Option<&str>) -> Value {
    if let Some(b) = blob {
        if !b.is_empty() {
            return board_to_value(&board_from_blob(b));
        }
    }
    if let Some(s) = json {
        if !s.is_empty() {
            return serde_json::from_str(s).unwrap_or(Value::Null);
        }
    }
    Value::Null
}

/// Décode le plateau en `Board` depuis board_blob (prioritaire) ou board_json (repli).
fn decode_board(blob: Option<&[u8]>, json: Option<&str>) -> Board {
    if let Some(b) = blob {
        if !b.is_empty() {
            return board_from_blob(b);
        }
    }
    if let Some(s) = json {
        if !s.is_empty() {
            return parse_board(&serde_json::from_str(s).unwrap_or(Value::Null));
        }
    }
    [[0i8; crate::game::BOARD_SIZE]; crate::game::BOARD_SIZE]
}

#[derive(Clone)]
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
             PRAGMA cache_size=-256000; PRAGMA temp_store=MEMORY; PRAGMA mmap_size=268435456;",
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

    pub fn count_in_progress(&self) -> Result<i64> {
        let conn = self.conn()?;
        let n: i64 = conn.query_row(
            "SELECT COUNT(*) FROM work_queue WHERE status='in_progress'",
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

    /// Taille totale de la base sur disque (fichier principal + WAL + SHM), en octets.
    pub fn db_size_bytes(&self) -> u64 {
        let mut total = 0u64;
        for suffix in ["", "-wal", "-shm"] {
            let p = format!("{}{}", self.path, suffix);
            if let Ok(meta) = std::fs::metadata(&p) {
                total += meta.len();
            }
        }
        total
    }

    pub fn load_seed_positions(&self, limit: usize) -> Result<Vec<Position>> {
        let conn = self.conn()?;
        let mut stmt = conn.prepare(
            "SELECT board_blob, board_json, current_player, pos_last_move_row, pos_last_move_col
             FROM positions WHERE (board_blob IS NOT NULL OR board_json IS NOT NULL)
             ORDER BY depth_remaining ASC LIMIT ?",
        )?;
        let rows = stmt.query_map([limit as i64], |row| {
            Ok((
                row.get::<_, Option<Vec<u8>>>(0)?,
                row.get::<_, Option<String>>(1)?,
                row.get::<_, i32>(2)?,
                row.get::<_, Option<i32>>(3)?,
                row.get::<_, Option<i32>>(4)?,
            ))
        })?;

        let mut out = Vec::new();
        for row in rows {
            let (blob, board_json, player, lmr, lmc) = row?;
            let board: Board = decode_board(blob.as_deref(), board_json.as_deref());
            let lm = lmr
                .filter(|&r| r >= 0)
                .map(|r| (r as usize, lmc.unwrap_or(-1).max(0) as usize));
            out.push((board, player as i8, lm));
        }
        Ok(out)
    }

    /// Frontière vers l'ouverture : positions connues (résolues) ayant le plus de cases vides,
    /// avec un coup précédent (pour pouvoir générer les parents). Sert au rétrograde mature.
    /// Le nombre de cases vides est compté via le nombre de '0' dans board_json
    /// (les valeurs n'étant que 0/1/2, un '0' = une case vide exacte).
    pub fn load_frontier_seeds(&self, max_empty: usize, limit: usize) -> Result<Vec<Position>> {
        let conn = self.conn()?;
        let mut stmt = conn.prepare(
            "SELECT board_blob, board_json, current_player, pos_last_move_row, pos_last_move_col
             FROM positions
             WHERE (board_blob IS NOT NULL OR board_json IS NOT NULL)
               AND pos_last_move_row IS NOT NULL AND pos_last_move_row >= 0
               AND empty_cells IS NOT NULL AND empty_cells <= ?1
             ORDER BY empty_cells DESC
             LIMIT ?2",
        )?;
        let rows = stmt.query_map(params![max_empty as i64, limit as i64], |row| {
            Ok((
                row.get::<_, Option<Vec<u8>>>(0)?,
                row.get::<_, Option<String>>(1)?,
                row.get::<_, i32>(2)?,
                row.get::<_, Option<i32>>(3)?,
                row.get::<_, Option<i32>>(4)?,
            ))
        })?;

        let mut out = Vec::new();
        for row in rows {
            let (blob, board_json, player, lmr, lmc) = row?;
            let board: Board = decode_board(blob.as_deref(), board_json.as_deref());
            let lm = lmr
                .filter(|&r| r >= 0)
                .map(|r| (r as usize, lmc.unwrap_or(-1).max(0) as usize));
            out.push((board, player as i8, lm));
        }
        Ok(out)
    }

    pub fn bulk_insert_queue(
        &self,
        positions: &[(String, Vec<u8>, i8, i32, i32, i32)],
    ) -> Result<usize> {
        if positions.is_empty() {
            return Ok(0);
        }
        let conn = self.conn()?;
        conn.execute("BEGIN IMMEDIATE", [])?;
        let mut inserted = 0usize;
        {
            // board_json='' (placeholder pour la contrainte NOT NULL historique) ;
            // le plateau réel est dans board_blob (compacté).
            let mut stmt = conn.prepare(
                "INSERT OR IGNORE INTO work_queue
                 (hash, board_json, board_blob, player, last_move_row, last_move_col, empty_cells, status)
                 VALUES (?1, '', ?2, ?3, ?4, ?5, ?6, 'pending')",
            )?;
            for (hash, board_blob, player, lmr, lmc, empty) in positions {
                let changes = stmt.execute(params![
                    hash,
                    board_blob,
                    *player as i32,
                    lmr,
                    lmc,
                    empty
                ])?;
                inserted += changes;
            }
        }
        let pending_delta = inserted as i64;
        conn.execute(
            "UPDATE solver_progress SET
               total_queued = COALESCE(total_queued, 0) + ?1,
               updated_at = CURRENT_TIMESTAMP
             WHERE id = 1",
            [pending_delta],
        )?;
        conn.execute("COMMIT", [])?;
        Ok(inserted)
    }

    pub fn claim(&self, worker_id: &str, count: usize) -> Result<Vec<ClaimedPosition>> {
        let count = count.clamp(1, MAX_CLAIM_BATCH);
        let conn = self.conn()?;
        conn.execute("BEGIN IMMEDIATE", [])?;

        // Ordre strict par cases vides croissantes : les enfants (moins de vides) sont
        // résolus avant les parents, ce qui rend le lookup 1 coup quasi toujours suffisant.
        let mut stmt = conn.prepare(
            "SELECT hash, board_blob, board_json, player, last_move_row, last_move_col
             FROM work_queue WHERE status = 'pending'
             ORDER BY COALESCE(empty_cells, 99) ASC, created_at ASC LIMIT ?",
        )?;
        let rows: Vec<(String, Option<Vec<u8>>, Option<String>, i32, Option<i32>, Option<i32>)> =
            stmt.query_map([count as i64], |row| {
                Ok((
                    row.get(0)?,
                    row.get(1)?,
                    row.get(2)?,
                    row.get(3)?,
                    row.get(4)?,
                    row.get(5)?,
                ))
            })?
            .collect::<Result<Vec<_>, _>>()?;

        let mut claimed = Vec::with_capacity(rows.len());
        for (hash, board_blob, board_json, player, lmr, lmc) in rows {
            conn.execute(
                "UPDATE work_queue SET status='in_progress', worker_id=?1, claimed_at=CURRENT_TIMESTAMP
                 WHERE hash=?2 AND status='pending'",
                params![worker_id, hash],
            )?;
            let board: Value = decode_board_value(board_blob.as_deref(), board_json.as_deref());
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
                  board_blob, empty_cells, current_player, pos_last_move_row, pos_last_move_col, solved_at)
                 VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,CURRENT_TIMESTAMP)",
            )?;
            // Purge à la soumission : la position est désormais dans `positions`,
            // la ligne work_queue (doublon) est supprimée pour ne pas gonfler la base.
            let mut wq_stmt = conn.prepare("DELETE FROM work_queue WHERE hash=?1")?;

            for payload in payloads {
                let board = parse_board(&payload.board_json);
                let blob = board_to_blob(&board);
                let empty = empty_cells(&board) as i64;
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
                        blob,
                        empty,
                        payload.player,
                        lmr,
                        lmc,
                    ])
                    .is_err()
                {
                    fail += 1;
                    continue;
                }
                let _ = wq_stmt.execute(params![payload.hash]);
                ok += 1;
            }
        }

        let ok_i64 = ok as i64;
        conn.execute(
            "UPDATE solver_progress SET
               total_solved = COALESCE(total_solved, 0) + ?1,
               updated_at = CURRENT_TIMESTAMP
             WHERE id = 1",
            [ok_i64],
        )?;
        conn.execute("COMMIT", [])?;
        Ok((ok, fail))
    }

    /// Marque immédiatement failed (plateau non résoluble / hors limite).
    pub fn fail_bulk(&self, worker_id: &str, hashes: &[String]) -> Result<usize> {
        if hashes.is_empty() {
            return Ok(0);
        }
        let conn = self.conn()?;
        conn.execute("BEGIN IMMEDIATE", [])?;
        let mut stmt = conn.prepare(
            "UPDATE work_queue SET
               status='failed',
               solve_attempts=?3,
               worker_id=NULL,
               claimed_at=NULL
             WHERE hash=?1 AND status='in_progress' AND worker_id=?2",
        )?;
        let mut n = 0usize;
        for hash in hashes {
            n += stmt.execute(params![hash, worker_id, MAX_SOLVE_ATTEMPTS])?;
        }
        drop(stmt);
        conn.execute("COMMIT", [])?;
        Ok(n)
    }

    /// Remet en pending ou marque failed après trop de tentatives.
    pub fn release_bulk(&self, worker_id: &str, hashes: &[String]) -> Result<usize> {
        if hashes.is_empty() {
            return Ok(0);
        }
        let conn = self.conn()?;
        conn.execute("BEGIN IMMEDIATE", [])?;
        let mut stmt = conn.prepare(
            "UPDATE work_queue SET
               solve_attempts = COALESCE(solve_attempts, 0) + 1,
               status = CASE
                 WHEN COALESCE(solve_attempts, 0) + 1 >= ?3 THEN 'failed'
                 ELSE 'pending'
               END,
               worker_id = NULL,
               claimed_at = NULL
             WHERE hash=?1 AND status='in_progress' AND worker_id=?2",
        )?;
        let mut failed = 0usize;
        for hash in hashes {
            if stmt.execute(params![hash, worker_id, MAX_SOLVE_ATTEMPTS])? == 0 {
                continue;
            }
            let status: String = conn.query_row(
                "SELECT status FROM work_queue WHERE hash=?1",
                [hash],
                |r| r.get(0),
            )?;
            if status == "failed" {
                failed += 1;
            }
        }
        drop(stmt);
        conn.execute("COMMIT", [])?;
        Ok(failed)
    }

    /// Remet en pending les claims expirés (solveur planté ou arrêt brutal).
    pub fn sync_exploration_level(&self, level_idx: usize, max_empty: usize) -> Result<()> {
        let conn = self.conn()?;
        conn.execute(
            "UPDATE solver_progress SET
               current_max_empty = ?1,
               max_empty_level_idx = ?2,
               updated_at = CURRENT_TIMESTAMP
             WHERE id = 1",
            params![max_empty as i64, level_idx as i64],
        )?;
        Ok(())
    }

    pub fn reclaim_stale_in_progress(&self, timeout_sec: i64) -> Result<usize> {
        let conn = self.conn()?;
        let modifier = format!("-{timeout_sec} seconds");
        let n = conn.execute(
            "UPDATE work_queue SET status='pending', worker_id=NULL, claimed_at=NULL
             WHERE status='in_progress' AND (
               claimed_at IS NULL
               OR datetime(claimed_at) < datetime('now', ?1)
             )",
            [modifier],
        )?;
        Ok(n)
    }

    pub fn requeue_failed(&self) -> Result<usize> {
        let conn = self.conn()?;
        let mut stmt = conn.prepare(
            "SELECT hash, board_blob, board_json FROM work_queue WHERE status='failed'",
        )?;
        let rows: Vec<(String, Option<Vec<u8>>, Option<String>)> = stmt
            .query_map([], |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)))
            .and_then(|iter| iter.collect())?;
        drop(stmt);

        let mut n = 0usize;
        for (hash, blob, board_json) in rows {
            let board = decode_board(blob.as_deref(), board_json.as_deref());
            if empty_cells(&board) > MAX_UNSOLVABLE_EMPTY {
                continue;
            }
            n += conn.execute(
                "UPDATE work_queue SET status='pending', solve_attempts=0, worker_id=NULL, claimed_at=NULL
                 WHERE hash=?1 AND status='failed'",
                [&hash],
            )?;
        }
        Ok(n)
    }

    /// Itère toutes les positions résolues (hash, result, depth_remaining) — chargement ResultTable.
    pub fn for_each_solved<F: FnMut(&str, &str, i64)>(&self, mut f: F) -> Result<usize> {
        let conn = self.conn()?;
        let mut stmt =
            conn.prepare("SELECT hash, result, COALESCE(depth_remaining, 0) FROM positions")?;
        let mut rows = stmt.query([])?;
        let mut n = 0usize;
        while let Some(row) = rows.next()? {
            let hash: String = row.get(0)?;
            let result: String = row.get(1)?;
            let depth: i64 = row.get(2)?;
            f(&hash, &result, depth);
            n += 1;
        }
        Ok(n)
    }

    /// Échantillon de positions résolues (≤ max_empty cases vides) pour la non-régression.
    /// Renvoie (board_json, player, last_move_row, last_move_col, result, best_row, best_col).
    #[allow(clippy::type_complexity)]
    pub fn fetch_solved_sample(
        &self,
        max_empty: usize,
        limit: usize,
    ) -> Result<Vec<(String, i32, Option<i32>, Option<i32>, String, Option<i32>, Option<i32>)>> {
        let conn = self.conn()?;
        let mut stmt = conn.prepare(
            "SELECT board_blob, board_json, current_player, pos_last_move_row, pos_last_move_col,
                    result, best_move_row, best_move_col
             FROM positions
             WHERE (board_blob IS NOT NULL OR board_json IS NOT NULL) AND current_player IS NOT NULL
               AND empty_cells IS NOT NULL AND empty_cells <= ?1
             LIMIT ?2",
        )?;
        let rows = stmt
            .query_map(params![max_empty as i64, limit as i64], |row| {
                let blob: Option<Vec<u8>> = row.get(0)?;
                let json: Option<String> = row.get(1)?;
                let board_str =
                    serde_json::to_string(&decode_board_value(blob.as_deref(), json.as_deref()))
                        .unwrap_or_else(|_| "null".to_string());
                Ok((
                    board_str,
                    row.get::<_, i32>(2)?,
                    row.get::<_, Option<i32>>(3)?,
                    row.get::<_, Option<i32>>(4)?,
                    row.get::<_, String>(5)?,
                    row.get::<_, Option<i32>>(6)?,
                    row.get::<_, Option<i32>>(7)?,
                ))
            })?
            .collect::<Result<Vec<_>, _>>()?;
        Ok(rows)
    }

    pub fn count_failed(&self) -> Result<i64> {
        let conn = self.conn()?;
        let n: i64 = conn.query_row(
            "SELECT COUNT(*) FROM work_queue WHERE status='failed'",
            [],
            |r| r.get(0),
        )?;
        Ok(n)
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

    /// Compaction one-shot : convertit board_json → board_blob (2 bits/cellule),
    /// libère board_json, purge les doublons work_queue `done`, puis VACUUM.
    pub fn compact(&self) -> Result<()> {
        let conn = self.conn()?;

        // 1. positions : board_json (TEXT) → board_blob (BLOB), board_json=NULL.
        let mut total_pos = 0usize;
        loop {
            let batch: Vec<(String, String)> = {
                let mut stmt = conn.prepare(
                    "SELECT hash, board_json FROM positions
                     WHERE board_blob IS NULL AND board_json IS NOT NULL LIMIT 20000",
                )?;
                let rows = stmt
                    .query_map([], |r| Ok((r.get(0)?, r.get(1)?)))?
                    .collect::<Result<Vec<_>, _>>()?;
                rows
            };
            if batch.is_empty() {
                break;
            }
            conn.execute("BEGIN IMMEDIATE", [])?;
            {
                let mut up = conn.prepare(
                    "UPDATE positions SET board_blob=?2, empty_cells=?3, board_json=NULL WHERE hash=?1",
                )?;
                for (hash, json) in &batch {
                    let board = parse_board(&serde_json::from_str(json).unwrap_or(Value::Null));
                    up.execute(params![hash, board_to_blob(&board), empty_cells(&board) as i64])?;
                }
            }
            conn.execute("COMMIT", [])?;
            total_pos += batch.len();
            info!("Compaction positions : {} converties", total_pos);
        }

        // 2. Purge des doublons work_queue déjà résolus (avant conversion, pour ne pas
        //    convertir des lignes qu'on supprime aussitôt).
        let deleted = conn.execute("DELETE FROM work_queue WHERE status='done'", [])?;

        // 3. work_queue restante (pending/in_progress) : board_json → board_blob, board_json=''.
        let mut total_wq = 0usize;
        loop {
            let batch: Vec<(String, String)> = {
                let mut stmt = conn.prepare(
                    "SELECT hash, board_json FROM work_queue
                     WHERE board_blob IS NULL AND board_json IS NOT NULL AND board_json != '' LIMIT 20000",
                )?;
                let rows = stmt
                    .query_map([], |r| Ok((r.get(0)?, r.get(1)?)))?
                    .collect::<Result<Vec<_>, _>>()?;
                rows
            };
            if batch.is_empty() {
                break;
            }
            conn.execute("BEGIN IMMEDIATE", [])?;
            {
                let mut up = conn.prepare(
                    "UPDATE work_queue SET board_blob=?2, empty_cells=COALESCE(empty_cells,?3), board_json='' WHERE hash=?1",
                )?;
                for (hash, json) in &batch {
                    let board = parse_board(&serde_json::from_str(json).unwrap_or(Value::Null));
                    up.execute(params![hash, board_to_blob(&board), empty_cells(&board) as i64])?;
                }
            }
            conn.execute("COMMIT", [])?;
            total_wq += batch.len();
        }

        info!(
            "Compaction : {} positions converties, {} work_queue converties, {} 'done' purgées — VACUUM…",
            total_pos, total_wq, deleted
        );

        // 4. Récupération de l'espace disque.
        conn.execute_batch("VACUUM")?;
        info!("Compaction terminée (VACUUM ok).");
        Ok(())
    }
}
