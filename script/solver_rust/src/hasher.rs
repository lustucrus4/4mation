//! Hash Zobrist — clés identiques à `position_hasher.py` (seed Python 42, clés pré-calculées).

use crate::game::{Board, Move, BOARD_SIZE};
use std::sync::atomic::{AtomicBool, Ordering};

include!("zobrist_keys.inc");

static SYMMETRY_ENABLED: AtomicBool = AtomicBool::new(true);

pub struct PositionHasher;

impl PositionHasher {
    pub fn set_symmetry_enabled(enabled: bool) {
        SYMMETRY_ENABLED.store(enabled, Ordering::Relaxed);
    }

    pub fn symmetry_enabled() -> bool {
        SYMMETRY_ENABLED.load(Ordering::Relaxed)
    }
    #[inline]
    fn cell_index(row: usize, col: usize, player: i8) -> usize {
        (row * BOARD_SIZE + col) * 3 + player as usize
    }

    pub fn zobrist_int(board: &Board, current_player: i8, last_move: Option<Move>) -> u64 {
        Self::raw_zobrist_int(board, current_player, last_move)
    }

    /// Hash sans canonicalisation (compat tests / migration).
    pub fn raw_zobrist_int(board: &Board, current_player: i8, last_move: Option<Move>) -> u64 {
        let mut h = 0u64;
        for r in 0..BOARD_SIZE {
            for c in 0..BOARD_SIZE {
                let player = board[r][c];
                h ^= ZOBRIST_CELL[Self::cell_index(r, c, player)];
            }
        }
        h ^= if current_player == 1 {
            ZOBRIST_P1
        } else {
            ZOBRIST_P2
        };
        if let Some((lr, lc)) = last_move {
            h ^= ((lr * BOARD_SIZE + lc) as u64) << 32;
        }
        h
    }

    pub fn hash_key(board: &Board, current_player: i8, last_move: Option<Move>) -> String {
        if Self::symmetry_enabled() {
            Self::canonical_hash_key(board, current_player, last_move)
        } else {
            Self::raw_hash_key(board, current_player, last_move)
        }
    }

    pub fn raw_hash_key(board: &Board, current_player: i8, last_move: Option<Move>) -> String {
        format!("{:016x}", Self::raw_zobrist_int(board, current_player, last_move))
    }

    /// Forme canonique (symétries D₄) puis clé hex.
    pub fn canonical_hash_key(board: &Board, current_player: i8, last_move: Option<Move>) -> String {
        let (b, p, lm) = crate::symmetry::canonical_position(board, current_player, last_move);
        Self::raw_hash_key(&b, p, lm)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::game::BOARD_SIZE;

    #[test]
    fn matches_python_vectors() {
        let board = [[0i8; BOARD_SIZE]; BOARD_SIZE];
        assert_eq!(
            PositionHasher::raw_hash_key(&board, 1, None),
            "34cbd58d62f1894e"
        );
        let mut b2 = board;
        b2[1][1] = 1;
        assert_eq!(
            PositionHasher::raw_hash_key(&b2, 2, Some((1, 1))),
            "eb8d073c48730da1"
        );
    }
}
