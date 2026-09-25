//! Solveur exact depuis l'ouverture, avec dashboard local.

use std::process::ExitCode;
use std::sync::Arc;
use std::time::Duration;

use axum::extract::State;
use axum::response::{Html, Json};
use axum::routing::get;
use axum::Router;
use clap::Parser;
use formation_worker::proof::{solve_opening, ProofConfig, ProofLive};

#[derive(Parser, Debug)]
#[command(
    name = "4mation-proof",
    about = "Prouve le résultat de 4mation et affiche l'avancement dans le navigateur"
)]
struct Args {
    /// Fils de recherche
    #[arg(long, env = "SOLVER_THREADS")]
    threads: Option<usize>,

    /// Mémoire de la table de transposition, en Mo
    #[arg(long, default_value = "1024")]
    tt_mb: usize,

    /// Arrêt après N secondes (0 = jusqu'à la preuve)
    #[arg(long, default_value = "0")]
    seconds: u64,

    /// Port du dashboard (uniquement en local)
    #[arg(long, default_value = "8770")]
    port: u16,

    /// Ne pas ouvrir le dashboard
    #[arg(long)]
    no_dashboard: bool,
}

fn label(v: i8) -> &'static str {
    match v {
        1 => "victoire du joueur 1",
        0 => "nulle",
        -1 => "défaite du joueur 1",
        _ => "inconnu",
    }
}

fn spawn_dashboard(live: Arc<ProofLive>, port: u16) {
    std::thread::Builder::new()
        .name("proof-dashboard".into())
        .spawn(move || {
            let rt = tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()
                .expect("runtime dashboard");
            rt.block_on(async move {
                let app = Router::new()
                    .route("/", get(index))
                    .route("/api/status", get(status))
                    .with_state(live);
                let addr = format!("127.0.0.1:{port}");
                let listener = match tokio::net::TcpListener::bind(&addr).await {
                    Ok(listener) => listener,
                    Err(err) => {
                        eprintln!("Dashboard indisponible sur {addr} : {err}");
                        return;
                    }
                };
                if let Err(err) = axum::serve(listener, app).await {
                    eprintln!("Dashboard arrêté : {err}");
                }
            });
        })
        .expect("thread dashboard");
}

async fn index() -> Html<&'static str> {
    Html(include_str!("../web/proof.html"))
}

async fn status(State(live): State<Arc<ProofLive>>) -> Json<serde_json::Value> {
    Json(live.status_json())
}

fn main() -> ExitCode {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::from_default_env()
                .add_directive(tracing::Level::INFO.into()),
        )
        .init();

    let args = Args::parse();
    let threads = args.threads.unwrap_or_else(|| {
        std::thread::available_parallelism()
            .map(|n| n.get())
            .unwrap_or(8)
    });
    let live = ProofLive::new(threads, args.tt_mb);

    if !args.no_dashboard {
        spawn_dashboard(Arc::clone(&live), args.port);
        std::thread::sleep(Duration::from_millis(250));
        println!("Dashboard : http://127.0.0.1:{}/", args.port);
    }

    let report = solve_opening(&ProofConfig {
        threads,
        tt_mb: args.tt_mb,
        seconds: args.seconds,
        live: Some(live),
    });

    let secs = report.elapsed.as_secs_f64().max(0.001);
    println!();
    println!(
        "Orbites cherchées : {}   nœuds : {}   temps : {:.1} s   débit : {:.2} M/s",
        report.orbits,
        report.nodes,
        secs,
        report.nodes as f64 / secs / 1e6
    );

    match report.result {
        Some(v) => {
            println!("Résultat prouvé : {}", label(v));
            if let Some((r, c)) = report.best {
                println!("Meilleur premier coup : ligne {r}, colonne {c}");
            }
        }
        None => {
            println!("Preuve incomplète.");
        }
    }

    println!();
    println!("Coups d'ouverture (un représentant par symétrie) :");
    for mv in &report.moves {
        match mv.value_for_first {
            Some(v) => println!("  ({}, {})  {}", mv.row, mv.col, label(v)),
            None => println!("  ({}, {})  non terminé", mv.row, mv.col),
        }
    }

    if !args.no_dashboard {
        println!();
        println!(
            "Le dashboard reste ouvert sur http://127.0.0.1:{}/ — Ctrl+C pour quitter.",
            args.port
        );
        loop {
            std::thread::sleep(Duration::from_secs(3600));
        }
    }

    if report.result.is_some() {
        ExitCode::SUCCESS
    } else {
        ExitCode::from(2)
    }
}
