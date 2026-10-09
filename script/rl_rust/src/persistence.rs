//! Persistance checkpoints, métriques JSONL et SQLite.

use std::fs::{File, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result};
use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};

use crate::policy::PolicyNet;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct TrainingStatus {
    pub running: bool,
    pub pid: u32,
    pub step: u64,
    pub total_games: u64,
    pub policy_version: u64,
    pub cores: usize,
    pub self_play_batch: usize,
    pub last_self_play_win_rate: f64,
    pub last_eval_vs_level5: Option<f64>,
    #[serde(default)]
    pub last_eval_vs_level3: Option<f64>,
    pub games_per_sec: f64,
    pub eta_seconds: Option<f64>,
    pub started_at: String,
    pub updated_at: String,
    pub checkpoint: String,
    pub message: String,
    /// Phase courante : `vs_level5` | `self_play`
    #[serde(default)]
    pub training_phase: Option<String>,
    #[serde(default)]
    pub phase2_win_threshold: Option<f64>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct MetricRow {
    pub ts: String,
    pub step: u64,
    pub event: String,
    pub games: u64,
    pub self_play_win_rate_p1: Option<f64>,
    pub eval_vs_level5: Option<f64>,
    #[serde(default)]
    pub eval_vs_level3: Option<f64>,
    pub eval_games: Option<u32>,
    pub policy_version: u64,
    pub games_per_sec: Option<f64>,
    pub avg_moves: Option<f64>,
    pub message: Option<String>,
}

pub struct DataStore {
    pub root: PathBuf,
}

impl DataStore {
    pub fn new(root: PathBuf) -> Result<Self> {
        std::fs::create_dir_all(&root)?;
        std::fs::create_dir_all(root.join("checkpoints"))?;
        Ok(Self { root })
    }

    pub fn status_path(&self) -> PathBuf {
        self.root.join("status.json")
    }

    pub fn metrics_path(&self) -> PathBuf {
        self.root.join("metrics.jsonl")
    }

    pub fn db_path(&self) -> PathBuf {
        self.root.join("metrics.db")
    }

    pub fn latest_checkpoint(&self) -> PathBuf {
        self.root.join("checkpoints").join("latest.json")
    }

    pub fn checkpoint_for_step(&self, step: u64) -> PathBuf {
        self.root
            .join("checkpoints")
            .join(format!("policy_step_{step:08}.json"))
    }

    pub fn init_db(&self) -> Result<Connection> {
        let conn = Connection::open(self.db_path())?;
        conn.execute_batch(
            "
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                step INTEGER NOT NULL,
                event TEXT NOT NULL,
                games INTEGER,
                self_play_win_rate REAL,
                eval_vs_level5 REAL,
                policy_version INTEGER,
                games_per_sec REAL,
                payload TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_metrics_step ON metrics(step);
            ",
        )?;
        Ok(conn)
    }

    pub fn write_status(&self, status: &TrainingStatus) -> Result<()> {
        let file = File::create(self.status_path())?;
        serde_json::to_writer_pretty(file, status)?;
        Ok(())
    }

    pub fn append_metric(&self, row: &MetricRow) -> Result<()> {
        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(self.metrics_path())?;
        writeln!(file, "{}", serde_json::to_string(row)?)?;

        if let Ok(conn) = self.init_db() {
            let _ = conn.execute(
                "INSERT INTO metrics (ts, step, event, games, self_play_win_rate, eval_vs_level5, policy_version, games_per_sec, payload)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)",
                params![
                    row.ts,
                    row.step,
                    row.event,
                    row.games,
                    row.self_play_win_rate_p1,
                    row.eval_vs_level5,
                    row.policy_version,
                    row.games_per_sec,
                    serde_json::to_string(row).unwrap_or_default(),
                ],
            );
        }
        Ok(())
    }

    /// Sauvegarde `latest.json` à chaque appel ; checkpoint numéroté tous les `checkpoint_every` steps.
    pub fn save_policy(&self, policy: &PolicyNet, step: u64, checkpoint_every: u64) -> Result<PathBuf> {
        policy.save(&self.latest_checkpoint())?;
        let save_numbered = checkpoint_every == 0
            || step == 0
            || checkpoint_every == 1
            || step % checkpoint_every == 0;
        if save_numbered {
            let path = self.checkpoint_for_step(step);
            policy.save(&path)?;
            Ok(path)
        } else {
            Ok(self.latest_checkpoint())
        }
    }

    pub fn load_policy(&self) -> Result<PolicyNet> {
        let latest = self.latest_checkpoint();
        if latest.exists() {
            return PolicyNet::load(&latest);
        }
        Ok(PolicyNet::default())
    }
}

pub fn now_iso() -> String {
    let dur = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default();
    format!("{}", dur.as_secs())
}

pub fn read_metrics_jsonl(path: &Path, limit: usize) -> Result<Vec<MetricRow>> {
    if !path.exists() {
        return Ok(vec![]);
    }
    let file = File::open(path)?;
    let reader = BufReader::new(file);
    let mut rows: Vec<MetricRow> = reader
        .lines()
        .filter_map(|l| l.ok())
        .filter_map(|l| serde_json::from_str(&l).ok())
        .collect();
    if rows.len() > limit {
        rows.drain(0..rows.len() - limit);
    }
    Ok(rows)
}

pub fn read_status(path: &Path) -> Result<Option<TrainingStatus>> {
    if !path.exists() {
        return Ok(None);
    }
    let file = File::open(path).with_context(|| format!("lecture {path:?}"))?;
    Ok(serde_json::from_reader(file).ok())
}
