//! CLI entraînement RL 4mation.

use std::path::PathBuf;

use anyhow::Result;
use clap::Parser;
use formation_rl::{TrainConfig, Trainer, TrainingPhaseMode};
use tracing_subscriber::EnvFilter;

#[derive(Parser, Debug)]
#[command(
    name = "train",
    about = "Entraînement RL 4mation (MLP + self-play + curriculum + eval level_5)"
)]
struct Args {
    #[arg(long, default_value = "16")]
    cores: usize,

    #[arg(long, default_value = "1000")]
    self_play_games: usize,

    /// Éval vs level_5 tous les N parties cumulées (alias historique: --eval-every)
    #[arg(long, default_value = "10000", alias = "eval-every")]
    eval_every_l5: u64,

    /// Éval vs level_3 (suivi early-game, moins fréquent)
    #[arg(long, default_value = "25000")]
    eval_every_l3: u64,

    #[arg(long, default_value = "12")]
    eval_games: usize,

    #[arg(long, default_value = "0.008")]
    value_lr: f64,

    #[arg(long, default_value_t = true)]
    az_mcts: bool,

    #[arg(long, default_value = "36")]
    mcts_sims: u32,

    #[arg(long, default_value = "16")]
    eval_mcts_sims: u32,

    /// Checkpoint numéroté tous les N steps (latest.json à chaque step)
    #[arg(long, default_value = "25")]
    checkpoint_every: u64,

    #[arg(long, default_value = "0.003")]
    lr: f64,

    #[arg(long)]
    resume: bool,

    /// Repartir de zéro avec un nouveau réseau MLP
    #[arg(long)]
    fresh: bool,

    #[arg(long, action = clap::ArgAction::SetTrue)]
    imitate: bool,

    #[arg(long, default_value = "6")]
    imitate_depth: u8,

    #[arg(long, default_value = "50")]
    imitate_games: usize,

    /// Fraction de parties vs adversaire curriculum (heuristique / minimax Rust)
    #[arg(long, default_value = "0.45")]
    curriculum: f64,

    /// Phase d'entraînement : auto (L5 puis self-play), vs_level5, self_play
    #[arg(long, default_value = "self_play")]
    training_phase: String,

    /// Seuil win rate vs level_5 pour basculer en self-play (mode auto)
    #[arg(long, default_value = "0.50")]
    phase2_win_threshold: f64,

    /// Parties eval L5 pour décision de transition (mode auto, phase 1)
    #[arg(long, default_value = "20")]
    phase_transition_games: usize,

    #[arg(long, default_value = "data")]
    data_dir: PathBuf,

    #[arg(long, default_value = "0")]
    max_steps: u64,

    #[arg(long, default_value = "py")]
    python: String,
}

fn resolve_data_dir(path: PathBuf) -> PathBuf {
    let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let rel = if path.as_os_str() == "script/rl_rust/data" || path.as_os_str() == "script\\rl_rust\\data" {
        PathBuf::from("data")
    } else {
        path
    };
    if rel.is_absolute() {
        rel
    } else {
        manifest.join(rel)
    }
}

fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::from_default_env().add_directive("formation_rl=info".parse()?))
        .init();

    let args = Args::parse();
    let total_steps = if args.max_steps == 0 {
        None
    } else {
        Some(args.max_steps)
    };

    let cfg = TrainConfig {
        cores: args.cores,
        self_play_games: args.self_play_games,
        eval_every_l5: args.eval_every_l5,
        eval_every_l3: args.eval_every_l3,
        eval_games: args.eval_games,
        mcts_sims: args.mcts_sims,
        learning_rate: args.lr,
        data_dir: resolve_data_dir(args.data_dir),
        resume: args.resume && !args.fresh,
        imitate: args.imitate,
        imitate_depth: args.imitate_depth,
        imitate_games: args.imitate_games,
        total_steps,
        python: args.python,
        curriculum_rate: args.curriculum,
        eval_mcts_sims: args.eval_mcts_sims,
        fresh: args.fresh,
        value_lr: args.value_lr,
        use_az_mcts: args.az_mcts,
        checkpoint_every: args.checkpoint_every,
        training_phase_mode: TrainingPhaseMode::from_cli(&args.training_phase),
        phase2_win_threshold: args.phase2_win_threshold,
        phase_transition_games: args.phase_transition_games,
    };

    let mut trainer = Trainer::new(cfg)?;
    trainer.run()
}
