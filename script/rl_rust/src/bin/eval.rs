//! Évaluation standalone d'un checkpoint vs level_5.

use std::path::PathBuf;

use anyhow::{Context, Result};
use clap::Parser;
use formation_rl::eval::{evaluate_vs_minimax, resolve_paths, EvalConfig, MinimaxBridge};
use formation_rl::policy::PolicyNet;
use tracing_subscriber::EnvFilter;

#[derive(Parser, Debug)]
#[command(name = "eval", about = "Évalue un checkpoint RL vs Minimax level_5")]
struct Args {
    /// Checkpoint JSON (policy linéaire)
    #[arg(long, default_value = "checkpoints/latest.json")]
    checkpoint: PathBuf,

    #[arg(long, default_value = "20")]
    games: usize,

    #[arg(long, default_value = "12")]
    mcts_sims: u32,

    #[arg(long, default_value = "level_5")]
    bot: String,

    #[arg(long, default_value = "py")]
    python: String,

    #[arg(long, default_value = "data")]
    data_dir: PathBuf,
}

fn resolve_data_dir(path: PathBuf) -> PathBuf {
    let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    if path.is_absolute() {
        path
    } else {
        manifest.join(path)
    }
}

fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::from_default_env().add_directive("formation_rl=info".parse()?))
        .init();

    let args = Args::parse();
    let data_dir = resolve_data_dir(args.data_dir);
    let ckpt = if args.checkpoint.is_absolute() {
        args.checkpoint
    } else {
        data_dir.join(&args.checkpoint)
    };

    let policy = PolicyNet::load(&ckpt)
        .with_context(|| format!("chargement checkpoint {ckpt:?}"))?;

    let (script_path, project_root) = resolve_paths(&data_dir);
    let bot = args.bot.clone();
    let eval_cfg = EvalConfig {
        games: args.games,
        mcts_sims: args.mcts_sims,
        python: args.python,
        script_path,
        project_root,
        bot_id: bot.clone(),
        ..EvalConfig::default()
    };

    let mut bridge = MinimaxBridge::spawn(&eval_cfg)?;
    let result = evaluate_vs_minimax(&policy, &eval_cfg, &mut bridge, 12345)?;

    println!("Checkpoint: {}", ckpt.display());
    println!(
        "vs {} — {} parties: {} victoires RL, {} défaites, {} nulles ({:.1} % win)",
        bot,
        result.games,
        result.rl_wins,
        result.bot_wins,
        result.draws,
        result.win_rate * 100.0
    );

    Ok(())
}
