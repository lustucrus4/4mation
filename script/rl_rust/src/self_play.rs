//! Self-play parallèle + curriculum + AlphaZero-lite MCTS.

use formation_worker::game::Move;
use rand::rngs::StdRng;
use rand::Rng;
use rand::SeedableRng;

use crate::az_mcts::MctsAz;
use crate::features::{move_features, position_features};
use crate::game_session::GameSession;
use crate::mcts::MctsLite;
use crate::opponent::CurriculumOpponent;
use crate::policy::{PolicyNet, TrajectoryStep};

pub struct SelfPlayConfig {
    pub mcts_sims: u32,
    pub temperature: f64,
    pub max_moves: u32,
    pub curriculum_rate: f64,
    pub use_az_mcts: bool,
}

impl Default for SelfPlayConfig {
    fn default() -> Self {
        Self {
            mcts_sims: 36,
            temperature: 0.85,
            max_moves: 120,
            curriculum_rate: 0.45,
            use_az_mcts: true,
        }
    }
}

pub struct GameResult {
    pub trajectory: Vec<TrajectoryStep>,
    pub winner: Option<i8>,
    pub moves: u32,
    /// Joueur RL (1 ou 2) — renseigné en parties vs adversaire externe.
    pub rl_player: Option<i8>,
}

fn shaped_step_reward(feats: &[f64; 12], terminal: f64) -> f64 {
    terminal + feats[0] * 0.4 + feats[1] * 0.25 + feats[8] * 0.15
}

pub(crate) fn policy_move(
    policy: &PolicyNet,
    session: &GameSession,
    rng: &mut StdRng,
    cfg: &SelfPlayConfig,
) -> Option<Move> {
    if cfg.use_az_mcts && cfg.mcts_sims > 0 {
        let az = MctsAz {
            sims: cfg.mcts_sims,
        };
        return az.choose_move(policy, session, rng);
    }
    if cfg.mcts_sims > 0 {
        let mcts = MctsLite {
            sims_per_move: cfg.mcts_sims,
        };
        return mcts.choose_move(policy, session, rng);
    }
    policy.sample_move(
        rng,
        &session.board,
        &session.legal_moves(),
        session.current_player,
        session.last_move,
        cfg.temperature,
    )
}

pub fn play_self_game(
    policy: &PolicyNet,
    cfg: &SelfPlayConfig,
    seed: u64,
) -> GameResult {
    let mut rng = StdRng::seed_from_u64(seed);

    let vs_opponent = rng.gen::<f64>() < cfg.curriculum_rate.clamp(0.0, 1.0);
    if vs_opponent {
        return play_vs_opponent(policy, cfg, &mut rng);
    }

    let mut session = GameSession::new();
    let mut trajectory = Vec::new();

    while !session.is_terminal() && session.move_count < cfg.max_moves {
        let player = session.current_player;
        let moves = session.legal_moves();
        if moves.is_empty() {
            break;
        }

        let Some(chosen) = policy_move(policy, &session, &mut rng, cfg) else {
            break;
        };

        let feats = move_features(&session.board, chosen, player, session.last_move);
        let pos = position_features(&session.board, player, session.last_move);
        trajectory.push(TrajectoryStep {
            features: feats,
            pos_features: pos,
            reward: 0.0,
            player,
        });
        session.apply(chosen);
    }

    for step in &mut trajectory {
        step.reward = shaped_step_reward(&step.features, session.terminal_reward(step.player));
    }

    GameResult {
        trajectory,
        winner: session.winner(),
        moves: session.move_count,
        rl_player: None,
    }
}

fn play_vs_opponent(
    policy: &PolicyNet,
    cfg: &SelfPlayConfig,
    rng: &mut StdRng,
) -> GameResult {
    let mut session = GameSession::new();
    let mut trajectory = Vec::new();
    let rl_player: i8 = if rng.gen_bool(0.5) { 1 } else { 2 };
    let opponent = CurriculumOpponent::random(rng);

    while !session.is_terminal() && session.move_count < cfg.max_moves {
        let player = session.current_player;
        let moves = session.legal_moves();
        if moves.is_empty() {
            break;
        }

        let chosen = if player == rl_player {
            policy_move(policy, &session, rng, cfg)
        } else {
            opponent.choose(&session, rng)
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

    GameResult {
        trajectory,
        winner: session.winner(),
        moves: session.move_count,
        rl_player: Some(rl_player),
    }
}

pub fn batch_self_play(
    policy: &PolicyNet,
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
        rl_win_rate: p1_wins as f64 / games.max(1) as f64,
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
    /// Victoires RL en parties vs adversaire (sinon = win_rate_p1).
    pub rl_win_rate: f64,
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
