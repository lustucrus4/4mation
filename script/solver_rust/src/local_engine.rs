//! Moteur solveur local — exploration + résolution parallèle + SQLite.

use anyhow::Result;
use rayon::prelude::*;
use serde_json::Value;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tracing::{info, warn};

use crate::explorer::ExplorerState;
use crate::game::{parse_board, Board, Position};
use crate::hasher::PositionHasher;
use crate::local_db::LocalDb;
use crate::solver::{RetrogradeSolver, SolvedPosition};
use crate::work::{parse_last_move, ClaimedPosition, SubmitMove, SubmitPayload};

const IDLE_SLEEP_SEC: f64 = 2.0;
const STATS_INTERVAL_SEC: f64 = 30.0;
const EXPLORE_BATCH: usize = 5000;
const INSERT_CHUNK: usize = 2000;
const SEED_LIMIT: usize = 20000;

pub struct LocalConfig {
    pub threads: usize,
    pub max_empty: usize,
    pub solve_batch: usize,
    pub min_pending: usize,
    pub max_iterations: Option<u64>,
    pub once: bool,
}

struct Stats {
    solved: AtomicU64,
    failed: AtomicU64,
    explored: AtomicU64,
}

fn board_to_json(board: &Board) -> Value {
    let rows: Vec<Vec<i8>> = board.iter().map(|r| r.to_vec()).collect();
    serde_json::to_value(rows).unwrap_or(Value::Null)
}

fn position_to_queue_row(pos: &Position) -> (String, String, i8, i32, i32) {
    let (board, player, last_move) = pos;
    let hash = PositionHasher::hash_key(board, *player, *last_move);
    let board_json = serde_json::to_string(&board_to_json(board)).unwrap_or_default();
    let (lmr, lmc) = last_move
        .map(|(r, c)| (r as i32, c as i32))
        .unwrap_or((-1, -1));
    (hash, board_json, *player, lmr, lmc)
}

pub fn solve_claimed(pos: &ClaimedPosition, max_empty: usize) -> Option<SubmitPayload> {
    let board: Board = parse_board(&pos.board_json);
    let player = pos.player as i8;
    let last_move = parse_last_move(&pos.last_move);

    let mut solver = RetrogradeSolver::new(max_empty);
    let solved: SolvedPosition = solver.solve_position(&board, player, last_move)?;

    let best_move = solved.best_move.map(|(r, c)| SubmitMove {
        row: r as i32,
        col: c as i32,
    });

    Some(SubmitPayload {
        hash: pos.hash.clone(),
        result: solved.result,
        win_rate: solved.win_rate,
        best_move,
        depth_remaining: solved.depth_remaining,
        board_json: pos.board_json.clone(),
        player: pos.player,
        last_move: pos.last_move.clone(),
        worker_id: String::new(),
    })
}

fn solve_batch(
    positions: &[ClaimedPosition],
    max_empty: usize,
    worker_id: &str,
) -> (Vec<SubmitPayload>, Vec<String>) {
    let results: Vec<(Option<SubmitPayload>, Option<String>)> = positions
        .par_iter()
        .map(|pos| match solve_claimed(pos, max_empty) {
            Some(mut s) => {
                s.worker_id = worker_id.to_string();
                (Some(s), None)
            }
            None => (None, Some(pos.hash.clone())),
        })
        .collect();

    let mut submits = Vec::new();
    let mut releases = Vec::new();
    for (sub, rel) in results {
        if let Some(s) = sub {
            submits.push(s);
        }
        if let Some(h) = rel {
            releases.push(h);
        }
    }
    (submits, releases)
}

fn explore_and_enqueue(
    db: &LocalDb,
    explorer: &mut ExplorerState,
    target: usize,
    stats: &Stats,
) -> Result<usize> {
    let seeds = db.load_seed_positions(SEED_LIMIT).unwrap_or_default();

    let mut positions = Vec::new();
    let mut phase_attempts = 0usize;
    const MAX_PHASE_ATTEMPTS: usize = 8;

    while positions.len() < target && phase_attempts < MAX_PHASE_ATTEMPTS {
        let batch = explorer.next_batch(target - positions.len(), &seeds);
        if batch.is_empty() {
            explorer.advance_phase();
            phase_attempts += 1;
            continue;
        }
        positions.extend(batch);
        phase_attempts = 0;
    }

    if positions.is_empty() {
        return Ok(0);
    }

    let rows: Vec<_> = positions.iter().map(position_to_queue_row).collect();
    let mut total_inserted = 0usize;

    for chunk in rows.chunks(INSERT_CHUNK) {
        let n = db.bulk_insert_queue(chunk)?;
        total_inserted += n;
    }

    stats.explored.fetch_add(positions.len() as u64, Ordering::Relaxed);
    Ok(total_inserted)
}

pub fn run_local_engine(
    db: &LocalDb,
    worker_id: &str,
    cfg: &LocalConfig,
    shutdown: Option<&std::sync::atomic::AtomicBool>,
) -> Result<()> {
    rayon::ThreadPoolBuilder::new()
        .num_threads(cfg.threads)
        .build_global()
        .map_err(|e| anyhow::anyhow!("pool rayon : {e}"))?;

    let known = db.known_hashes_full()?;
    let mut explorer = ExplorerState::new(cfg.max_empty, known);

    let seeds = db.load_seed_positions(SEED_LIMIT).unwrap_or_default();
    if seeds.is_empty() {
        explorer.mode = crate::explorer::ExplorationMode::Forward;
        explorer.init_bfs();
        info!(
            "Peu de graines rétrograde — démarrage en BFS forward (conseil : lancer build_endgame_tablebase.py une fois)"
        );
    }

    let stats = Arc::new(Stats {
        solved: AtomicU64::new(0),
        failed: AtomicU64::new(0),
        explored: AtomicU64::new(0),
    });

    let solved_start = db.count_solved().unwrap_or(0);
    info!(
        "4mation-local — threads={}, max_empty={}, solve_batch={}, min_pending={}, résolues={}",
        cfg.threads,
        cfg.max_empty,
        cfg.solve_batch,
        cfg.min_pending,
        solved_start
    );

    let mut last_stats = Instant::now();
    let mut idle_rounds = 0u32;

    loop {
        if shutdown.is_some_and(|s| s.load(Ordering::Relaxed)) {
            info!("Arrêt demandé via dashboard — sortie");
            break;
        }

        if let Some(max) = cfg.max_iterations {
            if stats.solved.load(Ordering::Relaxed) >= max {
                info!("Limite {} atteinte — arrêt", max);
                break;
            }
        }

        let pending = db.count_pending().unwrap_or(0) as usize;

        if pending < cfg.min_pending {
            let target = EXPLORE_BATCH.max(cfg.min_pending - pending);
            match explore_and_enqueue(db, &mut explorer, target, &stats) {
                Ok(n) if n > 0 => {
                    info!(
                        "+{} en queue (pending≈{}, max_empty={})",
                        n,
                        pending + n,
                        explorer.max_empty
                    );
                    idle_rounds = 0;
                }
                Ok(_) => {
                    idle_rounds += 1;
                    if idle_rounds >= 3 {
                        warn!("Exploration stagne — pause {:.0}s", IDLE_SLEEP_SEC);
                        std::thread::sleep(Duration::from_secs_f64(IDLE_SLEEP_SEC));
                    }
                }
                Err(e) => warn!("exploration : {:#}", e),
            }
        }

        let positions = match db.claim(worker_id, cfg.solve_batch) {
            Ok(p) => p,
            Err(e) => {
                warn!("claim : {:#}", e);
                std::thread::sleep(Duration::from_secs_f64(IDLE_SLEEP_SEC));
                continue;
            }
        };

        if positions.is_empty() {
            if cfg.once {
                break;
            }
            std::thread::sleep(Duration::from_secs_f64(IDLE_SLEEP_SEC));
            continue;
        }

        let max_empty = cfg.max_empty;
        let (submits, releases) = solve_batch(&positions, max_empty, worker_id);

        for hash in releases {
            let _ = db.release(worker_id, &hash);
        }

        match db.submit_bulk(&submits) {
            Ok((ok, fail)) => {
                stats.solved.fetch_add(ok as u64, Ordering::Relaxed);
                stats.failed.fetch_add(fail as u64, Ordering::Relaxed);
                info!(
                    "Résolu {} positions (échecs={}, total session={})",
                    ok,
                    fail,
                    stats.solved.load(Ordering::Relaxed)
                );
            }
            Err(e) => warn!("submit bulk : {:#}", e),
        }

        if last_stats.elapsed().as_secs_f64() >= STATS_INTERVAL_SEC {
            let total = db.count_solved().unwrap_or(0);
            info!(
                "Stats — session résolues={}, échecs={}, explorées={}, total DB={}, pending={}",
                stats.solved.load(Ordering::Relaxed),
                stats.failed.load(Ordering::Relaxed),
                stats.explored.load(Ordering::Relaxed),
                total,
                db.count_pending().unwrap_or(0)
            );
            last_stats = Instant::now();
        }

        if cfg.once {
            break;
        }
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::game::BOARD_SIZE;

    #[test]
    fn board_json_shape() {
        let board = [[0i8; BOARD_SIZE]; BOARD_SIZE];
        let j = board_to_json(&board);
        assert_eq!(j.as_array().map(|a| a.len()), Some(BOARD_SIZE));
    }
}
