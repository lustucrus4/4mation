//! Extraction de features hand-crafted pour policy linéaire (MVP CPU).

use formation_worker::game::{
    apply_move, check_winner, frontier_moves, is_winning_move, Board, Move, BOARD_SIZE,
};

pub const FEATURE_DIM: usize = 12;

/// Features normalisées pour un coup candidat (vue du joueur `player`).
pub fn move_features(
    board: &Board,
    mv: Move,
    player: i8,
    last_move: Option<Move>,
) -> [f64; FEATURE_DIM] {
    let opponent = 3 - player;
    let (r, c) = mv;
    let moves = frontier_moves(board, last_move, player);
    let frontier_norm = (moves.len() as f64 / (BOARD_SIZE * BOARD_SIZE) as f64).clamp(0.0, 1.0);

    let win_now = is_winning_move(board, mv, player) as i32 as f64;
    let block = is_winning_move(board, mv, opponent) as i32 as f64;

    let center = (BOARD_SIZE as f64 - 1.0) / 2.0;
    let dist_center =
        ((r as f64 - center).powi(2) + (c as f64 - center).powi(2)).sqrt()
            / (center * 2.0_f64.sqrt());

    let mut friends = 0u32;
    let mut enemies = 0u32;
    for dr in -1i32..=1 {
        for dc in -1i32..=1 {
            if dr == 0 && dc == 0 {
                continue;
            }
            let nr = r as i32 + dr;
            let nc = c as i32 + dc;
            if nr < 0 || nc < 0 || nr as usize >= BOARD_SIZE || nc as usize >= BOARD_SIZE {
                continue;
            }
            match board[nr as usize][nc as usize] {
                0 => {}
                p if p == player => friends += 1,
                _ => enemies += 1,
            }
        }
    }

    let nb = apply_move(board, mv, player);
    let opp_moves = frontier_moves(&nb, Some(mv), opponent);
    let mobility_after = opp_moves.len() as f64 / (BOARD_SIZE * BOARD_SIZE) as f64;

    let mut threats_created = 0.0;
    for om in opp_moves {
        if is_winning_move(&nb, om, opponent) {
            threats_created += 1.0;
        }
    }
    threats_created /= 8.0;

    let mut open_threes = 0.0;
    for &(dr, dc) in &[(0, 1), (1, 0), (1, 1), (1, -1)] {
        let mut count = 1i32;
        for step in [1i32, -1] {
            let mut rr = r as i32;
            let mut cc = c as i32;
            for _ in 0..3 {
                rr += dr * step;
                cc += dc * step;
                if rr >= 0
                    && cc >= 0
                    && (rr as usize) < BOARD_SIZE
                    && (cc as usize) < BOARD_SIZE
                    && nb[rr as usize][cc as usize] == player
                {
                    count += 1;
                } else {
                    break;
                }
            }
        }
        if count >= 3 {
            open_threes += 1.0;
        }
    }
    open_threes /= 4.0;

    let empty = board.iter().flatten().filter(|&&x| x == 0).count();
    let fill = 1.0 - (empty as f64 / (BOARD_SIZE * BOARD_SIZE) as f64);

    let player_sign = if player == 1 { 1.0 } else { -1.0 };

    let winner = check_winner(&nb);
    let terminal_win = if winner == Some(player) {
        1.0
    } else if winner == Some(opponent) {
        -1.0
    } else {
        0.0
    };

    [
        win_now,
        block,
        1.0 - dist_center,
        friends as f64 / 8.0,
        enemies as f64 / 8.0,
        frontier_norm,
        mobility_after,
        threats_created,
        open_threes,
        fill,
        player_sign,
        terminal_win,
    ]
}

#[cfg(test)]
mod tests {
    use super::*;
    use formation_worker::game::BOARD_SIZE;

    #[test]
    fn feature_vector_size() {
        let board = [[0i8; BOARD_SIZE]; BOARD_SIZE];
        let f = move_features(&board, (3, 3), 1, None);
        assert_eq!(f.len(), FEATURE_DIM);
    }
}
