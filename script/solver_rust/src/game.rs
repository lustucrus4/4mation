//! Règles 4mation 7×7 — génération de coups et détection de victoire.

pub const BOARD_SIZE: usize = 7;
pub const WIN_LENGTH: usize = 4;

pub type Board = [[i8; BOARD_SIZE]; BOARD_SIZE];
pub type Move = (usize, usize);

const DIRECTIONS: [(i32, i32); 4] = [(0, 1), (1, 0), (1, 1), (1, -1)];

pub fn empty_cells(board: &Board) -> usize {
    board.iter().flatten().filter(|&&c| c == 0).count()
}

pub fn board_full(board: &Board) -> bool {
    empty_cells(board) == 0
}

pub fn parse_board(json: &serde_json::Value) -> Board {
    let mut board = [[0i8; BOARD_SIZE]; BOARD_SIZE];
    if let Some(rows) = json.as_array() {
        for (r, row) in rows.iter().enumerate().take(BOARD_SIZE) {
            if let Some(cols) = row.as_array() {
                for (c, cell) in cols.iter().enumerate().take(BOARD_SIZE) {
                    board[r][c] = cell.as_i64().unwrap_or(0) as i8;
                }
            }
        }
    }
    board
}

pub fn apply_move(board: &Board, mv: Move, player: i8) -> Board {
    let mut nb = *board;
    nb[mv.0][mv.1] = player;
    nb
}

/// Coups légaux (frontier) — même logique que OptimizedMinimaxAdvisor.
pub fn frontier_moves(board: &Board, last_move: Option<Move>, current_player: i8) -> Vec<Move> {
    let opponent = 3 - current_player;
    let mut valid = Vec::new();
    let mut seen = [false; BOARD_SIZE * BOARD_SIZE];

    let mut mark = |r: usize, c: usize| {
        let idx = r * BOARD_SIZE + c;
        if !seen[idx] {
            seen[idx] = true;
            valid.push((r, c));
        }
    };

    if empty_cells(board) == BOARD_SIZE * BOARD_SIZE {
        for r in 0..BOARD_SIZE {
            for c in 0..BOARD_SIZE {
                mark(r, c);
            }
        }
        return valid;
    }

    if let Some((lr, lc)) = last_move {
        for dr in -1..=1 {
            for dc in -1..=1 {
                if dr == 0 && dc == 0 {
                    continue;
                }
                let r = lr as i32 + dr;
                let c = lc as i32 + dc;
                if r >= 0
                    && c >= 0
                    && (r as usize) < BOARD_SIZE
                    && (c as usize) < BOARD_SIZE
                    && board[r as usize][c as usize] == 0
                {
                    mark(r as usize, c as usize);
                }
            }
        }
    }

    if valid.is_empty() {
        for row in 0..BOARD_SIZE {
            for col in 0..BOARD_SIZE {
                if board[row][col] != opponent {
                    continue;
                }
                for dr in -1..=1 {
                    for dc in -1..=1 {
                        if dr == 0 && dc == 0 {
                            continue;
                        }
                        let r = row as i32 + dr;
                        let c = col as i32 + dc;
                        if r >= 0
                            && c >= 0
                            && (r as usize) < BOARD_SIZE
                            && (c as usize) < BOARD_SIZE
                            && board[r as usize][c as usize] == 0
                        {
                            mark(r as usize, c as usize);
                        }
                    }
                }
            }
        }
    }

    valid
}

pub fn is_winning_move(board: &Board, mv: Move, player: i8) -> bool {
    let (row, col) = mv;
    let mut test = *board;
    test[row][col] = player;

    for &(dr, dc) in &DIRECTIONS {
        let mut count = 1i32;
        for step in [1i32, -1] {
            let mut r = row as i32;
            let mut c = col as i32;
            for _ in 0..3 {
                r += dr * step;
                c += dc * step;
                if r >= 0
                    && c >= 0
                    && (r as usize) < BOARD_SIZE
                    && (c as usize) < BOARD_SIZE
                    && test[r as usize][c as usize] == player
                {
                    count += 1;
                } else {
                    break;
                }
            }
        }
        if count >= WIN_LENGTH as i32 {
            return true;
        }
    }
    false
}

/// Retourne le joueur gagnant (1 ou 2), 0 pour nulle plateau plein, None si partie en cours.
pub fn check_winner(board: &Board) -> Option<i8> {
    for row in 0..BOARD_SIZE {
        for col in 0..BOARD_SIZE {
            let player = board[row][col];
            if player == 0 {
                continue;
            }
            for &(dr, dc) in &DIRECTIONS {
                let mut count = 1i32;
                for step in [1i32, -1] {
                    let mut r = row as i32;
                    let mut c = col as i32;
                    for _ in 0..3 {
                        r += dr * step;
                        c += dc * step;
                        if r >= 0
                            && c >= 0
                            && (r as usize) < BOARD_SIZE
                            && (c as usize) < BOARD_SIZE
                            && board[r as usize][c as usize] == player
                        {
                            count += 1;
                        } else {
                            break;
                        }
                    }
                }
                if count >= WIN_LENGTH as i32 {
                    return Some(player);
                }
            }
        }
    }
    None
}
