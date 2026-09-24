//! Boucle d'entraînement principale.

use std::path::PathBuf;
use std::time::Instant;

use anyhow::Result;
use rayon::ThreadPoolBuilder;
use tracing::{info, warn};

use crate::eval::{evaluate_vs_minimax, resolve_paths, EvalConfig, MinimaxBridge};
use crate::imitation::{heuristic_bootstrap, run_imitation_bootstrap, ImitationConfig};
use crate::persistence::{now_iso, read_status, DataStore, MetricRow, TrainingStatus};
use crate::policy::{reinforce_update, PolicyNet};
use crate::self_play::{batch_self_play, SelfPlayConfig};
use crate::vs_minimax_training::batch_vs_minimax;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TrainingPhase {
    VsLevel5,
    SelfPlay,
}

impl TrainingPhase {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::VsLevel5 => "vs_level5",
            Self::SelfPlay => "self_play",
        }
    }

    pub fn from_str(s: &str) -> Option<Self> {
        match s {
            "vs_level5" => Some(Self::VsLevel5),
            "self_play" => Some(Self::SelfPlay),
            _ => None,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TrainingPhaseMode {
    Auto,
    VsLevel5,
    SelfPlay,
}

impl TrainingPhaseMode {
    pub fn from_cli(s: &str) -> Self {
        match s {
            "vs_level5" => Self::VsLevel5,
            "self_play" => Self::SelfPlay,
            _ => Self::Auto,
        }
    }
}

pub struct TrainConfig {
    pub cores: usize,
    pub self_play_games: usize,
    /// Éval level_5 tous les N parties cumulées
    pub eval_every_l5: u64,
    /// Éval level_3 (moins fréquente, suivi early-game)
    pub eval_every_l3: u64,
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
    pub curriculum_rate: f64,
    pub eval_mcts_sims: u32,
    pub fresh: bool,
    pub value_lr: f64,
    pub use_az_mcts: bool,
    /// Checkpoint numéroté tous les N steps (latest.json à chaque step)
    pub checkpoint_every: u64,
    /// auto | vs_level5 | self_play
    pub training_phase_mode: TrainingPhaseMode,
    /// Seuil win rate vs level_5 pour basculer en self-play (mode auto)
    pub phase2_win_threshold: f64,
    /// Nombre de parties pour la décision de transition (stable)
    pub phase_transition_games: usize,
}

pub struct Trainer {
    pub cfg: TrainConfig,
    pub store: DataStore,
    pub policy: PolicyNet,
    pub step: u64,
    pub total_games: u64,
    pub started_at: String,
}

impl Trainer {
    pub fn new(cfg: TrainConfig) -> Result<Self> {
        let store = DataStore::new(cfg.data_dir.clone())?;
        let policy = if cfg.fresh {
            info!("Nouveau réseau MLP (reset --fresh)");
            PolicyNet::new_mlp_random()
        } else if cfg.resume {
            store.load_policy().unwrap_or_else(|_| PolicyNet::new_mlp_random())
        } else {
            PolicyNet::new_mlp_random()
        };
        let step = if cfg.fresh {
            0
        } else if cfg.resume {
            read_status(&store.status_path())?
                .map(|s| s.step)
                .unwrap_or(0)
        } else {
            0
        };
        let total_games = if cfg.fresh {
            0
        } else if cfg.resume {
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

    fn resolve_initial_phase(&self) -> TrainingPhase {
        match self.cfg.training_phase_mode {
            TrainingPhaseMode::SelfPlay => TrainingPhase::SelfPlay,
            TrainingPhaseMode::VsLevel5 => TrainingPhase::VsLevel5,
            TrainingPhaseMode::Auto => {
                if self.cfg.resume && !self.cfg.fresh {
                    if let Ok(Some(status)) = read_status(&self.store.status_path()) {
                        if let Some(ref phase) = status.training_phase {
                            if let Some(p) = TrainingPhase::from_str(phase) {
                                return p;
                            }
                        }
                        // Reprise sans champ phase : conserver self-play (runs existants)
                        return TrainingPhase::SelfPlay;
                    }
                }
                TrainingPhase::VsLevel5
            }
        }
    }

    pub fn run(&mut self) -> Result<()> {
        ThreadPoolBuilder::new()
            .num_threads(self.cfg.cores)
            .build_global()
            .ok();

        let pid = std::process::id();
        let mut current_phase = self.resolve_initial_phase();
        info!(
            "Entraînement AlphaZero-lite — phase={}, mode={:?}, seuil L5→SP {:.0}%, {} cœurs, curriculum {:.0}%, MCTS {} sims, eval L5/{}, L3/{}",
            current_phase.as_str(),
            self.cfg.training_phase_mode,
            self.cfg.phase2_win_threshold * 100.0,
            self.cfg.cores,
            self.cfg.curriculum_rate * 100.0,
            self.cfg.mcts_sims,
            self.cfg.eval_every_l5,
            self.cfg.eval_every_l3
        );

        self.write_status_snapshot(pid, &format!("démarrage ({})", current_phase.as_str()), 0.0, None, None, None, current_phase)?;

        if !self.cfg.resume || self.step == 0 || self.cfg.fresh {
            self.bootstrap()?;
        }

        let self_cfg = SelfPlayConfig {
            mcts_sims: self.cfg.mcts_sims,
            temperature: 0.85,
            max_moves: 120,
            curriculum_rate: self.cfg.curriculum_rate,
            use_az_mcts: self.cfg.use_az_mcts,
        };

        let (script_path, project_root) = resolve_paths(&self.cfg.data_dir);
        let mut eval_cfg = EvalConfig {
            games: self.cfg.eval_games,
            mcts_sims: self.cfg.eval_mcts_sims,
            python: self.cfg.python.clone(),
            script_path,
            project_root,
            use_az_mcts: self.cfg.use_az_mcts,
            ..EvalConfig::default()
        };

        let mut minimax_bridge = MinimaxBridge::spawn(&eval_cfg)?;
        info!("Daemon eval bots prêt (level_3 + level_5)");

        let mut last_eval_l5: Option<f64> = None;
        let mut last_eval_l3: Option<f64> = None;
        let mut games_since_eval_l5 = 0u64;
        let mut games_since_eval_l3 = 0u64;

        let mut vs_l5_eval_cfg = eval_cfg.clone();
        vs_l5_eval_cfg.bot_id = "level_5".to_string();

        loop {
            if let Some(max) = self.cfg.total_steps {
                if self.step >= max {
                    break;
                }
            }

            let t0 = Instant::now();
            let seed = self.step.wrapping_mul(7919).wrapping_add(42);

            let (trajectory, stats, train_event, batch_win_rate) = match current_phase {
                TrainingPhase::VsLevel5 => {
                    let (trajectory, stats) = batch_vs_minimax(
                        &self.policy,
                        &self_cfg,
                        &vs_l5_eval_cfg,
                        self.cfg.self_play_games,
                        seed,
                    )?;
                    let wr = stats.rl_win_rate;
                    (trajectory, stats, "vs_level5", wr)
                }
                TrainingPhase::SelfPlay => {
                    let (trajectory, stats) = batch_self_play(
                        &self.policy,
                        &self_cfg,
                        self.cfg.self_play_games,
                        seed,
                    );
                    let wr = stats.win_rate_p1();
                    (trajectory, stats, "self_play", wr)
                }
            };
            let elapsed = t0.elapsed().as_secs_f64().max(1e-6);
            let gps = self.cfg.self_play_games as f64 / elapsed;

            reinforce_update(
                &mut self.policy,
                &trajectory,
                self.cfg.learning_rate,
                self.cfg.value_lr,
            );
            self.step += 1;
            self.total_games += self.cfg.self_play_games as u64;
            games_since_eval_l5 += self.cfg.self_play_games as u64;
            games_since_eval_l3 += self.cfg.self_play_games as u64;

            let ckpt = self
                .store
                .save_policy(&self.policy, self.step, self.cfg.checkpoint_every)?;
            let win_rate = batch_win_rate;

            let metric = MetricRow {
                ts: now_iso(),
                step: self.step,
                event: train_event.into(),
                games: self.total_games,
                self_play_win_rate_p1: Some(win_rate),
                eval_vs_level5: last_eval_l5,
                eval_vs_level3: last_eval_l3,
                eval_games: None,
                policy_version: self.policy.version(),
                games_per_sec: Some(gps),
                avg_moves: Some(stats.avg_moves),
                message: Some(format!("phase={}", current_phase.as_str())),
            };
            self.store.append_metric(&metric)?;

            info!(
                "step={} phase={} games={} win={:.2} gps={:.1} avg_moves={:.1} ckpt={}",
                self.step,
                current_phase.as_str(),
                self.total_games,
                win_rate,
                gps,
                stats.avg_moves,
                ckpt.display()
            );

            let run_l5 = self.step == 1 || games_since_eval_l5 >= self.cfg.eval_every_l5;
            let run_l3 = self.step == 1 || games_since_eval_l3 >= self.cfg.eval_every_l3;

            if run_l5 {
                games_since_eval_l5 = 0;
            }
            if run_l3 {
                games_since_eval_l3 = 0;
            }

            let l5_games = if current_phase == TrainingPhase::VsLevel5
                && self.cfg.training_phase_mode == TrainingPhaseMode::Auto
            {
                self.cfg.phase_transition_games.max(self.cfg.eval_games)
            } else {
                self.cfg.eval_games
            };

            let eval_plan: Vec<(&str, &str, usize)> = [
                if run_l3 {
                    Some(("level_3", "level_3", self.cfg.eval_games))
                } else {
                    None
                },
                if run_l5 {
                    Some(("level_5", "level_5", l5_games))
                } else {
                    None
                },
            ]
            .into_iter()
            .flatten()
            .collect();

            for (bot_id, label, games_n) in eval_plan {
                eval_cfg.bot_id = bot_id.to_string();
                eval_cfg.games = games_n;
                match evaluate_vs_minimax(
                    &self.policy,
                    &eval_cfg,
                    &mut minimax_bridge,
                    seed.wrapping_add(if bot_id == "level_3" { 333 } else { 999 }),
                ) {
                    Ok(ev) => {
                        info!(
                            "eval vs {}: {:.1}% ({}/{}/{})",
                            label,
                            ev.win_rate * 100.0,
                            ev.rl_wins,
                            ev.bot_wins,
                            ev.draws
                        );
                        if bot_id == "level_3" {
                            last_eval_l3 = Some(ev.win_rate);
                        } else {
                            last_eval_l5 = Some(ev.win_rate);
                        }
                        let eval_metric = MetricRow {
                            ts: now_iso(),
                            step: self.step,
                            event: format!("eval_{label}"),
                            games: self.total_games,
                            self_play_win_rate_p1: Some(win_rate),
                            eval_vs_level5: if bot_id == "level_5" {
                                Some(ev.win_rate)
                            } else {
                                last_eval_l5
                            },
                            eval_vs_level3: if bot_id == "level_3" {
                                Some(ev.win_rate)
                            } else {
                                last_eval_l3
                            },
                            eval_games: Some(ev.games as u32),
                            policy_version: self.policy.version(),
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
                        warn!("eval {label} ignorée: {e:#}");
                    }
                }
            }

            if self.cfg.training_phase_mode == TrainingPhaseMode::Auto
                && current_phase == TrainingPhase::VsLevel5
                && run_l5
            {
                if let Some(wr) = last_eval_l5 {
                    if wr >= self.cfg.phase2_win_threshold {
                        let from = current_phase.as_str();
                        current_phase = TrainingPhase::SelfPlay;
                        info!(
                            "Transition phase {} → {} (eval L5 {:.1}% >= seuil {:.1}%)",
                            from,
                            current_phase.as_str(),
                            wr * 100.0,
                            self.cfg.phase2_win_threshold * 100.0
                        );
                        let transition_metric = MetricRow {
                            ts: now_iso(),
                            step: self.step,
                            event: "phase_transition".into(),
                            games: self.total_games,
                            self_play_win_rate_p1: Some(win_rate),
                            eval_vs_level5: last_eval_l5,
                            eval_vs_level3: last_eval_l3,
                            eval_games: Some(l5_games as u32),
                            policy_version: self.policy.version(),
                            games_per_sec: Some(gps),
                            avg_moves: None,
                            message: Some(format!(
                                "{from} -> {}: win_rate={wr:.4}",
                                current_phase.as_str()
                            )),
                        };
                        self.store.append_metric(&transition_metric)?;
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
                policy_version: self.policy.version(),
                cores: self.cfg.cores,
                self_play_batch: self.cfg.self_play_games,
                last_self_play_win_rate: win_rate,
                last_eval_vs_level5: last_eval_l5,
                last_eval_vs_level3: last_eval_l3,
                games_per_sec: gps,
                eta_seconds: eta,
                started_at: self.started_at.clone(),
                updated_at: now_iso(),
                checkpoint: ckpt.display().to_string(),
                message: format!("entraînement actif ({})", current_phase.as_str()),
                training_phase: Some(current_phase.as_str().to_string()),
                phase2_win_threshold: Some(self.cfg.phase2_win_threshold),
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
        last_eval_l5: Option<f64>,
        last_eval_l3: Option<f64>,
        eta: Option<f64>,
        phase: TrainingPhase,
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
            policy_version: self.policy.version(),
            cores: self.cfg.cores,
            self_play_batch: self.cfg.self_play_games,
            last_self_play_win_rate: 0.0,
            last_eval_vs_level5: last_eval_l5,
            last_eval_vs_level3: last_eval_l3,
            games_per_sec,
            eta_seconds: eta,
            started_at: self.started_at.clone(),
            updated_at: now_iso(),
            checkpoint,
            message: message.into(),
            training_phase: Some(phase.as_str().to_string()),
            phase2_win_threshold: Some(self.cfg.phase2_win_threshold),
        };
        self.store.write_status(&status)?;
        Ok(())
    }

    fn bootstrap(&mut self) -> Result<()> {
        info!("Bootstrap policy (heuristique Rust{} )", if self.cfg.imitate { " + imitation Minimax" } else { "" });
        let pid = std::process::id();
        let phase = self.resolve_initial_phase();
        self.write_status_snapshot(pid, "bootstrap", 0.0, None, None, None, phase)?;
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
        self.store.save_policy(&self.policy, 0, self.cfg.checkpoint_every)?;
        Ok(())
    }
}
