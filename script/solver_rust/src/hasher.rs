//! Hash Zobrist — clés identiques à `position_hasher.py` (seed Python 42, clés pré-calculées).

use crate::game::{Board, Move, BOARD_SIZE};

include!("zobrist_keys.inc");

pub struct PositionHasher;

impl PositionHasher {
    #[inline]
    fn cell_index(row: usize, col: usize, player: i8) -> usize {
        (row * BOARD_SIZE + col) * 3 + player as usize
    }

    pub fn zobrist_int(board: &Board, current_player: i8, last_move: Option<Move>) -> u64 {
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
        format!("{:016x}", Self::zobrist_int(board, current_player, last_move))
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
            PositionHasher::hash_key(&board, 1, None),
            "34cbd58d62f1894e"
        );
        let mut b2 = board;
        b2[1][1] = 1;
        assert_eq!(
            PositionHasher::hash_key(&b2, 2, Some((1, 1))),
            "eb8d073c48730da1"
        );
    }
}
