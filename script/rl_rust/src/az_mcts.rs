//! AlphaZero-lite : MCTS racine + prior réseau + value head.

use formation_worker::game::Move;
use rand::Rng;

use crate::game_session::GameSession;
use crate::policy::PolicyNet;

const C_PUCT: f64 = 1.4;
const ROLLOUT_DEPTH: u32 = 2;
/// Arrêt anticipé si un enfant domine après au moins 25 % des simulations.
const EARLY_STOP_MIN_FRAC: f64 = 0.25;
const EARLY_STOP_VISIT_FRAC: f64 = 0.62;

struct ChildStat {
    visits: u32,
    value_sum: f64,
    prior: f64,
}

pub struct MctsAz {
    pub sims: u32,
}

impl Default for MctsAz {
    fn default() -> Self {
        Self { sims: 36 }
    }
}

impl MctsAz {
    pub fn choose_move(
        &self,
        policy: &PolicyNet,
        session: &GameSession,
        rng: &mut impl Rng,
    ) -> Option<Move> {
        let moves = session.legal_moves();
        if moves.is_empty() {
            return None;
        }
        if moves.len() == 1 {
            return Some(moves[0]);
        }
        if self.sims == 0 {
            return policy.best_move(
                &session.board,
                &moves,
                session.current_player,
                session.last_move,
            );
        }

        let root_player = session.current_player;
        let priors = policy_move_priors(policy, session, &moves);
        let mut children: Vec<ChildStat> = priors
            .into_iter()
            .map(|p| ChildStat {
                visits: 0,
                value_sum: 0.0,
                prior: p,
            })
            .collect();

        let max_sims = self.sims.max(1);
        let early_min = ((max_sims as f64) * EARLY_STOP_MIN_FRAC).ceil() as u32;
        for sim_i in 0..max_sims {
            let total_visits: u32 = children.iter().map(|c| c.visits).sum();
            let idx = children
                .iter()
                .enumerate()
                .max_by(|a, b| {
                    let qa = if a.1.visits == 0 {
                        f64::INFINITY
                    } else {
                        a.1.value_sum / a.1.visits as f64
                    };
                    let qb = if b.1.visits == 0 {
                        f64::INFINITY
                    } else {
                        b.1.value_sum / b.1.visits as f64
                    };
                    let ua = qa
                        + C_PUCT
                            * a.1.prior
                            * ((total_visits + 1) as f64).sqrt()
                            / (1.0 + a.1.visits as f64);
                    let ub = qb
                        + C_PUCT
                            * b.1.prior
                            * ((total_visits + 1) as f64).sqrt()
                            / (1.0 + b.1.visits as f64);
                    ua.partial_cmp(&ub).unwrap()
                })
                .map(|(i, _)| i)
                .unwrap_or(0);

            let mut sim = session.clone();
            sim.apply(moves[idx]);
            let v = evaluate_leaf(policy, &sim, root_player, rng);
            children[idx].visits += 1;
            children[idx].value_sum += v;

            if sim_i + 1 >= early_min {
                let total: u32 = children.iter().map(|c| c.visits).sum();
                if total > 0 {
                    let max_v = children.iter().map(|c| c.visits).max().unwrap_or(0);
                    if max_v as f64 / total as f64 >= EARLY_STOP_VISIT_FRAC {
                        break;
                    }
                }
            }
        }

        if rng.gen::<f64>() < 0.08 {
            let total: u32 = children.iter().map(|c| c.visits).sum();
            if total > 0 {
                let r = rng.gen_range(0..total);
                let mut acc = 0u32;
                for (i, c) in children.iter().enumerate() {
                    acc += c.visits;
                    if r < acc {
                        return Some(moves[i]);
                    }
                }
            }
        }

        let best = children
            .iter()
            .enumerate()
            .max_by_key(|(_, c)| c.visits)
            .map(|(i, _)| i)
            .unwrap_or(0);
        Some(moves[best])
    }
}

fn evaluate_leaf(
    policy: &PolicyNet,
    session: &GameSession,
    root_player: i8,
    rng: &mut impl Rng,
) -> f64 {
    if session.is_terminal() {
        return session.terminal_reward(root_player);
    }

    let mut sim = session.clone();
    for _ in 0..ROLLOUT_DEPTH {
        if sim.is_terminal() {
            return sim.terminal_reward(root_player);
        }
        let legal = sim.legal_moves();
        if legal.is_empty() {
            break;
        }
        let mv = policy
            .sample_move(
                rng,
                &sim.board,
                &legal,
                sim.current_player,
                sim.last_move,
                0.7,
            )
            .unwrap_or(legal[0]);
        sim.apply(mv);
    }

    if sim.is_terminal() {
        sim.terminal_reward(root_player)
    } else {
        policy.value(&sim, root_player)
    }
}

fn policy_move_priors(policy: &PolicyNet, session: &GameSession, moves: &[Move]) -> Vec<f64> {
    let logits = policy.logits(
        &session.board,
        moves,
        session.current_player,
        session.last_move,
    );
    if logits.is_empty() {
        let u = 1.0 / moves.len() as f64;
        return vec![u; moves.len()];
    }
    let max_l = logits.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    let exp: Vec<f64> = logits.iter().map(|l| (l - max_l).exp()).collect();
    let sum: f64 = exp.iter().sum::<f64>().max(1e-9);
    exp.iter().map(|e| e / sum).collect()
}
