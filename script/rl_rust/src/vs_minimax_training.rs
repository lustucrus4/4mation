//! Entraînement par parties vs Minimax Python (level_5) — phase 1 avant self-play.

use anyhow::Result;
use formation_worker::game::Move;
use rand::rngs::StdRng;
use rand::{Rng, SeedableRng};
use rayon::prelude::*;

use crate::eval::{EvalConfig, MinimaxBridge};
use crate::features::{move_features, position_features};
use crate::game_session::GameSession;
use crate::policy::{PolicyNet, TrajectoryStep};
use crate::self_play::{policy_move, GameResult, SelfPlayConfig, SelfPlayStats};

fn shaped_step_reward(feats: &[f64; 12], terminal: f64) -> f64 {
    terminal + feats[0] * 0.4 + feats[1] * 0.25 + feats[8] * 0.15
}

pub fn play_vs_minimax_game(
    policy: &PolicyNet,
    self_cfg: &SelfPlayConfig,
    eval_cfg: &EvalConfig,
    bridge: &mut MinimaxBridge,
    seed: u64,
) -> Result<GameResult> {
    let mut rng = StdRng::seed_from_u64(seed);
    let mut session = GameSession::new();
    let mut trajectory = Vec::new();
    let rl_player: i8 = if rng.gen_bool(0.5) { 1 } else { 2 };

    while !session.is_terminal() && session.move_count < self_cfg.max_moves {
        let player = session.current_player;
        let moves = session.legal_moves();
        if moves.is_empty() {
            break;
        }

        let chosen: Option<Move> = if player == rl_player {
            policy_move(policy, &session, &mut rng, self_cfg)
        } else {
            bridge.choose_move(eval_cfg, &session)?
        };

        let Some(chosen) = chosen else { break };

        if player == rl_player {
            let feats = move_features(&session.board, chosen, player, session.last_move);
            let pos = position_features(&session.board, player, session.last_move);
            trajectory.push(TrajectoryStep {
                features: feats,
                pos_features: pos,
                reward: 0.0,
                player,
            });
        }
        session.apply(chosen);
    }

    for step in &mut trajectory {
        step.reward = shaped_step_reward(&step.features, session.terminal_reward(step.player));
    }

    Ok(GameResult {
        trajectory,
        winner: session.winner(),
        moves: session.move_count,
        rl_player: Some(rl_player),
    })
}

/// Batch parallèle : un daemon Python par worker Rayon.
pub fn batch_vs_minimax(
    policy: &PolicyNet,
    self_cfg: &SelfPlayConfig,
    eval_cfg: &EvalConfig,
    games: usize,
    base_seed: u64,
) -> Result<(Vec<TrajectoryStep>, SelfPlayStats)> {
    let results: Vec<Result<GameResult>> = (0..games)
        .into_par_iter()
        .map_init(
            || MinimaxBridge::spawn(eval_cfg).expect("daemon Minimax worker"),
            |bridge, i| play_vs_minimax_game(policy, self_cfg, eval_cfg, bridge, base_seed.wrapping_add(i as u64)),
        )
        .collect();

    let mut all_steps = Vec::new();
    let mut rl_wins = 0u32;
    let mut rl_losses = 0u32;
    let mut draws = 0u32;
    let mut total_moves = 0u64;
    let mut played = 0usize;

    for r in results {
        let r = r?;
        played += 1;
        total_moves += r.moves as u64;
        if let Some(rl) = r.rl_player {
            match r.winner {
                Some(w) if w == rl => rl_wins += 1,
                Some(_) => rl_losses += 1,
                None => draws += 1,
            }
        }
        all_steps.extend(r.trajectory);
    }

    let stats = SelfPlayStats {
        games: played,
        p1_wins: rl_wins,
        p2_wins: rl_losses,
        draws,
        avg_moves: if played > 0 {
            total_moves as f64 / played as f64
        } else {
            0.0
        },
        rl_win_rate: if played > 0 {
            rl_wins as f64 / played as f64
        } else {
            0.0
        },
    };
    Ok((all_steps, stats))
}
