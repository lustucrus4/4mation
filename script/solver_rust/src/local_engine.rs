//! Moteur solveur local — exploration en arrière-plan + résolution parallèle + SQLite pipeliné.

use anyhow::Result;
use rayon::prelude::*;
use serde_json::Value;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};
use tracing::{info, warn};

use crate::explorer::ExplorerState;
use crate::game::{empty_cells, parse_board, Board, Position};
use crate::hasher::PositionHasher;
use crate::local_db::LocalDb;
use crate::result_table::ResultTable;
use crate::solver::{resolve_via_children, RetrogradeSolver};
use crate::work::{parse_last_move, ClaimedPosition, SubmitMove, SubmitPayload};

const STATS_INTERVAL_SEC: f64 = 30.0;
const SYNC_LEVEL_EVERY: u32 = 20;
const EXPLORE_BATCH: usize = 20_000;
const INSERT_CHUNK: usize = 4000;
const SEED_LIMIT: usize = 20_000;
const EXPLORER_POLL_MS: u64 = 25;
const EMPTY_QUEUE_SPIN_MS: u64 = 5;
/// Pause minimale sur un niveau max_empty avant de passer au suivant (base mature).
const LEVEL_DWELL_SEC: f64 = 60.0;
const LEVEL_DWELL_MATURE_SEC: f64 = 8.0;
const IDLE_ROUNDS_BEFORE_ADVANCE: u32 = 24;
const IDLE_ROUNDS_MATURE: u32 = 3;
const RECLAIM_IDLE_EVERY: u32 = 40;

/// Base mature : plafond de cases vides initial du rétrograde de frontière.
/// On étend la base connue vers l'ouverture, et ce plafond est relevé automatiquement
/// d'un cran dès qu'un niveau est saturé (voir `FRONTIER_MAX`).
const FRONTIER_CAP: usize = 20;
/// Plafond maximal d'extension automatique du cap. Fixé au plateau entier (49)
/// via `MAX_UNSOLVABLE_EMPTY` : l'explorateur remonte jusqu'à l'ouverture complète.
/// En pratique c'est le plafond de stockage 5 Go qui arrête l'exploration avant.
const FRONTIER_MAX: usize = crate::local_db::MAX_UNSOLVABLE_EMPTY;
/// Passes idle consécutives (réamorçage = 0 nouveau parent) avant de relever le cap.
const FRONTIER_ADVANCE_IDLE: u32 = 2;
/// Nombre de graines de frontière rechargées depuis la DB à chaque réamorçage.
const FRONTIER_SEED_LIMIT: usize = 60_000;
/// Seuil de base "mature" (bascule sur le rétrograde de frontière).
const MATURE_THRESHOLD: usize = 600_000;

/// Plafond de taille de la base : au-delà, l'exploration se met en pause
/// (le solveur continue à drainer le pending). ~5 Go.
const MAX_DB_BYTES: u64 = 5 * 1024 * 1024 * 1024;

/// Sommeil découpé en tranches de 100 ms, interrompu dès que `shutdown` est levé
/// (réactivité de l'arrêt via dashboard, même en veille).
fn sleep_interruptible(shutdown: &AtomicBool, total_ms: u64) {
    let mut left = total_ms;
    while left > 0 {
        if shutdown.load(Ordering::Relaxed) {
            return;
        }
        let chunk = left.min(100);
        thread::sleep(Duration::from_millis(chunk));
        left -= chunk;
    }
}

/// Vrai si la base a atteint le plafond de stockage (exploration à suspendre).
/// Journalise au plus une fois toutes les 30 s.
fn storage_capped(db: &LocalDb, last_log: &mut Instant) -> bool {
    let size = db.db_size_bytes();
    if size >= MAX_DB_BYTES {
        if last_log.elapsed().as_secs_f64() >= 30.0 {
            info!(
                "Plafond stockage atteint ({:.2} Go ≥ {:.0} Go) — exploration en pause, drainage du pending",
                size as f64 / 1e9,
                MAX_DB_BYTES as f64 / 1e9
            );
            *last_log = Instant::now();
        }
        return true;
    }
    false
}

#[derive(Clone)]
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

struct PersistResult {
    ok: usize,
    fail: usize,
}

fn board_to_json(board: &Board) -> Value {
    let rows: Vec<Vec<i8>> = board.iter().map(|r| r.to_vec()).collect();
    serde_json::to_value(rows).unwrap_or(Value::Null)
}

fn position_to_queue_row(pos: &Position) -> (String, Vec<u8>, i8, i32, i32, i32) {
    let (board, player, last_move) = if PositionHasher::symmetry_enabled() {
        crate::symmetry::canonical_position(&pos.0, pos.1, pos.2)
    } else {
        pos.clone()
    };
    let hash = PositionHasher::hash_key(&board, player, last_move);
    let board_blob = crate::game::board_to_blob(&board);
    let (lmr, lmc) = last_move
        .map(|(r, c)| (r as i32, c as i32))
        .unwrap_or((-1, -1));
    let empty = empty_cells(&board) as i32;
    (hash, board_blob, player, lmr, lmc, empty)
}

pub fn solve_claimed(
    pos: &ClaimedPosition,
    max_empty: usize,
    oracle: &ResultTable,
) -> Option<SubmitPayload> {
    let board: Board = parse_board(&pos.board_json);
    let player = pos.player as i8;
    let last_move = parse_last_move(&pos.last_move);

    let make_payload = |solved: crate::solver::SolvedPosition| {
        let best_move = solved.best_move.map(|(r, c)| SubmitMove {
            row: r as i32,
            col: c as i32,
        });
        SubmitPayload {
            hash: pos.hash.clone(),
            result: solved.result,
            win_rate: solved.win_rate,
            best_move,
            depth_remaining: solved.depth_remaining,
            board_json: pos.board_json.clone(),
            player: pos.player,
            last_move: pos.last_move.clone(),
            worker_id: String::new(),
        }
    };

    // Chemin chaud : résolution 1 coup via la tablebase (enfants déjà connus).
    if let Some(solved) = resolve_via_children(&board, player, last_move, oracle) {
        return Some(make_payload(solved));
    }

    // Repli : recherche alpha-bêta avec consultation de l'oracle aux nœuds.
    let empty = empty_cells(&board);
    let solve_depth = max_empty.max(empty);
    for budget_mult in [1usize, 2, 4] {
        let mut solver = RetrogradeSolver::for_board_scaled(solve_depth, empty, budget_mult);
        if let Some(solved) = solver.solve_with_oracle(&board, player, last_move, Some(oracle)) {
            return Some(make_payload(solved));
        }
    }

    None
}

const MAX_SOLVE_EMPTY: usize = crate::local_db::MAX_UNSOLVABLE_EMPTY;

fn solve_batch(
    positions: &[ClaimedPosition],
    max_empty: usize,
    worker_id: &str,
    oracle: &ResultTable,
) -> (Vec<SubmitPayload>, Vec<String>, Vec<String>) {
    let results: Vec<(Option<SubmitPayload>, Option<String>, Option<String>)> = positions
        .par_iter()
        .map(|pos| {
            let empty = empty_cells(&parse_board(&pos.board_json));
            if empty > MAX_SOLVE_EMPTY {
                return (None, None, Some(pos.hash.clone()));
            }
            match solve_claimed(pos, max_empty, oracle) {
                Some(mut s) => {
                    s.worker_id = worker_id.to_string();
                    (Some(s), None, None)
                }
                None => (None, Some(pos.hash.clone()), None),
            }
        })
        .collect();

    let mut submits = Vec::with_capacity(positions.len());
    let mut releases = Vec::new();
    let mut unsolvable = Vec::new();
    for (sub, rel, skip) in results {
        if let Some(s) = sub {
            submits.push(s);
        }
        if let Some(h) = rel {
            releases.push(h);
        }
        if let Some(h) = skip {
            unsolvable.push(h);
        }
    }
    (submits, releases, unsolvable)
}

fn explore_batch(
    db: &LocalDb,
    explorer: &mut ExplorerState,
    seeds: &[Position],
    target: usize,
    stats: &Stats,
    mature_base: bool,
) -> Result<usize> {
    let node_limit = if mature_base {
        crate::explorer::MAX_NODES_MATURE
    } else {
        crate::explorer::MAX_NODES_PER_BATCH
    };
    let batch = explorer.next_batch_limited(target, seeds, node_limit);
    if batch.is_empty() {
        return Ok(0);
    }

    let rows: Vec<_> = batch.iter().map(position_to_queue_row).collect();
    let mut total_inserted = 0usize;
    for chunk in rows.chunks(INSERT_CHUNK) {
        total_inserted += db.bulk_insert_queue(chunk)?;
    }

    stats.explored.fetch_add(batch.len() as u64, Ordering::Relaxed);
    Ok(total_inserted)
}

fn sync_explorer_progress(db: &LocalDb, explorer: &Arc<Mutex<ExplorerState>>) {
    if let Ok(ex) = explorer.lock() {
        let _ = db.sync_exploration_level(ex.level_idx, ex.max_empty);
    }
}

fn spawn_explorer_thread(
    db: LocalDb,
    explorer: Arc<Mutex<ExplorerState>>,
    seeds: Arc<Vec<Position>>,
    stats: Arc<Stats>,
    cfg: LocalConfig,
    shutdown: Arc<AtomicBool>,
    known_count: usize,
) -> JoinHandle<()> {
    thread::Builder::new()
        .name("4mation-explorer".into())
        .spawn(move || {
            if known_count > MATURE_THRESHOLD {
                frontier_explorer_loop(&db, &explorer, &stats, &cfg, &shutdown);
            } else {
                legacy_explorer_loop(&db, &explorer, &seeds, &stats, &cfg, &shutdown, known_count);
            }
        })
        .expect("thread explorer")
}

/// Rétrograde de frontière (base mature) : étend la base connue vers l'ouverture.
/// Recharge périodiquement la frontière (positions les plus ouvertes) depuis la DB,
/// génère leurs parents, et alimente la file de travail en continu jusqu'à épuisement.
fn frontier_explorer_loop(
    db: &LocalDb,
    explorer: &Arc<Mutex<ExplorerState>>,
    stats: &Stats,
    cfg: &LocalConfig,
    shutdown: &AtomicBool,
) {
    let mut cap = FRONTIER_CAP;
    let high_water = cfg.min_pending.max(EXPLORE_BATCH);
    let low_water = (cfg.min_pending / 2).max(200);

    if let Ok(mut ex) = explorer.lock() {
        ex.set_frontier_mode(cap);
    }
    info!(
        "Explorateur frontière — extension rétrograde vers l'ouverture, cap initial={cap}, auto-extension jusqu'à max_empty={FRONTIER_MAX} (cible pending={high_water})"
    );

    // Amorçage initial depuis la DB.
    reseed_frontier(db, explorer, cap);

    let mut idle_passes = 0u32;
    let mut last_heartbeat = Instant::now();
    let mut last_cap_log = Instant::now() - Duration::from_secs(60);
    let mut frontier_complete = false;

    loop {
        if shutdown.load(Ordering::Relaxed) {
            break;
        }

        if storage_capped(db, &mut last_cap_log) {
            sleep_interruptible(shutdown, 5000);
            continue;
        }

        let pending = db.count_pending().unwrap_or(0) as usize;
        if pending >= high_water {
            thread::sleep(Duration::from_millis(EXPLORER_POLL_MS));
            continue;
        }

        let target = (high_water - pending).max(EXPLORE_BATCH.min(high_water));
        let inserted = {
            let mut ex = match explorer.lock() {
                Ok(g) => g,
                Err(_) => break,
            };
            match explore_batch(db, &mut ex, &[], target, stats, true) {
                Ok(n) => n,
                Err(e) => {
                    warn!("frontière insert : {:#}", e);
                    thread::sleep(Duration::from_millis(200));
                    continue;
                }
            }
        };

        if inserted > 0 {
            idle_passes = 0;
            continue;
        }

        // File rétrograde drainée : recharger la frontière depuis la DB
        // (de nouvelles positions ont pu être résolues entre-temps).
        let queue_len = explorer.lock().map(|ex| ex.retro_queue_len()).unwrap_or(0);
        if queue_len == 0 {
            let added = reseed_frontier(db, explorer, cap);
            if added > 0 {
                idle_passes = 0;
                continue;
            }
            idle_passes = idle_passes.saturating_add(1);

            // Niveau courant saturé (plus aucun parent à générer) → on relève le cap
            // automatiquement d'un cran pour continuer vers l'ouverture, sans jamais s'arrêter.
            if idle_passes >= FRONTIER_ADVANCE_IDLE && cap < FRONTIER_MAX {
                cap += 1;
                if let Ok(mut ex) = explorer.lock() {
                    ex.set_frontier_mode(cap);
                }
                let lvl_idx = crate::explorer::MAX_EMPTY_LEVELS
                    .iter()
                    .position(|&l| l >= cap)
                    .unwrap_or(crate::explorer::MAX_EMPTY_LEVELS.len() - 1);
                let _ = db.sync_exploration_level(lvl_idx, cap);
                let seeded = reseed_frontier(db, explorer, cap);
                info!(
                    "Niveau saturé — cap relevé automatiquement à max_empty={cap} ({seeded} parents amorcés)"
                );
                idle_passes = 0;
                frontier_complete = false;
                continue;
            }
        }

        // Rien de nouveau à étendre pour l'instant : le solveur rattrape ou la frontière est complète.
        if cap >= FRONTIER_MAX && idle_passes >= FRONTIER_ADVANCE_IDLE && !frontier_complete {
            warn!(
                "Frontière complète jusqu'à la limite soluble max_empty={FRONTIER_MAX} — exploration terminée (relancer avec une limite plus profonde pour aller plus loin)."
            );
            frontier_complete = true;
        }
        if last_heartbeat.elapsed().as_secs_f64() >= 15.0 {
            let in_prog = db.count_in_progress().unwrap_or(0);
            info!(
                "Frontière max_empty={cap} — pending={pending}, in_progress={in_prog}, attente (passes idle={idle_passes})"
            );
            last_heartbeat = Instant::now();
        }
        let wait_ms = if idle_passes > 4 { 4000 } else { 800 };
        sleep_interruptible(shutdown, wait_ms);
    }
}

/// Recharge la frontière depuis la DB et met en file les parents non connus.
fn reseed_frontier(db: &LocalDb, explorer: &Arc<Mutex<ExplorerState>>, cap: usize) -> usize {
    let seeds = match db.load_frontier_seeds(cap.saturating_sub(1), FRONTIER_SEED_LIMIT) {
        Ok(s) => s,
        Err(e) => {
            warn!("chargement frontière : {:#}", e);
            return 0;
        }
    };
    if seeds.is_empty() {
        return 0;
    }
    explorer
        .lock()
        .map(|mut ex| ex.extend_retrograde(&seeds))
        .unwrap_or(0)
}

fn legacy_explorer_loop(
    db: &LocalDb,
    explorer: &Arc<Mutex<ExplorerState>>,
    seeds: &Arc<Vec<Position>>,
    stats: &Stats,
    cfg: &LocalConfig,
    shutdown: &AtomicBool,
    known_count: usize,
) {
    {
            let high_water = if known_count > 600_000 {
                cfg.min_pending
            } else {
                cfg.min_pending.saturating_mul(4).max(EXPLORE_BATCH / 2)
            };
            let mature_base = known_count > 600_000;
            let dwell_sec = if mature_base {
                LEVEL_DWELL_MATURE_SEC
            } else {
                LEVEL_DWELL_SEC
            };
            let idle_before_advance = if mature_base {
                IDLE_ROUNDS_MATURE
            } else {
                IDLE_ROUNDS_BEFORE_ADVANCE
            };
            let mut idle_rounds = 0u32;
            let mut last_level_advance = Instant::now();
            let mut last_cap_log = Instant::now() - Duration::from_secs(60);

            loop {
                if shutdown.load(Ordering::Relaxed) {
                    break;
                }

                if storage_capped(db, &mut last_cap_log) {
                    sleep_interruptible(shutdown, 5000);
                    continue;
                }

                let pending = match db.count_pending() {
                    Ok(n) => n as usize,
                    Err(e) => {
                        warn!("explorer count_pending : {:#}", e);
                        thread::sleep(Duration::from_millis(200));
                        continue;
                    }
                };

                if pending >= high_water {
                    thread::sleep(Duration::from_millis(EXPLORER_POLL_MS));
                    continue;
                }

                // Base mature : vider la file avant d'explorer davantage
                if mature_base && pending >= cfg.min_pending / 2 {
                    thread::sleep(Duration::from_secs(1));
                    continue;
                }

                let target = if mature_base {
                    cfg.min_pending.min(EXPLORE_BATCH)
                } else {
                    EXPLORE_BATCH.max(high_water.saturating_sub(pending))
                };
                let inserted = {
                    let mut ex = match explorer.lock() {
                        Ok(g) => g,
                        Err(_) => break,
                    };
                    match explore_batch(db, &mut ex, seeds, target, stats, mature_base) {
                        Ok(n) => n,
                        Err(e) => {
                            warn!("explorer insert : {:#}", e);
                            thread::sleep(Duration::from_millis(200));
                            continue;
                        }
                    }
                };

                if inserted > 0 {
                    idle_rounds = 0;
                    sync_explorer_progress(db, explorer);
                } else {
                    let exhausted = explorer
                        .lock()
                        .map(|ex| ex.is_exhausted())
                        .unwrap_or(false);
                    idle_rounds += if exhausted {
                        idle_before_advance
                    } else {
                        1
                    };
                    let dwell_ok =
                        last_level_advance.elapsed().as_secs_f64() >= dwell_sec;
                    if idle_rounds >= idle_before_advance && dwell_ok {
                        let mut ex = match explorer.lock() {
                            Ok(g) => g,
                            Err(_) => break,
                        };
                        if ex.advance_phase() {
                            idle_rounds = 0;
                            last_level_advance = Instant::now();
                            sync_explorer_progress(db, explorer);
                        } else {
                            // Recyclage complet — longue pause avant de recommencer
                            last_level_advance = Instant::now();
                            idle_rounds = 0;
                            info!(
                                "Exploration en pause {:.0}s après recyclage (base quasi complète)",
                                dwell_sec * 2.0
                            );
                            thread::sleep(Duration::from_secs_f64(dwell_sec * 2.0));
                        }
                    } else if idle_rounds % 5 == 0 {
                        let pending_n = db.count_pending().unwrap_or(0);
                        if let Ok(ex) = explorer.lock() {
                            let mode_s = if ex.mode == crate::explorer::ExplorationMode::Forward {
                                "forward"
                            } else {
                                "rétrograde"
                            };
                            let wait = (dwell_sec
                                - last_level_advance.elapsed().as_secs_f64())
                            .max(0.0);
                            info!(
                                "Exploration {mode_s} max_empty={} — pending={pending_n}, palier suivant ≤{wait:.0}s",
                                ex.max_empty
                            );
                        }
                    } else {
                        thread::sleep(Duration::from_millis(500));
                    }
                }
            }
    }
}

fn spawn_persist(
    db: LocalDb,
    worker_id: String,
    submits: Vec<SubmitPayload>,
    releases: Vec<String>,
    unsolvable: Vec<String>,
    table: Arc<ResultTable>,
) -> JoinHandle<PersistResult> {
    thread::Builder::new()
        .name("4mation-persist".into())
        .spawn(move || {
            if !unsolvable.is_empty() {
                match db.fail_bulk(&worker_id, &unsolvable) {
                    Ok(n) if n > 0 => {
                        warn!("{n} positions hors limite marquées failed (>{MAX_SOLVE_EMPTY} cases vides)");
                    }
                    Err(e) => warn!("fail_bulk : {:#}", e),
                    _ => {}
                }
            }
            if !releases.is_empty() {
                match db.release_bulk(&worker_id, &releases) {
                    Ok(n_failed) if n_failed > 0 => {
                        warn!(
                            "{n_failed} positions marquées failed après {} tentatives",
                            crate::local_db::MAX_SOLVE_ATTEMPTS
                        );
                    }
                    Err(e) => warn!("release_bulk : {:#}", e),
                    _ => {}
                }
            }
            match db.submit_bulk(&submits) {
                Ok((ok, fail)) => {
                    // Met à jour la tablebase chaude : les parents des lots suivants
                    // verront immédiatement ces enfants (résolution 1 coup).
                    for p in &submits {
                        table.insert_hash_hex(&p.hash, p.result, p.depth_remaining);
                    }
                    PersistResult { ok, fail }
                }
                Err(e) => {
                    warn!("submit_bulk : {:#}", e);
                    PersistResult {
                        ok: 0,
                        fail: submits.len(),
                    }
                }
            }
        })
        .expect("thread persist")
}

fn join_persist(handle: JoinHandle<PersistResult>, stats: &Stats) {
    match handle.join() {
        Ok(r) => {
            stats.solved.fetch_add(r.ok as u64, Ordering::Relaxed);
            stats.failed.fetch_add(r.fail as u64, Ordering::Relaxed);
        }
        Err(_) => warn!("thread persist paniqué"),
    }
}

pub fn run_local_engine(
    db: &LocalDb,
    worker_id: &str,
    cfg: &LocalConfig,
    shutdown: Option<&AtomicBool>,
) -> Result<()> {
    // Le pool global rayon ne s'initialise qu'une fois par processus. Lors d'un redémarrage
    // via le dashboard (2e cycle+), il est déjà en place : on réutilise alors le pool existant
    // au lieu de planter (« global thread pool has already been initialized »).
    if let Err(e) = rayon::ThreadPoolBuilder::new()
        .num_threads(cfg.threads)
        .build_global()
    {
        tracing::debug!("pool rayon déjà initialisé (redémarrage) : {e}");
    }

    // Tablebase chaude en mémoire : socle des lookups 1 coup.
    let table = {
        let t0 = Instant::now();
        let t = ResultTable::load_from_db(db).unwrap_or_else(|e| {
            warn!("chargement ResultTable : {:#} (démarrage à vide)", e);
            ResultTable::new()
        });
        info!(
            "ResultTable chargée : {} positions en {:.1}s",
            t.len(),
            t0.elapsed().as_secs_f64()
        );
        Arc::new(t)
    };

    let known = db.known_hashes_full()?;
    let known_count = known.len();
    let mut explorer = ExplorerState::new(cfg.max_empty, known);
    explorer.skip_completed_levels(known_count);

    let seeds: Vec<Position> = db.load_seed_positions(SEED_LIMIT).unwrap_or_default();
    let seeds = Arc::new(seeds);
    info!("Graines rétrograde chargées : {}", seeds.len());
    if seeds.is_empty() {
        explorer.mode = crate::explorer::ExplorationMode::Forward;
        explorer.init_bfs();
        info!(
            "Peu de graines rétrograde — démarrage en BFS forward (conseil : lancer build_endgame_tablebase.py une fois)"
        );
    }

    let explorer = Arc::new(Mutex::new(explorer));
    let stats = Arc::new(Stats {
        solved: AtomicU64::new(0),
        failed: AtomicU64::new(0),
        explored: AtomicU64::new(0),
    });

    let shutdown_arc = Arc::new(AtomicBool::new(false));
    let explorer_shutdown = Arc::clone(&shutdown_arc);
    let explorer_handle = spawn_explorer_thread(
        db.clone(),
        Arc::clone(&explorer),
        Arc::clone(&seeds),
        Arc::clone(&stats),
        cfg.clone(),
        explorer_shutdown,
        known_count,
    );

    sync_explorer_progress(db, &explorer);

    let solved_start = db.count_solved().unwrap_or(0);
    let claim_batch = cfg.solve_batch.min(crate::local_db::MAX_CLAIM_BATCH);
    info!(
        "4mation-local turbo — threads={}, max_empty={}, solve_batch={}, min_pending={}, résolues={}",
        cfg.threads,
        cfg.max_empty,
        claim_batch,
        cfg.min_pending,
        solved_start
    );
    info!("Pipeline : exploration arrière-plan + résolution rayon + persistance SQLite parallèle");
    info!(
        "Explorateur throttle v2 — palier max_empty ≥ {:.0}s (mature {:.0}s)",
        LEVEL_DWELL_SEC, LEVEL_DWELL_MATURE_SEC
    );

    let mut last_stats = Instant::now();
    let mut last_stats_solved = 0u64;
    let mut persist: Option<JoinHandle<PersistResult>> = None;
    let worker_owned = worker_id.to_string();
    let mut idle_claims = 0u32;
    let mut loop_ticks = 0u32;

    loop {
        if shutdown.is_some_and(|s| s.load(Ordering::Relaxed)) {
            shutdown_arc.store(true, Ordering::Relaxed);
            info!("Arrêt demandé via dashboard — sortie");
            break;
        }

        if let Some(max) = cfg.max_iterations {
            if stats.solved.load(Ordering::Relaxed) >= max {
                shutdown_arc.store(true, Ordering::Relaxed);
                info!("Limite {} atteinte — arrêt", max);
                break;
            }
        }

        loop_ticks += 1;
        if loop_ticks % SYNC_LEVEL_EVERY == 0 {
            sync_explorer_progress(db, &explorer);
        }

        if let Some(h) = persist.take() {
            join_persist(h, &stats);
        }

        let positions = match db.claim(worker_id, claim_batch) {
            Ok(p) => p,
            Err(e) => {
                warn!("claim : {:#}", e);
                thread::sleep(Duration::from_millis(50));
                continue;
            }
        };

        if positions.is_empty() {
            if let Some(h) = persist.take() {
                join_persist(h, &stats);
            }
            idle_claims += 1;
            if idle_claims % RECLAIM_IDLE_EVERY == 0 {
                if let Ok(n) = db.reclaim_stale_in_progress(60) {
                    if n > 0 {
                        info!("{n} positions bloquées recyclées (file vide)");
                    }
                }
            }
            if cfg.once {
                shutdown_arc.store(true, Ordering::Relaxed);
                break;
            }
            thread::sleep(Duration::from_millis(EMPTY_QUEUE_SPIN_MS));
            continue;
        }

        idle_claims = 0;

        let board_max_empty = positions
            .iter()
            .map(|pos| empty_cells(&parse_board(&pos.board_json)))
            .max()
            .unwrap_or(cfg.max_empty);
        let batch_n = positions.len();
        let solve_started = Instant::now();
        info!(
            "Résolution lot de {} positions (max_empty cfg={}, max plateau={})",
            batch_n, cfg.max_empty, board_max_empty
        );

        // Profondeur par position dans solve_claimed : max(cfg, cases vides du plateau).
        // Ne pas prendre le max du lot — une position aberrante ne doit pas gonfler tout le batch.
        let (submits, releases, unsolvable) =
            solve_batch(&positions, cfg.max_empty, worker_id, &table);

        info!(
            "Lot terminé en {:.1}s — {} ok, {} à relâcher, {} hors limite",
            solve_started.elapsed().as_secs_f64(),
            submits.len(),
            releases.len(),
            unsolvable.len()
        );

        persist = Some(spawn_persist(
            db.clone(),
            worker_owned.clone(),
            submits,
            releases,
            unsolvable,
            Arc::clone(&table),
        ));

        if cfg.once {
            shutdown_arc.store(true, Ordering::Relaxed);
            break;
        }

        if last_stats.elapsed().as_secs_f64() >= STATS_INTERVAL_SEC {
            if let Some(h) = persist.take() {
                join_persist(h, &stats);
            }
            let total = db.count_solved().unwrap_or(0);
            let session = stats.solved.load(Ordering::Relaxed);
            let delta = session.saturating_sub(last_stats_solved);
            let elapsed = last_stats.elapsed().as_secs_f64().max(0.1);
            let rate = delta as f64 / elapsed;
            let in_prog = db.count_in_progress().unwrap_or(0);
            let db_go = db.db_size_bytes() as f64 / 1e9;
            info!(
                "Stats — session résolues={} ({:.0}/s), échecs={}, explorées={}, total DB={}, pending={}, in_progress={}, taille={:.2} Go",
                session,
                rate,
                stats.failed.load(Ordering::Relaxed),
                stats.explored.load(Ordering::Relaxed),
                total,
                db.count_pending().unwrap_or(0),
                in_prog,
                db_go
            );
            last_stats = Instant::now();
            last_stats_solved = session;
        }
    }

    shutdown_arc.store(true, Ordering::Relaxed);
    if let Some(h) = persist.take() {
        join_persist(h, &stats);
    }
    let _ = explorer_handle.join();

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
