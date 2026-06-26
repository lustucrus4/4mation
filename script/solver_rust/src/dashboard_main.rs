//! Binaire dashboard seul — lecture SQLite + UI web (sans solveur).

mod game;
mod dashboard;

use anyhow::Result;
use clap::Parser;
use std::path::PathBuf;
use tracing_subscriber::EnvFilter;

use dashboard::{default_dashboard_config, run_dashboard_server};

const DEFAULT_DB: &str = "script/solver/data/tablebase.db";

#[derive(Parser, Debug)]
#[command(
    name = "4mation-dashboard",
    about = "Dashboard local solveur 4mation (Rust, lecture SQLite)"
)]
struct Args {
    /// Chemin vers tablebase.db
    #[arg(long, default_value = DEFAULT_DB)]
    db: PathBuf,

    /// Port HTTP
    #[arg(long, env = "SOLVER_DASHBOARD_PORT", default_value = "8765")]
    port: u16,

    /// Interface d'écoute
    #[arg(long, env = "SOLVER_DASHBOARD_HOST", default_value = "127.0.0.1")]
    host: String,
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::from_default_env().add_directive(tracing::Level::INFO.into()))
        .init();

    let args = Args::parse();
    let db_path = args.db;

    let url = format!("http://{}:{}/", args.host, args.port);
    println!("{}", "=".repeat(50));
    println!("  4mation — Dashboard solveur LOCAL (Rust)");
    println!("{}", "=".repeat(50));
    println!("URL      : {url}");
    println!("Base     : {}", db_path.display());
    println!(
        "Existe   : {}",
        if db_path.exists() {
            "oui"
        } else {
            "non — lancez seed_initial_tablebase.py"
        }
    );
    println!("Ctrl+C pour arrêter.");
    println!();

    let config = default_dashboard_config(db_path, args.host, args.port, false, None, None);
    run_dashboard_server(config).await
}
