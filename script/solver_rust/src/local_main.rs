//! Solveur 4mation 100 % local — exploration, résolution parallèle, SQLite.

//!

//! Remplace le trio filler VPS + API + workers HTTP sur une machine multi-cœurs.



mod dashboard;

mod explorer;

mod game;

mod ghost_audit;

mod hasher;

mod local_db;

mod local_engine;

mod layer_sweep;

mod opening_book;

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



use dashboard::{default_dashboard_config, spawn_dashboard_thread, BuildControl, EngineControl};

use hasher::PositionHasher;

use local_db::LocalDb;

use local_engine::{run_local_engine, LocalConfig};

use result_table::ResultTable;

use opening_book::{run_opening_book_build, OpeningBookConfig, OpeningEstimateMode};



const DEFAULT_DB: &str = "script/solver/data/tablebase.db";



#[derive(Parser, Debug)]

#[command(

    name = "4mation-local",

    about = "Solveur 4mation local (exploration + résolution + SQLite, sans réseau)"

)]

struct Args {

    /// Balayage exhaustif : complète la couche N à partir de la couche N-1

    #[arg(long)]

    sweep_from: Option<usize>,

    /// Dernière couche à compléter (incluse)

    #[arg(long, default_value = "8")]

    sweep_to: usize,

    /// Réparation : réécrit les valeurs stockées incohérentes avec les enfants, au lieu
    /// de sauter les positions déjà connues (`--sweep-from` requis ; lancer du bas vers le
    /// haut pour propager les corrections)

    #[arg(long)]

    repair: bool,

    /// Chemin vers tablebase.db

    #[arg(long, default_value = DEFAULT_DB)]

    db: PathBuf,

    /// Diagnostic : affiche jusqu'à 5 parents irrésolubles de la couche N+1

    #[arg(long)]

    diag_layer: Option<usize>,

    /// Vérifie la base : recalcule chaque valeur depuis ses enfants et la compare

    #[arg(long)]

    verify: bool,

    /// Audit des lignes fantômes en lecture seule (DRY-RUN : aucune suppression)

    #[arg(long)]

    audit_ghosts: bool,

    /// Supprime réellement les lignes fantômes (transaction par lot). À réserver à une copie.

    #[arg(long)]

    purge_ghosts: bool,

    /// Limite de lignes parcourues par l'audit (0 = toute la table)

    #[arg(long, default_value = "0")]

    ghost_limit: u64,

    /// Nombre de lignes fantômes affichées en échantillon

    #[arg(long, default_value = "5")]

    ghost_sample: usize,

    /// Hashes par transaction de suppression (max 900)

    #[arg(long, default_value = "500")]

    ghost_batch: usize,



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



    /// Construit le livre d'ouverture (Rust, parallèle) au lieu du solveur endgame

    #[arg(long)]

    opening_book: bool,



    /// Ply max pour le BFS d'ouverture

    #[arg(long, default_value = "18")]

    opening_max_ply: i32,



    /// Nombre max de positions par vague

    #[arg(long, default_value = "200000")]

    opening_max_positions: usize,



    /// Cible de taille du livre en Go

    #[arg(long, default_value = "2")]

    opening_target_gb: f64,



    /// Vide opening_book avant reconstruction

    #[arg(long)]

    opening_fresh: bool,



    /// Recalcule les estimations existantes (sinon promotions exactes seulement)

    #[arg(long)]

    opening_refresh_estimates: bool,



    /// Estimation : `fast` (oracle partiel + heuristique), `deep` (RetrogradeSolver), `exact-only`

    #[arg(long, default_value = "fast")]

    opening_estimate: String,



    /// Largeur réduite (lignes principales) au lieu de tous les coups frontier

    #[arg(long)]

    opening_selective_breadth: bool,

}



/// Re-résout un échantillon de positions déjà en base et compare result + best_move.

fn run_self_check(db: &LocalDb, sample: usize) -> Result<()> {

    use game::{apply_move, is_winning_move, parse_board, Move};

    use result_table::ResultTable;

    use solver::{resolve_via_children, ChildOracle, RetrogradeSolver, RESULT_DRAW, RESULT_LOSS, RESULT_WIN};



    let max_empty = 16usize;

    info!("Non-régression : chargement ResultTable…");

    let table = ResultTable::load_from_db(db)?;

    info!("ResultTable : {} positions", table.len());



    let rows = db.fetch_solved_sample(max_empty, sample)?;

    info!("Échantillon : {} positions (≤{} cases vides)", rows.len(), max_empty);



    let mut checked = 0usize;

    let mut result_mismatch = 0usize;

    let mut best_mismatch = 0usize;

    let mut best_alt = 0usize;

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

            // Un « meilleur coup » différent n'est un vrai écart que si le coup
            // renvoyé n'atteint pas le résultat optimal de la position.
            let returned_is_optimal = match solved.best_move {

                None => solved.result == RESULT_LOSS,

                Some(mv) => {

                    if is_winning_move(&board, mv, p) {

                        solved.result == RESULT_WIN

                    } else {

                        let nb = apply_move(&board, mv, p);

                        match table.lookup(&nb, 3 - p, Some(mv)) {

                            Some(cv) => {

                                let my_result = match cv.result {

                                    RESULT_WIN => RESULT_LOSS,

                                    RESULT_LOSS => RESULT_WIN,

                                    _ => RESULT_DRAW,

                                };

                                my_result == solved.result

                            }

                            None => true,

                        }

                    }

                }

            };

            if returned_is_optimal {

                best_alt += 1;

            } else {

                best_mismatch += 1;

                if best_mismatch <= 10 {

                    tracing::warn!(

                        "best_move NON optimal : attendu {:?} obtenu {:?} (result {})",

                        exp_best,

                        solved.best_move,

                        solved.result

                    );

                }

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

        "Écarts meilleur coup : {best_mismatch} ({:.4}%)  [dont {best_alt} coups alternatifs optimaux]",

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



    // Audit/purge des lignes fantômes — avant toute ouverture en écriture, pour que
    // le dry-run se contente d'une connexion en lecture seule.
    if args.audit_ghosts || args.purge_ghosts {

        let cfg = ghost_audit::GhostAuditConfig {

            purge: args.purge_ghosts,

            limit: args.ghost_limit,

            sample: args.ghost_sample,

            batch_delete: args.ghost_batch,

        };

        ghost_audit::run_and_report(&args.db, &cfg)?;

        return Ok(());

    }



    let db = LocalDb::open(&args.db)?;



    // Vérification : la valeur stockée de chaque position est-elle cohérente ?
    if args.verify {

        // `--sweep-from M --sweep-to N` restreint la vérification à ces couches, ce qui
        // permet de re-contrôler une couche réparée sans repayer les 30 M de lignes.
        let layers = match args.sweep_from {

            Some(from) => from..=args.sweep_to,

            None => 1..=12,

        };

        return layer_sweep::verify(&db, layers, 3000);

    }

    // Diagnostic : pourquoi des parents restent-ils irrésolubles ?
    if let Some(layer) = args.diag_layer {

        return layer_sweep::diagnose(&db, layer, 5);

    }

    // Mode balayage : comble les couches trouées puis s'arrête.
    if let Some(from) = args.sweep_from {

        let table = ResultTable::load_from_db(&db)?;

        info!("Table de résultats chargée : {} positions", table.len());

        for layer in from..args.sweep_to {

            let stats = layer_sweep::sweep_layer(&db, layer, &table, args.repair)?;

            info!(

                "Couche {} complétée : {} positions en {:.0}s ({:.0}/s), {} connues, {} réparées, {} inconnues",

                layer + 1,

                stats.inserted,

                stats.elapsed_secs,

                stats.rate(),

                stats.known,

                stats.repaired,

                stats.incomplete

            );

            if stats.incomplete > 0 {

                tracing::warn!(

                    "{} positions ignorées : la couche {} est trouée, relancer d'abord le balayage de la couche {}",

                    stats.incomplete,

                    layer,

                    layer.saturating_sub(1)

                );

            }

        }

        return Ok(());

    }

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



    if args.opening_book {

        let build_control = BuildControl::new();
        build_control.set_active(true);

        if args.dashboard {

            let dash_cfg = default_dashboard_config(

                args.db.clone(),

                args.dashboard_host.clone(),

                args.dashboard_port,

                true,

                None,

                Some(build_control.clone()),

            );

            let url = format!(

                "http://{}:{}/",

                args.dashboard_host, args.dashboard_port

            );

            println!("Dashboard : {url}");

            spawn_dashboard_thread(dash_cfg)?;

            std::thread::sleep(std::time::Duration::from_millis(300));

        }

        let target_bytes = (args.opening_target_gb * 1024.0 * 1024.0 * 1024.0) as u64;

        let estimate_mode = match args.opening_estimate.as_str() {
            "deep" => OpeningEstimateMode::Deep,
            "exact-only" | "exact" | "none" => OpeningEstimateMode::ExactOnly,
            _ => OpeningEstimateMode::Fast,
        };

        info!(

            "Mode livre d'ouverture Rust — ply≤{}, max={} positions, cible {:.1} Go, {} threads, estimate={}, breadth={}",

            args.opening_max_ply,

            args.opening_max_positions,

            args.opening_target_gb,

            args.threads,

            args.opening_estimate,

            if args.opening_selective_breadth {
                "selective"
            } else {
                "full"
            }

        );

        let result = run_opening_book_build(

            &db,

            OpeningBookConfig {

                max_ply: args.opening_max_ply,

                max_positions: args.opening_max_positions,

                target_bytes,

                threads: args.threads,

                refresh_estimates: args.opening_refresh_estimates,

                fresh: args.opening_fresh,

                estimate_mode,

                full_breadth: !args.opening_selective_breadth,

                build_control: Some(build_control.clone()),

            },

        );

        build_control.set_active(false);

        return result;

    }



    let engine_control = EngineControl::new();



    if args.dashboard {

        let dash_cfg = default_dashboard_config(

            args.db.clone(),

            args.dashboard_host.clone(),

            args.dashboard_port,

            true,

            Some(engine_control.clone()),

            None,

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


