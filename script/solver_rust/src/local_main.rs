//! Solveur 4mation 100 % local — exploration, résolution parallèle, SQLite.
//!
//! Remplace le trio filler VPS + API + workers HTTP sur une machine multi-cœurs.

mod dashboard;
mod explorer;
mod game;
mod hasher;
mod local_db;
mod local_engine;
mod solver;
mod work;

use anyhow::Result;
use clap::Parser;
use std::path::PathBuf;
use std::sync::atomic::AtomicBool;
use std::sync::Arc;
use tracing::info;
use tracing_subscriber::EnvFilter;

use dashboard::{default_dashboard_config, spawn_dashboard_thread};
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

    /// Positions par lot de résolution
    #[arg(long, default_value = "500")]
    solve_batch: usize,

    /// Tampon minimal en file avant pause exploration
    #[arg(long, default_value = "5000")]
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
}

fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::from_default_env().add_directive(tracing::Level::INFO.into()))
        .init();

    let args = Args::parse();

    let hostname = hostname::get()
        .map(|h| h.to_string_lossy().into_owned())
        .unwrap_or_else(|_| "legion".into());
    let worker_id = format!("{}-local-{}", hostname, std::process::id());

    info!("Démarrage 4mation-local — worker_id={}", worker_id);

    let db = LocalDb::open(&args.db)?;

    let shutdown = Arc::new(AtomicBool::new(false));

    if args.dashboard {
        let dash_cfg = default_dashboard_config(
            args.db.clone(),
            args.dashboard_host.clone(),
            args.dashboard_port,
            true,
            Some(Arc::clone(&shutdown)),
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

    run_local_engine(&db, &worker_id, &cfg, Some(&shutdown))
}
