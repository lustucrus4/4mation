//! Solveur 4mation 100 % local — exploration, résolution parallèle, SQLite.

//!

//! Remplace le trio filler VPS + API + workers HTTP sur une machine multi-cœurs.



mod dashboard;

mod explorer;

mod game;

mod hasher;

mod local_db;

mod local_engine;

mod result_table;

mod solver;

mod symmetry;

mod work;



use anyhow::Result;

use clap::Parser;

use std::path::PathBuf;

use std::sync::atomic::Ordering;

use tracing::info;

use tracing_subscriber::EnvFilter;



use dashboard::{default_dashboard_config, spawn_dashboard_thread, EngineControl};

use hasher::PositionHasher;

use local_db::LocalDb;

use local_engine::{run_local_engine, LocalConfig};



const DEFAULT_DB: &str = "script/solver/data/tablebase.db";



#[derive(Parser, Debug)]

#[command(

    name = "4mation-local",

    about = "Solveur 4mation local (exploration + résolution + SQLite, sans réseau)"

)]

struct Args {

    /// Chemin vers tablebase.db

    #[arg(long, default_value = DEFAULT_DB)]

    db: PathBuf,



    /// Threads rayon (résolution parallèle)

    #[arg(long, env = "SOLVER_THREADS", default_value = "16")]

    threads: usize,



    /// Cases vides max pour résolution rétrograde (niveau initial d'exploration)

    #[arg(long, env = "TABLEBASE_MAX_EMPTY", default_value = "12")]

    max_empty: usize,



    /// Positions par lot de résolution (gros lots = CPU saturé)

    #[arg(long, default_value = "2000")]

    solve_batch: usize,



    /// Tampon minimal en file avant ralentissement exploration

    #[arg(long, env = "SOLVER_MIN_PENDING", default_value = "500")]

    min_pending: usize,



    /// Limite de positions résolues puis arrêt (tests)

    #[arg(long)]

    max_iterations: Option<u64>,



    /// Un seul cycle explore+résolution puis sortie

    #[arg(long)]

    once: bool,



    /// Démarre le dashboard web intégré (http://127.0.0.1:8765/)

    #[arg(long)]

    dashboard: bool,



    /// Port du dashboard intégré

    #[arg(long, env = "SOLVER_DASHBOARD_PORT", default_value = "8765")]

    dashboard_port: u16,



    /// Interface d'écoute du dashboard

    #[arg(long, env = "SOLVER_DASHBOARD_HOST", default_value = "127.0.0.1")]

    dashboard_host: String,



    /// Désactive la canonicalisation par symétries (miroir/rotation) — compat ancienne base

    #[arg(long)]

    no_symmetry: bool,



    /// Test de non-régression : re-résout N positions connues et compare result + best_move

    #[arg(long)]

    self_check: Option<usize>,



    /// Compaction one-shot : board_json → board_blob, purge doublons work_queue, VACUUM

    #[arg(long)]

    compact: bool,

}



/// Re-résout un échantillon de positions déjà en base et compare result + best_move.

fn run_self_check(db: &LocalDb, sample: usize) -> Result<()> {

    use game::{parse_board, Move};

    use result_table::ResultTable;

    use solver::{resolve_via_children, RetrogradeSolver};



    let max_empty = 16usize;

    info!("Non-régression : chargement ResultTable…");

    let table = ResultTable::load_from_db(db)?;

    info!("ResultTable : {} positions", table.len());



    let rows = db.fetch_solved_sample(max_empty, sample)?;

    info!("Échantillon : {} positions (≤{} cases vides)", rows.len(), max_empty);



    let mut checked = 0usize;

    let mut result_mismatch = 0usize;

    let mut best_mismatch = 0usize;

    let mut unresolved = 0usize;

    let mut via_oracle = 0usize;

    let mut via_search = 0usize;



    for (board_json, player, lmr, lmc, exp_result, exp_br, exp_bc) in &rows {

        let board = parse_board(&serde_json::from_str(board_json).unwrap_or(serde_json::Value::Null));

        let p = *player as i8;

        let last_move: Option<Move> = lmr

            .filter(|&r| r >= 0)

            .map(|r| (r as usize, lmc.unwrap_or(-1).max(0) as usize));



        let solved = match resolve_via_children(&board, p, last_move, &table) {

            Some(s) => {

                via_oracle += 1;

                s

            }

            None => {

                via_search += 1;

                let empty = board.iter().flatten().filter(|&&c| c == 0).count();

                let mut solver = RetrogradeSolver::for_board_scaled(max_empty, empty, 4);

                match solver.solve_with_oracle(&board, p, last_move, None) {

                    Some(s) => s,

                    None => {

                        unresolved += 1;

                        continue;

                    }

                }

            }

        };

        checked += 1;



        let exp_result_char = exp_result.chars().next().unwrap_or('?');

        if solved.result != exp_result_char {

            result_mismatch += 1;

            if result_mismatch <= 10 {

                tracing::warn!(

                    "result diff : attendu {} obtenu {} (last_move={:?})",

                    exp_result_char,

                    solved.result,

                    last_move

                );

            }

        }



        let exp_best: Option<Move> = exp_br

            .filter(|&r| r >= 0)

            .map(|r| (r as usize, exp_bc.unwrap_or(-1).max(0) as usize));

        if solved.best_move != exp_best {

            best_mismatch += 1;

            if best_mismatch <= 10 {

                tracing::warn!(

                    "best_move diff : attendu {:?} obtenu {:?} (result {})",

                    exp_best,

                    solved.best_move,

                    solved.result

                );

            }

        }

    }



    let denom = checked.max(1);

    info!("===== Non-régression =====");

    info!("Vérifiées            : {checked}");

    info!("  via lookup 1 coup  : {via_oracle}");

    info!("  via recherche      : {via_search}");

    info!("Non résolues (skip)  : {unresolved}");

    info!(

        "Écarts résultat      : {result_mismatch} ({:.4}%)",

        100.0 * result_mismatch as f64 / denom as f64

    );

    info!(

        "Écarts meilleur coup : {best_mismatch} ({:.4}%)",

        100.0 * best_mismatch as f64 / denom as f64

    );

    if result_mismatch == 0 && best_mismatch == 0 {

        info!("RÉSULTAT : 100% concordance ✓");

    } else {

        info!("RÉSULTAT : écarts détectés ✗");

    }

    Ok(())

}



fn run_engine_cycle(

    db: &LocalDb,

    worker_id: &str,

    cfg: &LocalConfig,

    engine_control: &EngineControl,

) -> Result<()> {

    engine_control.shutdown.store(false, Ordering::Relaxed);

    engine_control.set_running(true);



    match db.reclaim_stale_in_progress(120) {
        Ok(n) if n > 0 => info!("{n} positions in_progress recyclées en pending"),
        Ok(_) => {}
        Err(e) => tracing::warn!("recyclage in_progress : {:#}", e),
    }

    let pending = db.count_pending().unwrap_or(0);
    if pending < 100 {
        match db.requeue_failed() {
            Ok(n) if n > 0 => {
                info!("{n} positions failed remises en pending (nouvelle tentative)")
            }
            Ok(_) => {}
            Err(e) => tracing::warn!("requeue failed : {:#}", e),
        }
    }

    let result = run_local_engine(db, worker_id, cfg, Some(&engine_control.shutdown));



    engine_control.set_running(false);

    result

}



fn main() -> Result<()> {

    tracing_subscriber::fmt()

        .with_env_filter(EnvFilter::from_default_env().add_directive(tracing::Level::INFO.into()))

        .init();



    let args = Args::parse();



    PositionHasher::set_symmetry_enabled(!args.no_symmetry);

    if args.no_symmetry {

        info!("Symétries désactivées — hash legacy (sans canonicalisation)");

    } else {

        info!("Symétries activées — forme canonique D₄ (4 rotations × miroir)");

    }



    let hostname = hostname::get()

        .map(|h| h.to_string_lossy().into_owned())

        .unwrap_or_else(|_| "legion".into());

    let worker_id = format!("{}-local-{}", hostname, std::process::id());



    info!("Démarrage 4mation-local — worker_id={}", worker_id);



    let db = LocalDb::open(&args.db)?;



    if let Some(n) = args.self_check {

        return run_self_check(&db, n);

    }



    if args.compact {

        let before = db.db_size_bytes() as f64 / 1e9;

        info!("Compaction démarrée (taille actuelle {:.2} Go)…", before);

        db.compact()?;

        let after = db.db_size_bytes() as f64 / 1e9;

        info!("Compaction OK : {:.2} Go → {:.2} Go", before, after);

        return Ok(());

    }



    let engine_control = EngineControl::new();



    if args.dashboard {

        let dash_cfg = default_dashboard_config(

            args.db.clone(),

            args.dashboard_host.clone(),

            args.dashboard_port,

            true,

            Some(engine_control.clone()),

        );

        let url = format!(

            "http://{}:{}/",

            args.dashboard_host, args.dashboard_port

        );

        println!("Dashboard : {url}");

        spawn_dashboard_thread(dash_cfg)?;

        std::thread::sleep(std::time::Duration::from_millis(300));

    }



    let cfg = LocalConfig {

        threads: args.threads,

        max_empty: args.max_empty,

        solve_batch: args.solve_batch,

        min_pending: args.min_pending,

        max_iterations: args.max_iterations,

        once: args.once,

    };



    if args.dashboard && !args.once {

        loop {

            run_engine_cycle(&db, &worker_id, &cfg, &engine_control)?;

            info!("Solveur en pause — bouton « Démarrer » sur le dashboard pour reprendre");

            engine_control.wait_restart();

            info!("Redémarrage solveur via dashboard");

        }

    } else {

        run_engine_cycle(&db, &worker_id, &cfg, &engine_control)?;

    }



    Ok(())

}


