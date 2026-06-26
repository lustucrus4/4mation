//! Boucle d'entraînement principale.

use std::path::PathBuf;
use std::time::Instant;

use anyhow::Result;
use rand::rngs::StdRng;
use rand::SeedableRng;
use rayon::ThreadPoolBuilder;
use tracing::{info, warn};

use crate::eval::{evaluate_vs_minimax, resolve_paths, EvalConfig};
use crate::imitation::{heuristic_bootstrap, run_imitation_bootstrap, ImitationConfig};
use crate::persistence::{now_iso, read_status, DataStore, MetricRow, TrainingStatus};
use crate::policy::{reinforce_update, LinearPolicy};
use crate::self_play::{batch_self_play, SelfPlayConfig};

pub struct TrainConfig {
    pub cores: usize,
    pub self_play_games: usize,
    pub eval_every: u64,
    pub eval_games: usize,
    pub mcts_sims: u32,
    pub learning_rate: f64,
    pub data_dir: PathBuf,
    pub resume: bool,
    pub imitate: bool,
    pub imitate_depth: u8,
    pub imitate_games: usize,
    pub total_steps: Option<u64>,
    pub python: String,
}

pub struct Trainer {
    pub cfg: TrainConfig,
    pub store: DataStore,
    pub policy: LinearPolicy,
    pub step: u64,
    pub total_games: u64,
    pub started_at: String,
}

impl Trainer {
    pub fn new(cfg: TrainConfig) -> Result<Self> {
        let store = DataStore::new(cfg.data_dir.clone())?;
        let policy = if cfg.resume {
            store.load_policy().unwrap_or_default()
        } else {
            let mut rng = StdRng::seed_from_u64(42);
            LinearPolicy::new_random(&mut rng)
        };
        let step = if cfg.resume {
            read_status(&store.status_path())?
                .map(|s| s.step)
                .unwrap_or(0)
        } else {
            0
        };
        let total_games = if cfg.resume {
            read_status(&store.status_path())?
                .map(|s| s.total_games)
                .unwrap_or(0)
        } else {
            0
        };
        let started_at = if cfg.resume {
            read_status(&store.status_path())?
                .map(|s| s.started_at)
                .unwrap_or_else(now_iso)
        } else {
            now_iso()
        };
        Ok(Self {
            cfg,
            store,
            policy,
            step,
            total_games,
            started_at,
        })
    }

    pub fn run(&mut self) -> Result<()> {
        ThreadPoolBuilder::new()
            .num_threads(self.cfg.cores)
            .build_global()
            .ok();

        let pid = std::process::id();
        info!(
            "Entraînement RL — {} cœurs, batch {} parties, eval tous les {} steps",
            self.cfg.cores, self.cfg.self_play_games, self.cfg.eval_every
        );

        self.write_status_snapshot(pid, "démarrage", 0.0, None, None)?;

        if !self.cfg.resume || self.step == 0 {
            self.bootstrap()?;
        }

        let self_cfg = SelfPlayConfig {
            mcts_sims: self.cfg.mcts_sims,
            temperature: 0.9,
            max_moves: 100,
        };

        let (script_path, project_root) = resolve_paths(&self.cfg.data_dir);
        let eval_cfg = EvalConfig {
            games: self.cfg.eval_games,
            mcts_sims: self.cfg.mcts_sims,
            python: self.cfg.python.clone(),
            script_path,
            project_root,
            ..EvalConfig::default()
        };

        let mut last_eval: Option<f64> = None;
        let mut games_since_eval = 0u64;

        loop {
            if let Some(max) = self.cfg.total_steps {
                if self.step >= max {
                    break;
                }
            }

            let t0 = Instant::now();
            let seed = self.step.wrapping_mul(7919).wrapping_add(42);
            let (trajectory, stats) = batch_self_play(
                &self.policy,
                &self_cfg,
                self.cfg.self_play_games,
                seed,
            );
            let elapsed = t0.elapsed().as_secs_f64().max(1e-6);
            let gps = self.cfg.self_play_games as f64 / elapsed;

            reinforce_update(&mut self.policy, &trajectory, self.cfg.learning_rate);
            self.step += 1;
            self.total_games += self.cfg.self_play_games as u64;
            games_since_eval += self.cfg.self_play_games as u64;

            let ckpt = self.store.save_policy(&self.policy, self.step)?;
            let win_rate = stats.win_rate_p1();

            let metric = MetricRow {
                ts: now_iso(),
                step: self.step,
                event: "self_play".into(),
                games: self.total_games,
                self_play_win_rate_p1: Some(win_rate),
                eval_vs_level5: last_eval,
                eval_games: None,
                policy_version: self.policy.version,
                games_per_sec: Some(gps),
                avg_moves: Some(stats.avg_moves),
                message: None,
            };
            self.store.append_metric(&metric)?;

            info!(
                "step={} games={} win_p1={:.2} gps={:.1} avg_moves={:.1} ckpt={}",
                self.step,
                self.total_games,
                win_rate,
                gps,
                stats.avg_moves,
                ckpt.display()
            );

            if games_since_eval >= self.cfg.eval_every || self.step == 1 {
                games_since_eval = 0;
                match evaluate_vs_minimax(&self.policy, &eval_cfg, seed.wrapping_add(999)) {
                    Ok(ev) => {
                        last_eval = Some(ev.win_rate);
                        info!(
                            "eval vs level_5: {:.1}% ({}/{}/{})",
                            ev.win_rate * 100.0,
                            ev.rl_wins,
                            ev.bot_wins,
                            ev.draws
                        );
                        let eval_metric = MetricRow {
                            ts: now_iso(),
                            step: self.step,
                            event: "eval_level5".into(),
                            games: self.total_games,
                            self_play_win_rate_p1: Some(win_rate),
                            eval_vs_level5: Some(ev.win_rate),
                            eval_games: Some(ev.games as u32),
                            policy_version: self.policy.version,
                            games_per_sec: Some(gps),
                            avg_moves: None,
                            message: Some(format!(
                                "wins={} losses={} draws={}",
                                ev.rl_wins, ev.bot_wins, ev.draws
                            )),
                        };
                        self.store.append_metric(&eval_metric)?;
                    }
                    Err(e) => {
                        warn!("eval level_5 ignorée: {e:#}");
                    }
                }
            }

            let eta = self.cfg.total_steps.map(|max| {
                let remaining = max.saturating_sub(self.step) as f64;
                remaining * elapsed
            });

            let status = TrainingStatus {
                running: true,
                pid,
                step: self.step,
                total_games: self.total_games,
                policy_version: self.policy.version,
                cores: self.cfg.cores,
                self_play_batch: self.cfg.self_play_games,
                last_self_play_win_rate: win_rate,
                last_eval_vs_level5: last_eval,
                games_per_sec: gps,
                eta_seconds: eta,
                started_at: self.started_at.clone(),
                updated_at: now_iso(),
                checkpoint: ckpt.display().to_string(),
                message: "entraînement actif".into(),
            };
            self.store.write_status(&status)?;
        }

        Ok(())
    }

    fn write_status_snapshot(
        &self,
        pid: u32,
        message: &str,
        games_per_sec: f64,
        last_eval: Option<f64>,
        eta: Option<f64>,
    ) -> Result<()> {
        let checkpoint = self
            .store
            .latest_checkpoint()
            .display()
            .to_string();
        let status = TrainingStatus {
            running: true,
            pid,
            step: self.step,
            total_games: self.total_games,
            policy_version: self.policy.version,
            cores: self.cfg.cores,
            self_play_batch: self.cfg.self_play_games,
            last_self_play_win_rate: 0.0,
            last_eval_vs_level5: last_eval,
            games_per_sec,
            eta_seconds: eta,
            started_at: self.started_at.clone(),
            updated_at: now_iso(),
            checkpoint,
            message: message.into(),
        };
        self.store.write_status(&status)?;
        Ok(())
    }

    fn bootstrap(&mut self) -> Result<()> {
        info!("Bootstrap policy (imitation + heuristique)");
        let pid = std::process::id();
        self.write_status_snapshot(pid, "bootstrap", 0.0, None, None)?;
        let (script_path, project_root) = resolve_paths(&self.cfg.data_dir);

        if self.cfg.imitate {
            let icfg = ImitationConfig {
                games: self.cfg.imitate_games,
                depth: self.cfg.imitate_depth,
                python: self.cfg.python.clone(),
                script_path: script_path.clone(),
                project_root: project_root.clone(),
            };
            info!(
                "Imitation Minimax d{} — {} parties (Python -u)",
                icfg.depth, icfg.games
            );
            match run_imitation_bootstrap(&mut self.policy, &icfg) {
                Ok(n) => info!("Imitation Minimax d{}: {} échantillons", icfg.depth, n),
                Err(e) => warn!("Imitation Python échouée ({e:#}), heuristique Rust"),
            }
        }

        let h = heuristic_bootstrap(&mut self.policy, 200, 7);
        info!("Heuristique Rust: {} coups", h);
        self.store.save_policy(&self.policy, 0)?;
        Ok(())
    }
}
