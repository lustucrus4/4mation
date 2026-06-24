//! Serveur HTTP local — stats SQLite + fichiers statiques web/.

mod process;
mod server;
mod stats;

pub use server::{
    default_dashboard_config, run_dashboard_server, spawn_dashboard_thread, DashboardConfig,
};
