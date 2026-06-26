//! CLI entraînement RL 4mation.

use std::path::PathBuf;

use anyhow::Result;
use clap::Parser;
use formation_rl::{TrainConfig, Trainer};
use tracing_subscriber::EnvFilter;

#[derive(Parser, Debug)]
#[command(
    name = "train",
    about = "Entraînement RL 4mation (self-play parallèle, policy linéaire + MCTS-lite)"
)]
struct Args {
    /// Nombre de workers rayon (cœurs physiques recommandés)
    #[arg(long, default_value = "16")]
    cores: usize,

    /// Parties self-play par batch
    #[arg(long, default_value = "1000")]
    self_play_games: usize,

    /// Évaluer vs Minimax level_5 tous les N coups cumulés
    #[arg(long, default_value = "5000")]
    eval_every: u64,

    /// Nombre de parties d'évaluation vs level_5
    #[arg(long, default_value = "20")]
    eval_games: usize,

    /// Simulations MCTS par coup (0 = policy directe)
    #[arg(long, default_value = "8")]
    mcts_sims: u32,

    /// Taux d'apprentissage REINFORCE
    #[arg(long, default_value = "0.02")]
    lr: f64,

    /// Reprendre depuis le dernier checkpoint
    #[arg(long)]
    resume: bool,

    /// Bootstrap via Minimax Python (depth 6–8)
    #[arg(long, default_value_t = true)]
    imitate: bool,

    /// Ignorer le bootstrap Minimax Python (heuristique Rust uniquement)
    #[arg(long, action = clap::ArgAction::SetTrue)]
    no_imitate: bool,

    #[arg(long, default_value = "7")]
    imitate_depth: u8,

    #[arg(long, default_value = "300")]
    imitate_games: usize,

    /// Dossier données (checkpoints, métriques)
    #[arg(long, default_value = "script/rl_rust/data")]
    data_dir: PathBuf,

    /// Arrêt automatique après N steps (0 = infini)
    #[arg(long, default_value = "0")]
    max_steps: u64,

    /// Exécutable Python (Windows: py)
    #[arg(long, default_value = "py")]
    python: String,
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
        eval_every: args.eval_every,
        eval_games: args.eval_games,
        mcts_sims: args.mcts_sims,
        learning_rate: args.lr,
        data_dir: args.data_dir,
        resume: args.resume,
        imitate: args.imitate && !args.no_imitate,
        imitate_depth: args.imitate_depth,
        imitate_games: args.imitate_games,
        total_steps,
        python: args.python,
    };

    let mut trainer = Trainer::new(cfg)?;
    trainer.run()
}
