//! Worker solveur 4mation — haute performance (Rust + rayon + HTTP persistant).

mod api_client;
mod game;
mod local_db;
mod solver;

use anyhow::{Context, Result};
use clap::Parser;
use rayon::prelude::*;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tracing::{info, warn};
use tracing_subscriber::EnvFilter;

use api_client::{solve_claimed, ApiClient, ClaimedPosition, SubmitPayload};
use local_db::LocalDb;

const DEFAULT_API: &str = "https://api-4mation.lab211.fr";
const IDLE_SLEEP_SEC: f64 = 5.0;
const STATS_INTERVAL_SEC: f64 = 30.0;

#[derive(Parser, Debug)]
#[command(name = "4mation-worker", about = "Worker solveur 4mation haute performance")]
struct Args {
    /// URL de l'API solveur
    #[arg(long, env = "SOLVER_API_URL", default_value = DEFAULT_API)]
    api_url: String,

    /// Token worker (header X-Solver-Worker-Token)
    #[arg(long, env = "SOLVER_WORKER_TOKEN", default_value = "")]
    token: String,

    /// Nombre de threads rayon pour la résolution parallèle
    #[arg(long, env = "SOLVER_THREADS", default_value = "16")]
    threads: usize,

    /// Positions par claim HTTP (max serveur : 50)
    #[arg(long, env = "SOLVER_CLAIM_BATCH", default_value = "25")]
    claim_batch: usize,

    /// Cases vides max pour résolution rétrograde
    #[arg(long, env = "TABLEBASE_MAX_EMPTY", default_value = "49")]
    max_empty: usize,

    /// Mode local : chemin vers tablebase.db (pas d'appels HTTP claim/submit)
    #[arg(long)]
    local_db: Option<PathBuf>,

    /// Limite de positions résolues puis arrêt (tests)
    #[arg(long)]
    max_iterations: Option<u64>,
}

struct Stats {
    solved: AtomicU64,
    failed: AtomicU64,
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::from_default_env().add_directive(tracing::Level::INFO.into()))
        .init();

    let args = Args::parse();
    rayon::ThreadPoolBuilder::new()
        .num_threads(args.threads)
        .build_global()
        .context("initialisation pool rayon")?;

    let hostname = hostname::get()
        .map(|h| h.to_string_lossy().into_owned())
        .unwrap_or_else(|_| "host".into());
    let worker_id = format!("{}-rust-{}", hostname, std::process::id());

    info!(
        "Démarrage 4mation-worker — threads={}, batch={}, max_empty={}, mode={}",
        args.threads,
        args.claim_batch,
        args.max_empty,
        if args.local_db.is_some() {
            "local-db"
        } else {
            "api"
        }
    );

    let stats = Arc::new(Stats {
        solved: AtomicU64::new(0),
        failed: AtomicU64::new(0),
    });

    if let Some(ref db_path) = args.local_db {
        run_local_loop(&args, &worker_id, db_path, stats).await?;
    } else {
        run_api_loop(&args, &worker_id, stats).await?;
    }

    Ok(())
}

async fn run_api_loop(args: &Args, worker_id: &str, stats: Arc<Stats>) -> Result<()> {
    let token = if args.token.is_empty() {
        None
    } else {
        Some(args.token.clone())
    };
    let client = ApiClient::new(&args.api_url, token)?;
    let mut last_stats = Instant::now();

    loop {
        if let Some(max) = args.max_iterations {
            if stats.solved.load(Ordering::Relaxed) >= max {
                info!("Limite {} atteinte — arrêt", max);
                break;
            }
        }

        match process_batch_api(&client, worker_id, args, &stats).await {
            Ok(true) => {}
            Ok(false) => {
                info!("File vide — pause {:.0}s", IDLE_SLEEP_SEC);
                tokio::time::sleep(Duration::from_secs_f64(IDLE_SLEEP_SEC)).await;
            }
            Err(e) => {
                warn!("Erreur boucle API : {:#}", e);
                tokio::time::sleep(Duration::from_secs_f64(IDLE_SLEEP_SEC)).await;
            }
        }

        if last_stats.elapsed().as_secs_f64() >= STATS_INTERVAL_SEC {
            info!(
                "Stats — résolues={}, échecs={}",
                stats.solved.load(Ordering::Relaxed),
                stats.failed.load(Ordering::Relaxed)
            );
            last_stats = Instant::now();
        }
    }
    Ok(())
}

async fn run_local_loop(
    args: &Args,
    worker_id: &str,
    db_path: &PathBuf,
    stats: Arc<Stats>,
) -> Result<()> {
    let db = LocalDb::open(db_path)?;
    let mut last_stats = Instant::now();

    loop {
        if let Some(max) = args.max_iterations {
            if stats.solved.load(Ordering::Relaxed) >= max {
                break;
            }
        }

        let positions = match db.claim(worker_id, args.claim_batch) {
            Ok(p) => p,
            Err(e) => {
                warn!("claim local : {:#}", e);
                tokio::time::sleep(Duration::from_secs_f64(IDLE_SLEEP_SEC)).await;
                continue;
            }
        };

        if positions.is_empty() {
            tokio::time::sleep(Duration::from_secs_f64(IDLE_SLEEP_SEC)).await;
            continue;
        }

        let (submits, releases) = solve_batch(&positions, args.max_empty, worker_id);
        for hash in releases {
            let _ = db.release(worker_id, &hash);
        }
        match db.submit_batch(&submits) {
            Ok((ok, fail)) => {
                stats.solved.fetch_add(ok as u64, Ordering::Relaxed);
                stats.failed.fetch_add(fail as u64, Ordering::Relaxed);
                info!("Batch local — {} ok, {} échecs", ok, fail);
            }
            Err(e) => warn!("submit local : {:#}", e),
        }

        if last_stats.elapsed().as_secs_f64() >= STATS_INTERVAL_SEC {
            info!(
                "Stats — résolues={}, échecs={}",
                stats.solved.load(Ordering::Relaxed),
                stats.failed.load(Ordering::Relaxed)
            );
            last_stats = Instant::now();
        }
    }
    Ok(())
}

/// Retourne Ok(true) si du travail a été fait, Ok(false) si file vide.
async fn process_batch_api(
    client: &ApiClient,
    worker_id: &str,
    args: &Args,
    stats: &Arc<Stats>,
) -> Result<bool> {
    let positions = client.claim(worker_id, args.claim_batch).await?;
    if positions.is_empty() {
        return Ok(false);
    }

    let (mut submits, releases) = solve_batch(&positions, args.max_empty, worker_id);

    for hash in releases {
        if let Err(e) = client.release(worker_id, &hash).await {
            warn!("release {} : {:#}", &hash[..10.min(hash.len())], e);
        }
    }

    for s in &mut submits {
        s.worker_id = worker_id.to_string();
    }

    let (ok, fail) = client.submit_batch(worker_id, submits).await?;
    stats.solved.fetch_add(ok as u64, Ordering::Relaxed);
    stats.failed.fetch_add(fail as u64, Ordering::Relaxed);
    info!("Batch API — {} soumis, {} échecs", ok, fail);
    Ok(true)
}

fn solve_batch(
    positions: &[ClaimedPosition],
    max_empty: usize,
    worker_id: &str,
) -> (Vec<SubmitPayload>, Vec<String>) {
    let results: Vec<(Option<SubmitPayload>, Option<String>)> = positions
        .par_iter()
        .map(|pos| {
            match solve_claimed(pos, max_empty) {
                Some(mut s) => {
                    s.worker_id = worker_id.to_string();
                    (Some(s), None)
                }
                None => (None, Some(pos.hash.clone())),
            }
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
