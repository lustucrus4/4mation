//! Self-play parallèle avec collecte de trajectoires REINFORCE.

use formation_worker::game::Move;
use rand::rngs::StdRng;
use rand::SeedableRng;

use crate::features::move_features;
use crate::game_session::GameSession;
use crate::mcts::MctsLite;
use crate::policy::{LinearPolicy, TrajectoryStep};

pub struct SelfPlayConfig {
    pub mcts_sims: u32,
    pub temperature: f64,
    pub max_moves: u32,
}

impl Default for SelfPlayConfig {
    fn default() -> Self {
        Self {
            mcts_sims: 8,
            temperature: 0.9,
            max_moves: 100,
        }
    }
}

pub struct GameResult {
    pub trajectory: Vec<TrajectoryStep>,
    pub winner: Option<i8>,
    pub moves: u32,
}

pub fn play_self_game(
    policy: &LinearPolicy,
    cfg: &SelfPlayConfig,
    seed: u64,
) -> GameResult {
    let mut rng = StdRng::seed_from_u64(seed);
    let mcts = MctsLite {
        sims_per_move: cfg.mcts_sims,
    };
    let mut session = GameSession::new();
    let mut trajectory = Vec::new();

    while !session.is_terminal() && session.move_count < cfg.max_moves {
        let player = session.current_player;
        let moves = session.legal_moves();
        if moves.is_empty() {
            break;
        }

        let mv = if cfg.mcts_sims > 0 {
            mcts.choose_move(policy, &session, &mut rng)
        } else {
            policy.sample_move(
                &mut rng,
                &session.board,
                &moves,
                player,
                session.last_move,
                cfg.temperature,
            )
        };

        let Some(chosen) = mv else { break };

        let feats = move_features(
            &session.board,
            chosen,
            player,
            session.last_move,
        );
        trajectory.push(TrajectoryStep {
            features: feats,
            reward: 0.0,
            player,
        });

        session.apply(chosen);
    }

    for step in &mut trajectory {
        step.reward = session.terminal_reward(step.player);
    }

    GameResult {
        trajectory,
        winner: session.winner(),
        moves: session.move_count,
    }
}

pub fn batch_self_play(
    policy: &LinearPolicy,
    cfg: &SelfPlayConfig,
    games: usize,
    base_seed: u64,
) -> (Vec<TrajectoryStep>, SelfPlayStats) {
    use rayon::prelude::*;

    let results: Vec<GameResult> = (0..games)
        .into_par_iter()
        .map(|i| play_self_game(policy, cfg, base_seed.wrapping_add(i as u64)))
        .collect();

    let mut all_steps = Vec::new();
    let mut p1_wins = 0u32;
    let mut p2_wins = 0u32;
    let mut draws = 0u32;
    let mut total_moves = 0u64;

    for r in results {
        total_moves += r.moves as u64;
        match r.winner {
            Some(1) => p1_wins += 1,
            Some(2) => p2_wins += 1,
            _ => draws += 1,
        }
        all_steps.extend(r.trajectory);
    }

    let stats = SelfPlayStats {
        games,
        p1_wins,
        p2_wins,
        draws,
        avg_moves: if games > 0 {
            total_moves as f64 / games as f64
        } else {
            0.0
        },
    };
    (all_steps, stats)
}

#[derive(Clone, Debug)]
pub struct SelfPlayStats {
    pub games: usize,
    pub p1_wins: u32,
    pub p2_wins: u32,
    pub draws: u32,
    pub avg_moves: f64,
}

impl SelfPlayStats {
    pub fn win_rate_p1(&self) -> f64 {
        if self.games == 0 {
            return 0.0;
        }
        self.p1_wins as f64 / self.games as f64
    }
}

#[allow(dead_code)]
fn mirror_move(mv: Move) -> Move {
    mv
}
