//! Règles 4mation 7×7 — génération de coups et détection de victoire.

pub const BOARD_SIZE: usize = 7;
pub const WIN_LENGTH: usize = 4;

pub type Board = [[i8; BOARD_SIZE]; BOARD_SIZE];
pub type Move = (usize, usize);
pub type Position = (Board, i8, Option<Move>);

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

/// Nombre d'octets d'un plateau compacté (49 cellules × 2 bits = 98 bits → 13 octets).
pub const BOARD_BLOB_LEN: usize = 13;

/// Compacte le plateau en BLOB : 2 bits par cellule (0/1/2), ordre ligne-major.
pub fn board_to_blob(board: &Board) -> Vec<u8> {
    let mut out = vec![0u8; BOARD_BLOB_LEN];
    for r in 0..BOARD_SIZE {
        for c in 0..BOARD_SIZE {
            let idx = r * BOARD_SIZE + c;
            let v = (board[r][c] & 0b11) as u8;
            out[idx / 4] |= v << ((idx % 4) * 2);
        }
    }
    out
}

/// Représentation JSON (tableau 2D) du plateau — interface inchangée pour le solveur.
pub fn board_to_value(board: &Board) -> serde_json::Value {
    serde_json::Value::Array(
        board
            .iter()
            .map(|row| {
                serde_json::Value::Array(
                    row.iter().map(|&c| serde_json::Value::from(c)).collect(),
                )
            })
            .collect(),
    )
}

/// Reconstruit le plateau depuis un BLOB compacté. Tolère un BLOB trop court (zéros).
pub fn board_from_blob(blob: &[u8]) -> Board {
    let mut board = [[0i8; BOARD_SIZE]; BOARD_SIZE];
    for r in 0..BOARD_SIZE {
        for c in 0..BOARD_SIZE {
            let idx = r * BOARD_SIZE + c;
            let byte = idx / 4;
            if byte < blob.len() {
                let v = (blob[byte] >> ((idx % 4) * 2)) & 0b11;
                board[r][c] = v as i8;
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

/// Vrai si tous les pions du plateau forment un unique bloc 8-connexe
/// (ou s'il y a 0/1 pion). C'est une condition NÉCESSAIRE de légalité :
/// chaque coup étant adjacent au précédent (ou à un pion adverse), une
/// position réellement atteignable n'a jamais de pion isolé ni de blocs séparés.
pub fn is_connected(board: &Board) -> bool {
    let mut start: Option<(usize, usize)> = None;
    let mut total = 0usize;
    for r in 0..BOARD_SIZE {
        for c in 0..BOARD_SIZE {
            if board[r][c] != 0 {
                total += 1;
                if start.is_none() {
                    start = Some((r, c));
                }
            }
        }
    }
    let Some((sr, sc)) = start else {
        return true;
    };

    let mut seen = [[false; BOARD_SIZE]; BOARD_SIZE];
    let mut stack = vec![(sr, sc)];
    seen[sr][sc] = true;
    let mut count = 0usize;
    while let Some((r, c)) = stack.pop() {
        count += 1;
        for dr in -1i32..=1 {
            for dc in -1i32..=1 {
                if dr == 0 && dc == 0 {
                    continue;
                }
                let nr = r as i32 + dr;
                let nc = c as i32 + dc;
                if nr >= 0 && nc >= 0 && (nr as usize) < BOARD_SIZE && (nc as usize) < BOARD_SIZE {
                    let (nr, nc) = (nr as usize, nc as usize);
                    if !seen[nr][nc] && board[nr][nc] != 0 {
                        seen[nr][nc] = true;
                        stack.push((nr, nc));
                    }
                }
            }
        }
    }
    count == total
}

/// Coups légaux (frontier) — même logique que OptimizedMinimaxAdvisor.
pub fn frontier_moves(board: &Board, last_move: Option<Move>, current_player: i8) -> Vec<Move> {
    let opponent = 3 - current_player;
    let mut valid = Vec::new();
    let mut seen = [false; BOARD_SIZE * BOARD_SIZE];

    fn push_unique(
        valid: &mut Vec<Move>,
        seen: &mut [bool; BOARD_SIZE * BOARD_SIZE],
        r: usize,
        c: usize,
    ) {
        let idx = r * BOARD_SIZE + c;
        if !seen[idx] {
            seen[idx] = true;
            valid.push((r, c));
        }
    }

    if empty_cells(board) == BOARD_SIZE * BOARD_SIZE {
        for r in 0..BOARD_SIZE {
            for c in 0..BOARD_SIZE {
                push_unique(&mut valid, &mut seen, r, c);
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
                    push_unique(&mut valid, &mut seen, r as usize, c as usize);
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
                            push_unique(&mut valid, &mut seen, r as usize, c as usize);
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn board_blob_round_trip() {
        let mut board = [[0i8; BOARD_SIZE]; BOARD_SIZE];
        let mut v = 0i8;
        for r in 0..BOARD_SIZE {
            for c in 0..BOARD_SIZE {
                board[r][c] = v;
                v = (v + 1) % 3;
            }
        }
        let blob = board_to_blob(&board);
        assert_eq!(blob.len(), BOARD_BLOB_LEN);
        assert_eq!(board_from_blob(&blob), board);
    }

    #[test]
    fn connected_detects_isolated_stone() {
        let mut b = [[0i8; BOARD_SIZE]; BOARD_SIZE];
        // 0 pion → connexe par convention
        assert!(is_connected(&b));
        // 1 pion → connexe
        b[3][3] = 1;
        assert!(is_connected(&b));
        // 2 pions adjacents → connexe
        b[3][4] = 2;
        assert!(is_connected(&b));
        // pion isolé loin du bloc → non connexe
        b[0][0] = 1;
        assert!(!is_connected(&b));
        // on relie le coin via la diagonale → de nouveau connexe
        b[1][1] = 2;
        b[2][2] = 1;
        assert!(is_connected(&b));
    }

    #[test]
    fn board_blob_empty_and_full() {
        let empty = [[0i8; BOARD_SIZE]; BOARD_SIZE];
        assert_eq!(board_from_blob(&board_to_blob(&empty)), empty);
        let full = [[2i8; BOARD_SIZE]; BOARD_SIZE];
        assert_eq!(board_from_blob(&board_to_blob(&full)), full);
    }
}
