//! Construction du livre d'ouverture — BFS + promotion exacte (oracle tablebase)
//! + estimations rapides (oracle partiel + heuristique) ou profondes (RetrogradeSolver).

use std::collections::HashSet;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use anyhow::Result;
use dashmap::DashMap;
use rayon::prelude::*;
use tracing::info;

use crate::dashboard::BuildControl;
use crate::game::{
    apply_move, board_to_value, check_winner, empty_cells, frontier_moves, Board, Move,
    BOARD_SIZE,
};
use crate::hasher::PositionHasher;
use crate::local_db::{LocalDb, OpeningBookRow};
use crate::result_table::ResultTable;
use crate::solver::{
    estimate_heuristic, estimate_via_partial_oracle, resolve_via_children, RetrogradeSolver,
    ChildOracle, ChildValue, SolvedPosition,
};

/// Cible par défaut : 2 Go de livre d'ouverture.
pub const DEFAULT_TARGET_BYTES: u64 = 2 * 1024 * 1024 * 1024;
const PAR_CHUNK: usize = 256;
const PROGRESS_INTERVAL: Duration = Duration::from_secs(10);
/// Profondeur max pour RetrogradeSolver en mode `deep` (au-delà : oracle partiel seulement).
const DEEP_ESTIMATE_MAX_EMPTY: usize = 22;

/// Stratégie d'estimation quand la promotion exacte échoue.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum OpeningEstimateMode {
    /// Oracle partiel + repli heuristique (~µs/position, défaut).
    #[default]
    Fast,
    /// RetrogradeSolver complet (lent, haute qualité).
    Deep,
    /// N'insère que les promotions exactes.
    ExactOnly,
}

#[derive(Clone, Debug)]
pub struct OpeningBookConfig {
    pub max_ply: i32,
    pub max_positions: usize,
    pub target_bytes: u64,
    pub threads: usize,
    pub refresh_estimates: bool,
    pub fresh: bool,
    pub estimate_mode: OpeningEstimateMode,
    /// Si vrai : tous les coups frontier à chaque ply (couverture complète de l'arbre).
    /// Si faux : largeur réduite après le premier coup (lignes principales seulement).
    pub full_breadth: bool,
    pub build_control: Option<BuildControl>,
}

impl Default for OpeningBookConfig {
    fn default() -> Self {
        Self {
            max_ply: 18,
            max_positions: 200_000,
            target_bytes: DEFAULT_TARGET_BYTES,
            threads: num_cpus(),
            refresh_estimates: false,
            fresh: false,
            estimate_mode: OpeningEstimateMode::Fast,
            full_breadth: true,
            build_control: None,
        }
    }
}

#[derive(Clone, Debug)]
struct CollectedPos {
    board: Board,
    player: i8,
    last_move: Option<Move>,
    ply: i32,
    hash: String,
}

/// Oracle dual : tablebase (`positions`) + livre exact déjà construit.
struct OpeningOracle {
    tablebase: Arc<ResultTable>,
    exact_book: Arc<DashMap<u64, u8>>,
}

impl OpeningOracle {
    fn lookup_packed(&self, board: &Board, player: i8, last_move: Option<Move>) -> Option<(char, u32)> {
        let key = ResultTable::key_for(board, player, last_move);
        if let Some(v) = self.exact_book.get(&key) {
            return Some(unpack_opening(*v));
        }
        self.tablebase.get(board, player, last_move)
    }

    fn is_exact_entry(&self, key: u64) -> bool {
        self.exact_book.contains_key(&key)
    }
}

impl ChildOracle for OpeningOracle {
    fn lookup(&self, board: &Board, player: i8, last_move: Option<Move>) -> Option<ChildValue> {
        self.lookup_packed(board, player, last_move)
            .map(|(result, depth)| ChildValue { result, depth })
    }
}

#[inline]
fn pack_opening(result: char, depth: u32) -> u8 {
    let code = match result {
        'W' => 2u8,
        'D' => 1,
        _ => 0,
    };
    ((depth.min(63) as u8) << 2) | code
}

#[inline]
fn unpack_opening(v: u8) -> (char, u32) {
    let result = match v & 0b11 {
        2 => 'W',
        1 => 'D',
        _ => 'L',
    };
    (result, (v >> 2) as u32)
}

fn branch_for_ply(ply: i32) -> usize {
    match ply {
        0 => 49,
        1..=2 => 12,
        3..=6 => 10,
        7..=10 => 8,
        _ => 6,
    }
}

fn order_moves(board: &Board, moves: &[Move], _player: i8, _last_move: Option<Move>) -> Vec<Move> {
    let mut ordered: Vec<Move> = moves.to_vec();
    ordered.sort_by_key(|&(r, c)| {
        let dr = (r as i32 - 3).abs();
        let dc = (c as i32 - 3).abs();
        dr.max(dc)
    });
    ordered
}

fn estimate_budget_mult(ply: i32) -> usize {
    match ply {
        0..=2 => 2,
        3..=6 => 2,
        _ => 1,
    }
}

fn moves_to_expand(ply: i32, moves: &[Move], full_breadth: bool) -> usize {
    if full_breadth {
        moves.len()
    } else {
        branch_for_ply(ply).min(moves.len())
    }
}

/// BFS niveau par niveau (ply 0, puis 1, puis 2…).
/// En mode `full_breadth`, tous les coups frontier sont explorés : seul `--opening-max-ply`
/// limite la profondeur. `--opening-max-positions` peut tronquer après un ply complet.
fn collect_positions(max_ply: i32, max_positions: usize, full_breadth: bool) -> Vec<CollectedPos> {
    let mut seen: HashSet<String> = HashSet::new();
    let mut out: Vec<CollectedPos> = Vec::new();
    let mut frontier: Vec<(Board, i8, Option<Move>, i32)> =
        vec![([[0i8; BOARD_SIZE]; BOARD_SIZE], 1, None, 0)];

    let mut last_completed_ply = 0i32;

    while !frontier.is_empty() {
        let ply_now = frontier[0].3;
        if ply_now > max_ply {
            break;
        }

        let mut next_frontier: Vec<(Board, i8, Option<Move>, i32)> = Vec::new();

        for (board, player, last_move, ply) in frontier {
            let hash = PositionHasher::hash_key(&board, player, last_move);
            if !seen.insert(hash.clone()) {
                continue;
            }
            out.push(CollectedPos {
                board,
                player,
                last_move,
                ply,
                hash,
            });

            if ply >= max_ply || check_winner(&board).is_some() {
                continue;
            }

            let moves = frontier_moves(&board, last_move, player);
            let ordered = order_moves(&board, &moves, player, last_move);
            let take = moves_to_expand(ply, &moves, full_breadth);
            for mv in ordered.into_iter().take(take) {
                let nb = apply_move(&board, mv, player);
                if check_winner(&nb).is_some() {
                    continue;
                }
                next_frontier.push((nb, 3 - player, Some(mv), ply + 1));
            }
        }

        last_completed_ply = ply_now;

        if out.len() >= max_positions {
            info!(
                "Collecte arrêtée après ply {} — {} positions (cap {}). \
                 Augmentez --opening-max-positions ou réduisez --opening-max-ply pour une couverture plus profonde.",
                last_completed_ply,
                out.len(),
                max_positions
            );
            break;
        }

        frontier = next_frontier;
    }

    if full_breadth {
        info!(
            "Couverture complète ply 0→{} : {} positions uniques",
            last_completed_ply,
            out.len()
        );
    }

    out
}

fn opening_book_bytes_estimate(db: &LocalDb, count: i64) -> u64 {
    (db.opening_book_table_bytes().unwrap_or(0).max(0) as u64)
        .max((count as u64).saturating_mul(420))
}

fn target_entries(target_bytes: u64, bytes_per_entry: u64) -> i64 {
    (target_bytes / bytes_per_entry.max(180)).max(1) as i64
}

pub fn run_opening_book_build(db: &LocalDb, cfg: OpeningBookConfig) -> Result<()> {
    rayon::ThreadPoolBuilder::new()
        .num_threads(cfg.threads.max(1))
        .build_global()
        .ok();

    info!(
        "Mode estimation : {:?} (fast = oracle partiel + heuristique, deep = RetrogradeSolver)",
        cfg.estimate_mode
    );

    if cfg.fresh {
        info!("Vidage opening_book (--opening-fresh)…");
        db.clear_opening_book()?;
    }

    info!("Chargement tablebase en mémoire…");
    let load_start = Instant::now();
    let tablebase = Arc::new(ResultTable::load_from_db(db)?);
    info!(
        "ResultTable : {} positions en {:.1}s",
        tablebase.len(),
        load_start.elapsed().as_secs_f64()
    );

    let exact_book: Arc<DashMap<u64, u8>> = Arc::new(DashMap::new());
    for (key, packed) in db.load_exact_opening_packed()? {
        exact_book.insert(key, packed);
    }
    info!("Livre exact en mémoire : {} entrées", exact_book.len());

    let skip_estimates: HashSet<u64> = if cfg.refresh_estimates {
        HashSet::new()
    } else {
        db.load_non_exact_opening_keys()?
    };

    let stop = Arc::new(AtomicBool::new(false));
    let session_exact = Arc::new(AtomicU64::new(0));
    let session_est = Arc::new(AtomicU64::new(0));
    let started_at = chrono_now_iso();

    db.set_opening_book_progress(0, 1, 0.0, true, Some(&started_at))?;

    if let Some(ref bc) = cfg.build_control {
        bc.set_active(true);
    }

    let hb_stop = Arc::new(AtomicBool::new(false));
    let hb_db = db.clone();
    let hb_target = cfg.target_bytes;
    let hb_started = started_at.clone();
    let hb_stop_flag = Arc::clone(&hb_stop);
    let hb_thread = std::thread::spawn(move || {
        while !hb_stop_flag.load(Ordering::Relaxed) {
            std::thread::sleep(PROGRESS_INTERVAL);
            if hb_stop_flag.load(Ordering::Relaxed) {
                break;
            }
            let _ = touch_opening_progress(&hb_db, hb_target, &hb_started);
        }
    });

    let waves: [(i32, usize, bool); 5] = [
        (14, 80_000, false),
        (16, 200_000, false),
        (18, 400_000, false),
        (18, 600_000, true),
        (20, 800_000, true),
    ];

    'waves: for (wave_idx, (max_ply, max_pos, refresh)) in waves.iter().enumerate() {
        if stop.load(Ordering::Relaxed) {
            break;
        }
        let wave_max_ply = (*max_ply).min(cfg.max_ply);
        let wave_max_pos = (*max_pos).min(cfg.max_positions);
        let do_refresh = *refresh || cfg.refresh_estimates;

        info!(
            "Vague {}/{} — ply≤{}, max={} positions, refresh={}",
            wave_idx + 1,
            waves.len(),
            wave_max_ply,
            wave_max_pos,
            do_refresh
        );

        let mut positions = collect_positions(wave_max_ply, wave_max_pos, cfg.full_breadth);
        positions.sort_by(|a, b| b.ply.cmp(&a.ply));

        info!("{} positions collectées (ply≤{})", positions.len(), wave_max_ply);

        let max_ply_in_wave = positions.iter().map(|p| p.ply).max().unwrap_or(0);

        for ply_level in (0..=max_ply_in_wave).rev() {
            if stop.load(Ordering::Relaxed) {
                break 'waves;
            }

            let bucket: Vec<CollectedPos> = positions
                .iter()
                .filter(|p| p.ply == ply_level)
                .cloned()
                .collect();

            if bucket.is_empty() {
                continue;
            }

            info!(
                "Ply {} — {} positions (vague {})",
                ply_level,
                bucket.len(),
                wave_idx + 1
            );

            let oracle = OpeningOracle {
                tablebase: Arc::clone(&tablebase),
                exact_book: Arc::clone(&exact_book),
            };

            for chunk in bucket.chunks(PAR_CHUNK) {
                if stop.load(Ordering::Relaxed) {
                    break;
                }

                let results: Vec<Option<OpeningBookRow>> = chunk
                    .par_iter()
                    .map(|pos| {
                        process_opening_position(
                            pos,
                            &oracle,
                            do_refresh,
                            &skip_estimates,
                            cfg.estimate_mode,
                            &session_exact,
                            &session_est,
                        )
                    })
                    .collect();

                let mut batch_rows: Vec<OpeningBookRow> = Vec::new();
                for row in results.into_iter().flatten() {
                    if row.exact == 1 {
                        if let Ok(key) = u64::from_str_radix(&row.hash, 16) {
                            exact_book.insert(key, pack_opening(row.result, 1));
                        }
                    }
                    batch_rows.push(row);
                }

                if !batch_rows.is_empty() {
                    db.bulk_insert_opening_book(&batch_rows)?;
                    touch_opening_progress(db, cfg.target_bytes, &started_at)?;
                }

                if check_target_reached(db, cfg.target_bytes)? {
                    stop.store(true, Ordering::Relaxed);
                    break 'waves;
                }
            }
        }
    }

    hb_stop.store(true, Ordering::Relaxed);
    let _ = hb_thread.join();

    if let Some(ref bc) = cfg.build_control {
        bc.set_active(false);
    }

    let count = db.count_opening_book()?;
    let exact = db.count_opening_exact()?;
    db.set_opening_book_progress(
        count,
        target_entries(cfg.target_bytes, 420),
        (100.0 * opening_book_bytes_estimate(db, count) as f64 / cfg.target_bytes as f64).min(100.0),
        false,
        Some(&started_at),
    )?;

    info!(
        "Livre d'ouverture terminé : {} entrées (exact={}), session exact={} estimé={}",
        count,
        exact,
        session_exact.load(Ordering::Relaxed),
        session_est.load(Ordering::Relaxed),
    );
    Ok(())
}

fn process_opening_position(
    pos: &CollectedPos,
    oracle: &OpeningOracle,
    do_refresh: bool,
    skip_estimates: &HashSet<u64>,
    estimate_mode: OpeningEstimateMode,
    session_exact: &AtomicU64,
    session_est: &AtomicU64,
) -> Option<OpeningBookRow> {
    let key = ResultTable::key_for(&pos.board, pos.player, pos.last_move);

    if let Some(solved) = resolve_via_children(&pos.board, pos.player, pos.last_move, oracle) {
        session_exact.fetch_add(1, Ordering::Relaxed);
        return Some(row_from_solved(pos, solved, 1));
    }

    // Ne jamais remplacer une entrée exact=1 par une estimation (INSERT OR REPLACE).
    if oracle.is_exact_entry(key) {
        return None;
    }

    if !do_refresh && skip_estimates.contains(&key) {
        return None;
    }

    if estimate_mode == OpeningEstimateMode::ExactOnly {
        return None;
    }

    let solved = match estimate_mode {
        OpeningEstimateMode::Fast => estimate_via_partial_oracle(
            &pos.board,
            pos.player,
            pos.last_move,
            oracle as &dyn ChildOracle,
        )
        .or_else(|| {
            Some(estimate_heuristic(
                &pos.board,
                pos.player,
                pos.last_move,
            ))
        }),
        OpeningEstimateMode::Deep => {
            let empty = empty_cells(&pos.board);
            if empty <= DEEP_ESTIMATE_MAX_EMPTY {
                let mult = estimate_budget_mult(pos.ply);
                let cap = empty.min(DEEP_ESTIMATE_MAX_EMPTY);
                let mut solver = RetrogradeSolver::for_board_scaled(cap, empty, mult);
                if let Some(s) = solver.solve_with_oracle(
                    &pos.board,
                    pos.player,
                    pos.last_move,
                    Some(oracle as &dyn ChildOracle),
                ) {
                    Some(s)
                } else {
                    estimate_via_partial_oracle(
                        &pos.board,
                        pos.player,
                        pos.last_move,
                        oracle as &dyn ChildOracle,
                    )
                    .or_else(|| {
                        Some(estimate_heuristic(
                            &pos.board,
                            pos.player,
                            pos.last_move,
                        ))
                    })
                }
            } else {
                estimate_via_partial_oracle(
                    &pos.board,
                    pos.player,
                    pos.last_move,
                    oracle as &dyn ChildOracle,
                )
                .or_else(|| {
                    Some(estimate_heuristic(
                        &pos.board,
                        pos.player,
                        pos.last_move,
                    ))
                })
            }
        }
        OpeningEstimateMode::ExactOnly => return None,
    }?;

    session_est.fetch_add(1, Ordering::Relaxed);
    Some(row_from_solved(pos, solved, 0))
}

fn row_from_solved(pos: &CollectedPos, solved: SolvedPosition, exact: i32) -> OpeningBookRow {
    OpeningBookRow {
        hash: pos.hash.clone(),
        result: solved.result,
        win_rate: solved.win_rate,
        best_move: solved.best_move,
        ply: pos.ply,
        exact,
        board_json: serde_json::to_string(&board_to_value(&pos.board))
            .unwrap_or_else(|_| "null".to_string()),
        current_player: pos.player,
        last_move: pos.last_move,
    }
}

fn touch_opening_progress(db: &LocalDb, target_bytes: u64, started_at: &str) -> Result<()> {
    let count = db.count_opening_book()?;
    let fill_bytes = opening_book_bytes_estimate(db, count);
    let bpe = if count > 0 {
        (fill_bytes / count as u64).max(180)
    } else {
        420
    };
    let pct = (100.0 * fill_bytes as f64 / target_bytes as f64).min(100.0);
    db.set_opening_book_progress(
        count,
        target_entries(target_bytes, bpe),
        pct,
        true,
        Some(started_at),
    )
}

fn check_target_reached(db: &LocalDb, target_bytes: u64) -> Result<bool> {
    let count = db.count_opening_book()?;
    Ok(opening_book_bytes_estimate(db, count) >= target_bytes)
}

fn chrono_now_iso() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    format!("{secs}")
}

fn num_cpus() -> usize {
    std::thread::available_parallelism()
        .map(|n| n.get())
        .unwrap_or(4)
}
