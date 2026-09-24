//! Adversaires Rust pour curriculum (heuristique + minimax alpha-beta).

use formation_worker::game::{is_winning_move, Move, BOARD_SIZE};
use rand::Rng;

use crate::game_session::GameSession;

/// Coup heuristique rapide : gagner > bloquer > centre.
pub fn heuristic_move(session: &GameSession, rng: &mut impl Rng) -> Option<Move> {
    let player = session.current_player;
    let opponent = 3 - player;
    let moves = session.legal_moves();
    if moves.is_empty() {
        return None;
    }

    if let Some(&mv) = moves
        .iter()
        .find(|&&m| is_winning_move(&session.board, m, player))
    {
        return Some(mv);
    }
    if let Some(&mv) = moves
        .iter()
        .find(|&&m| is_winning_move(&session.board, m, opponent))
    {
        return Some(mv);
    }

    let center = 3usize;
    Some(
        *moves
            .iter()
            .min_by_key(|&&(r, c)| {
                ((r as i32 - center as i32).abs() + (c as i32 - center as i32).abs()) as u32
            })
            .unwrap_or(&moves[rng.gen_range(0..moves.len())]),
    )
}

fn eval_board(session: &GameSession, perspective: i8) -> i32 {
    if let Some(w) = session.winner() {
        return if w == perspective { 10_000 } else { -10_000 };
    }
    let opponent = 3 - perspective;
    let mut score = 0i32;
    let moves = session.legal_moves();
    for &mv in &moves {
        if is_winning_move(&session.board, mv, perspective) {
            score += 500;
        }
        if is_winning_move(&session.board, mv, opponent) {
            score -= 400;
        }
    }
    let center = 3i32;
    for r in 0..BOARD_SIZE {
        for c in 0..BOARD_SIZE {
            let p = session.board[r][c];
            if p == perspective {
                score += 2 - ((r as i32 - center).abs() + (c as i32 - center).abs());
            } else if p == opponent {
                score -= 1;
            }
        }
    }
    score
}

fn alpha_beta(
    session: &GameSession,
    depth: u8,
    root: i8,
    alpha: i32,
    beta: i32,
    maximizing: bool,
) -> i32 {
    if depth == 0 || session.is_terminal() {
        return eval_board(session, root);
    }
    let moves = session.legal_moves();
    if moves.is_empty() {
        return eval_board(session, root);
    }

    let mut a = alpha;
    let mut b = beta;
    if maximizing {
        let mut best = i32::MIN;
        for &mv in &moves {
            let mut child = session.clone();
            child.apply(mv);
            let val = alpha_beta(&child, depth - 1, root, a, b, false);
            best = best.max(val);
            a = a.max(val);
            if b <= a {
                break;
            }
        }
        best
    } else {
        let mut best = i32::MAX;
        for &mv in &moves {
            let mut child = session.clone();
            child.apply(mv);
            let val = alpha_beta(&child, depth - 1, root, a, b, true);
            best = best.min(val);
            b = b.min(val);
            if b <= a {
                break;
            }
        }
        best
    }
}

/// Minimax alpha-beta en Rust (depth 2–5) — adversaire curriculum sans Python.
pub fn minimax_move(session: &GameSession, depth: u8) -> Option<Move> {
    let moves = session.legal_moves();
    if moves.is_empty() {
        return None;
    }
    if moves.len() == 1 {
        return Some(moves[0]);
    }

    let root = session.current_player;
    let mut best_mv = moves[0];
    let mut best_score = i32::MIN;
    let mut alpha = i32::MIN;
    let beta = i32::MAX;

    for &mv in &moves {
        let mut child = session.clone();
        child.apply(mv);
        let score = alpha_beta(&child, depth.saturating_sub(1), root, alpha, beta, false);
        if score > best_score {
            best_score = score;
            best_mv = mv;
        }
        alpha = alpha.max(score);
    }
    Some(best_mv)
}

#[derive(Clone, Copy, Debug)]
pub enum CurriculumOpponent {
    Heuristic,
    MinimaxD3,
    MinimaxD4,
    MinimaxD5,
}

impl CurriculumOpponent {
    pub fn random(rng: &mut impl Rng) -> Self {
        match rng.gen_range(0..4) {
            0 => Self::Heuristic,
            1 => Self::MinimaxD3,
            2 => Self::MinimaxD4,
            _ => Self::MinimaxD5,
        }
    }

    pub fn choose(&self, session: &GameSession, rng: &mut impl Rng) -> Option<Move> {
        match self {
            Self::Heuristic => heuristic_move(session, rng),
            Self::MinimaxD3 => minimax_move(session, 3),
            Self::MinimaxD4 => minimax_move(session, 4),
            Self::MinimaxD5 => minimax_move(session, 5),
        }
    }
}
