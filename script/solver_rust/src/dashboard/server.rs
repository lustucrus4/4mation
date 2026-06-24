//! Serveur Axum — fichiers statiques + API JSON.

use anyhow::{Context, Result};
use axum::{
    extract::{ConnectInfo, State},
    http::{header, StatusCode},
    response::{IntoResponse, Json},
    routing::{get, post},
    Router,
};
use std::net::SocketAddr;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use tower_http::cors::CorsLayer;
use tower_http::services::ServeDir;
use tracing::info;

use super::process;
use super::stats::{
    self, get_health, get_process_status, get_solver_status, get_work_stats, resolve_web_dir,
};

#[derive(Clone)]
pub struct DashboardConfig {
    pub db_path: PathBuf,
    pub web_dir: PathBuf,
    pub host: String,
    pub port: u16,
    pub solver_in_process: bool,
    pub shutdown: Option<Arc<AtomicBool>>,
}

#[derive(Clone)]
struct AppState {
    config: DashboardConfig,
}

fn is_localhost(addr: &SocketAddr) -> bool {
    match addr.ip() {
        std::net::IpAddr::V4(v4) => v4.is_loopback(),
        std::net::IpAddr::V6(v6) => v6.is_loopback(),
    }
}

fn localhost_denied() -> (StatusCode, Json<serde_json::Value>) {
    (
        StatusCode::FORBIDDEN,
        Json(serde_json::json!({
            "success": false,
            "error": "Endpoints locaux réservés à 127.0.0.1"
        })),
    )
}

async fn index_handler(State(state): State<AppState>) -> impl IntoResponse {
    let path = state.config.web_dir.join("index.html");
    match tokio::fs::read(&path).await {
        Ok(bytes) => (
            [(header::CONTENT_TYPE, "text/html; charset=utf-8")],
            bytes,
        )
            .into_response(),
        Err(_) => (StatusCode::NOT_FOUND, "index.html introuvable").into_response(),
    }
}

async fn solver_status_handler(State(state): State<AppState>) -> Json<stats::SolverStatusPayload> {
    Json(get_solver_status(
        &state.config.db_path,
        state.config.solver_in_process,
    ))
}

async fn work_stats_handler(State(state): State<AppState>) -> Json<stats::WorkStatsPayload> {
    Json(get_work_stats(&state.config.db_path))
}

async fn health_handler(State(state): State<AppState>) -> Json<stats::HealthPayload> {
    Json(get_health(&state.config.db_path))
}

async fn process_status_handler(
    ConnectInfo(addr): ConnectInfo<SocketAddr>,
    State(state): State<AppState>,
) -> impl IntoResponse {
    if !is_localhost(&addr) {
        return localhost_denied().into_response();
    }
    Json(get_process_status(state.config.solver_in_process)).into_response()
}

async fn start_solver_handler(
    ConnectInfo(addr): ConnectInfo<SocketAddr>,
    State(state): State<AppState>,
) -> impl IntoResponse {
    if !is_localhost(&addr) {
        return localhost_denied().into_response();
    }
    if state.config.solver_in_process || process::is_solver_running() {
        return (
            StatusCode::CONFLICT,
            Json(serde_json::json!({
                "success": false,
                "error": "Le solveur est déjà en cours d'exécution.",
                "running": true
            })),
        )
            .into_response();
    }
    match process::launch_local_script("solver", "4mation-solver") {
        Ok(script_path) => (
            StatusCode::OK,
            Json(serde_json::json!({
                "success": true,
                "message": "Solveur lancé dans une nouvelle fenêtre.",
                "script": script_path.display().to_string()
            })),
        )
            .into_response(),
        Err(e) => (
            StatusCode::BAD_REQUEST,
            Json(serde_json::json!({
                "success": false,
                "error": e.to_string()
            })),
        )
            .into_response(),
    }
}

async fn start_stack_handler(
    ConnectInfo(addr): ConnectInfo<SocketAddr>,
    State(_state): State<AppState>,
) -> impl IntoResponse {
    if !is_localhost(&addr) {
        return localhost_denied().into_response();
    }
    match process::launch_local_script("stack", "4mation-stack") {
        Ok(script_path) => (
            StatusCode::OK,
            Json(serde_json::json!({
                "success": true,
                "message": "Stack locale lancée (dashboard + solveur).",
                "script": script_path.display().to_string()
            })),
        )
            .into_response(),
        Err(e) => (
            StatusCode::BAD_REQUEST,
            Json(serde_json::json!({
                "success": false,
                "error": e.to_string()
            })),
        )
            .into_response(),
    }
}

async fn stop_solver_handler(
    ConnectInfo(addr): ConnectInfo<SocketAddr>,
    State(state): State<AppState>,
) -> impl IntoResponse {
    if !is_localhost(&addr) {
        return localhost_denied().into_response();
    }

    if state.config.solver_in_process {
        if let Some(shutdown) = &state.config.shutdown {
            shutdown.store(true, Ordering::Relaxed);
            return (
                StatusCode::OK,
                Json(serde_json::json!({
                    "success": true,
                    "message": "Arrêt du solveur demandé.",
                    "running": false
                })),
            )
                .into_response();
        }
    }

    if !process::is_solver_running() {
        return (
            StatusCode::NOT_FOUND,
            Json(serde_json::json!({
                "success": false,
                "error": "Aucun solveur en cours d'exécution.",
                "running": false
            })),
        )
            .into_response();
    }
    process::stop_solver_process();
    (
        StatusCode::OK,
        Json(serde_json::json!({
            "success": true,
            "message": "Arrêt du solveur demandé.",
            "running": false
        })),
    )
        .into_response()
}

fn build_router(state: AppState) -> Router {
    let web = state.config.web_dir.clone();
    Router::new()
        .route("/", get(index_handler))
        .route("/api/solver/status", get(solver_status_handler))
        .route("/api/solver/work/stats", get(work_stats_handler))
        .route("/health", get(health_handler))
        .route("/api/local/process-status", get(process_status_handler))
        .route("/api/local/start-solver", post(start_solver_handler))
        .route("/api/local/start-stack", post(start_stack_handler))
        .route("/api/local/stop-solver", post(stop_solver_handler))
        .fallback_service(ServeDir::new(web))
        .layer(CorsLayer::permissive())
        .with_state(state)
}

pub async fn run_dashboard_server(config: DashboardConfig) -> Result<()> {
    if !config.web_dir.is_dir() {
        anyhow::bail!("dossier web introuvable : {}", config.web_dir.display());
    }

    let addr: SocketAddr = format!("{}:{}", config.host, config.port)
        .parse()
        .context("adresse d'écoute invalide")?;

    let state = AppState {
        config: config.clone(),
    };
    let app = build_router(state);

    let url = format!("http://{}:{}/", config.host, config.port);
    info!("Dashboard local — URL {}", url);
    info!("Base SQLite : {}", config.db_path.display());

    let listener = tokio::net::TcpListener::bind(addr)
        .await
        .with_context(|| format!("impossible d'écouter sur {addr}"))?;

    axum::serve(
        listener,
        app.into_make_service_with_connect_info::<SocketAddr>(),
    )
    .await
    .context("serveur dashboard arrêté avec erreur")?;

    Ok(())
}

pub fn spawn_dashboard_thread(config: DashboardConfig) -> Result<()> {
    std::thread::Builder::new()
        .name("4mation-dashboard".into())
        .spawn(move || {
            let rt = tokio::runtime::Builder::new_multi_thread()
                .enable_all()
                .build()
                .expect("runtime tokio dashboard");
            if let Err(e) = rt.block_on(run_dashboard_server(config)) {
                tracing::error!("dashboard : {:#}", e);
            }
        })
        .context("impossible de démarrer le thread dashboard")?;
    Ok(())
}

pub fn default_dashboard_config(
    db_path: PathBuf,
    host: String,
    port: u16,
    solver_in_process: bool,
    shutdown: Option<Arc<AtomicBool>>,
) -> DashboardConfig {
    DashboardConfig {
        db_path,
        web_dir: resolve_web_dir(),
        host,
        port,
        solver_in_process,
        shutdown,
    }
}
