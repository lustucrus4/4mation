//! Bootstrap par imitation Minimax (subprocess Python depth 6–8).

use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Command, Stdio};

use anyhow::{Context, Result};
use rand::rngs::StdRng;
use rand::{Rng, SeedableRng};
use serde::Deserialize;

use crate::features::move_features;
use crate::game_session::GameSession;
use crate::policy::{LinearPolicy, TrajectoryStep};

#[derive(Deserialize)]
struct ImitationSample {
    features: Vec<f64>,
    target_move_idx: usize,
    legal_count: usize,
}

pub struct ImitationConfig {
    pub games: usize,
    pub depth: u8,
    pub python: String,
    pub script_path: PathBuf,
    pub project_root: PathBuf,
}

pub fn run_imitation_bootstrap(policy: &mut LinearPolicy, cfg: &ImitationConfig) -> Result<usize> {
    let script = if cfg.script_path.is_absolute() {
        cfg.script_path.clone()
    } else {
        cfg.project_root.join(&cfg.script_path)
    };

    let mut child = Command::new(&cfg.python)
        .arg("-3")
        .arg("-u")
        .arg(&script)
        .arg("imitate")
        .arg("--games")
        .arg(cfg.games.to_string())
        .arg("--depth")
        .arg(cfg.depth.to_string())
        .current_dir(&cfg.project_root)
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit())
        .spawn()
        .with_context(|| "lancement imitate")?;

    let stdout = child.stdout.take().context("stdout imitate")?;
    let reader = BufReader::new(stdout);
    let mut samples = 0usize;
    let lr = 0.05;

    for line in reader.lines() {
        let line = line?;
        if line.trim().is_empty() {
            continue;
        }
        let sample: ImitationSample = match serde_json::from_str(&line) {
            Ok(s) => s,
            Err(_) => continue,
        };
        if sample.features.len() != crate::features::FEATURE_DIM {
            continue;
        }
        let mut feats = [0.0; crate::features::FEATURE_DIM];
        for (i, v) in sample.features.iter().enumerate().take(feats.len()) {
            feats[i] = *v;
        }
        let reward = 1.0;
        let step = TrajectoryStep {
            features: feats,
            reward,
            player: 1,
        };
        crate::policy::reinforce_update(policy, std::slice::from_ref(&step), lr);
        samples += 1;
    }

    let status = child.wait()?;
    if !status.success() {
        anyhow::bail!("imitate terminé avec code {:?}", status.code());
    }
    Ok(samples)
}

/// Heuristique Rust rapide si Python indisponible.
pub fn heuristic_bootstrap(policy: &mut LinearPolicy, games: usize, seed: u64) -> usize {
    use formation_worker::game::is_winning_move;

    let mut rng = StdRng::seed_from_u64(seed);
    let mut samples = 0usize;

    for g in 0..games {
        let mut session = GameSession::new();
        while !session.is_terminal() && session.move_count < 80 {
            let player = session.current_player;
            let moves = session.legal_moves();
            if moves.is_empty() {
                break;
            }
            let opponent = 3 - player;
            let chosen = moves
                .iter()
                .find(|&&mv| is_winning_move(&session.board, mv, player))
                .copied()
                .or_else(|| {
                    moves
                        .iter()
                        .find(|&&mv| is_winning_move(&session.board, mv, opponent))
                        .copied()
                })
                .unwrap_or_else(|| {
                    let center = 3usize;
                    *moves
                        .iter()
                        .min_by_key(|&&(r, c)| {
                            ((r as i32 - center as i32).abs() + (c as i32 - center as i32).abs())
                                as u32
                        })
                        .unwrap_or(&moves[rng.gen_range(0..moves.len())])
                });

            let feats = move_features(&session.board, chosen, player, session.last_move);
            let step = TrajectoryStep {
                features: feats,
                reward: 1.0,
                player,
            };
            crate::policy::reinforce_update(policy, std::slice::from_ref(&step), 0.08);
            samples += 1;
            session.apply(chosen);

            if g % 2 == 1 {
                let opp_moves = session.legal_moves();
                if opp_moves.is_empty() {
                    break;
                }
                let om = opp_moves[rng.gen_range(0..opp_moves.len())];
                session.apply(om);
            }
        }
    }
    samples
}
