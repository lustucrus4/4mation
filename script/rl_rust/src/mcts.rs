//! MCTS-lite : évalue chaque coup racine via rollouts policy + aléatoire.

use formation_worker::game::{frontier_moves, Board, Move};
use rand::Rng;

use crate::game_session::GameSession;
use crate::policy::LinearPolicy;

pub struct MctsLite {
    pub sims_per_move: u32,
}

impl Default for MctsLite {
    fn default() -> Self {
        Self { sims_per_move: 8 }
    }
}

impl MctsLite {
    pub fn choose_move(
        &self,
        policy: &LinearPolicy,
        session: &GameSession,
        rng: &mut impl Rng,
    ) -> Option<Move> {
        let moves = session.legal_moves();
        if moves.is_empty() {
            return None;
        }
        if self.sims_per_move == 0 {
            return policy.sample_move(
                rng,
                &session.board,
                &moves,
                session.current_player,
                session.last_move,
                0.85,
            );
        }
        if moves.len() == 1 {
            return Some(moves[0]);
        }

        let root = session.current_player;
        let mut best_mv = moves[0];
        let mut best_score = f64::NEG_INFINITY;

        for &mv in &moves {
            let mut wins = 0.0;
            let sims = self.sims_per_move.max(1);
            for _ in 0..sims {
                let mut sim = session.clone();
                sim.apply(mv);
                wins += rollout_value(&mut sim, policy, root, rng);
            }
            let score = wins / sims as f64;
            if score > best_score {
                best_score = score;
                best_mv = mv;
            }
        }
        Some(best_mv)
    }
}

fn rollout_value(
    session: &mut GameSession,
    policy: &LinearPolicy,
    root: i8,
    rng: &mut impl Rng,
) -> f64 {
    while !session.is_terminal() {
        let moves = session.legal_moves();
        if moves.is_empty() {
            break;
        }
        let mv = if rng.gen::<f64>() < 0.7 {
            policy
                .sample_move(
                    rng,
                    &session.board,
                    &moves,
                    session.current_player,
                    session.last_move,
                    1.0,
                )
                .unwrap_or(moves[0])
        } else {
            moves[rng.gen_range(0..moves.len())]
        };
        session.apply(mv);
        if session.move_count > 90 {
            break;
        }
    }
    session.terminal_reward(root)
}

#[allow(dead_code)]
pub fn policy_move(
    policy: &LinearPolicy,
    board: &Board,
    player: i8,
    last_move: Option<Move>,
    rng: &mut impl Rng,
) -> Option<Move> {
    let moves = frontier_moves(board, last_move, player);
    policy.sample_move(rng, board, &moves, player, last_move, 0.9)
}
