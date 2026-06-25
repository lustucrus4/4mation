//! Symétries du plateau 7×7 (groupe diédral D₄ : 4 rotations × miroir).
//!
//! Forme canonique = représentant de hash Zobrist minimal parmi les 8 images.

use crate::game::{Board, Move, BOARD_SIZE};

const N: usize = BOARD_SIZE;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum Symmetry {
    Id = 0,
    R90 = 1,
    R180 = 2,
    R270 = 3,
    FlipH = 4,
    FlipHR90 = 5,
    FlipHR180 = 6,
    FlipHR270 = 7,
}

pub const ALL_SYMMETRIES: [Symmetry; 8] = [
    Symmetry::Id,
    Symmetry::R90,
    Symmetry::R180,
    Symmetry::R270,
    Symmetry::FlipH,
    Symmetry::FlipHR90,
    Symmetry::FlipHR180,
    Symmetry::FlipHR270,
];

fn rot90_cell(r: usize, c: usize) -> (usize, usize) {
    (c, N - 1 - r)
}

fn rot180_cell(r: usize, c: usize) -> (usize, usize) {
    (N - 1 - r, N - 1 - c)
}

fn rot270_cell(r: usize, c: usize) -> (usize, usize) {
    (N - 1 - c, r)
}

fn flip_h_cell(r: usize, c: usize) -> (usize, usize) {
    (r, N - 1 - c)
}

fn transform_cell(r: usize, c: usize, sym: Symmetry) -> (usize, usize) {
    match sym {
        Symmetry::Id => (r, c),
        Symmetry::R90 => rot90_cell(r, c),
        Symmetry::R180 => rot180_cell(r, c),
        Symmetry::R270 => rot270_cell(r, c),
        Symmetry::FlipH => flip_h_cell(r, c),
        Symmetry::FlipHR90 => rot90_cell(flip_h_cell(r, c).0, flip_h_cell(r, c).1),
        Symmetry::FlipHR180 => rot180_cell(flip_h_cell(r, c).0, flip_h_cell(r, c).1),
        Symmetry::FlipHR270 => rot270_cell(flip_h_cell(r, c).0, flip_h_cell(r, c).1),
    }
}

/// Applique une symétrie au plateau et au dernier coup.
pub fn apply_symmetry(board: &Board, last_move: Option<Move>, sym: Symmetry) -> (Board, Option<Move>) {
    let mut out = [[0i8; N]; N];
    for r in 0..N {
        for c in 0..N {
            let (nr, nc) = transform_cell(r, c, sym);
            out[nr][nc] = board[r][c];
        }
    }
    let lm = last_move.map(|(r, c)| transform_cell(r, c, sym));
    (out, lm)
}

/// Retourne la forme canonique (hash Zobrist brut minimal).
pub fn canonical_position(
    board: &Board,
    current_player: i8,
    last_move: Option<Move>,
) -> (Board, i8, Option<Move>) {
    use crate::hasher::PositionHasher;

    let mut best: Option<(Board, Option<Move>, u64)> = None;

    for sym in ALL_SYMMETRIES {
        let (b, lm) = apply_symmetry(board, last_move, sym);
        let key = PositionHasher::raw_zobrist_int(&b, current_player, lm);
        if best.as_ref().map(|(_, _, k)| key < *k).unwrap_or(true) {
            best = Some((b, lm, key));
        }
    }

    let (b, lm, _) = best.expect("8 symétries");
    (b, current_player, lm)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::hasher::PositionHasher;

    #[test]
    fn rot90_four_times_is_identity() {
        let mut board = [[0i8; N]; N];
        board[2][3] = 1;
        board[4][5] = 2;
        let mut b = board;
        for _ in 0..4 {
            b = apply_symmetry(&b, None, Symmetry::R90).0;
        }
        assert_eq!(b, board);
    }

    #[test]
    fn symmetric_positions_share_canonical_hash() {
        let mut board = [[0i8; N]; N];
        board[1][1] = 1;
        let (b_rot, lm_rot) = apply_symmetry(&board, Some((1, 1)), Symmetry::R90);

        let c1 = canonical_position(&board, 2, Some((1, 1)));
        let c2 = canonical_position(&b_rot, 2, lm_rot);

        assert_eq!(
            PositionHasher::raw_hash_key(&c1.0, c1.1, c1.2),
            PositionHasher::raw_hash_key(&c2.0, c2.1, c2.2)
        );
    }

    #[test]
    fn empty_board_unchanged_by_canonical() {
        let board = [[0i8; N]; N];
        let c = canonical_position(&board, 1, None);
        assert_eq!(c.0, board);
        assert_eq!(c.2, None);
    }
}
