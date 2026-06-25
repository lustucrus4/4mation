//! Solveur rétrograde — résolution 1 coup (tablebase) + repli negamax alpha-bêta.
//!
//! Deux chemins :
//! - `resolve_via_children` : lookup des enfants (déjà résolus) dans un `ChildOracle`,
//!   combinaison immédiate -> O(coups). C'est le chemin chaud.
//! - `RetrogradeSolver::solve_with_oracle` : recherche negamax 3-valeurs avec
//!   élagage alpha-bêta, ordre des coups et consultation de l'oracle aux nœuds (repli).
//!
//! Les deux partagent la même sélection de `best_move` (`decide`) afin de garantir
//! une concordance stricte avec la base déjà construite.

use std::collections::HashMap;

use crate::game::{
    apply_move, board_full, check_winner, empty_cells, frontier_moves, is_winning_move, Board,
    Move, BOARD_SIZE,
};

pub const RESULT_WIN: char = 'W';
pub const RESULT_LOSS: char = 'L';
pub const RESULT_DRAW: char = 'D';

#[derive(Clone, Debug)]
pub struct SolvedPosition {
    pub result: char,
    pub win_rate: f64,
    pub best_move: Option<Move>,
    pub depth_remaining: u32,
}

/// Valeur d'un enfant déjà résolu (du point de vue du joueur au trait dans cet enfant).
#[derive(Clone, Copy, Debug)]
pub struct ChildValue {
    pub result: char,
    pub depth: u32,
}

/// Source de positions déjà résolues (tablebase en mémoire).
pub trait ChildOracle {
    fn lookup(&self, board: &Board, player: i8, last_move: Option<Move>) -> Option<ChildValue>;
}

#[inline]
fn value_to_result(v: i8) -> char {
    match v {
        1 => RESULT_WIN,
        0 => RESULT_DRAW,
        _ => RESULT_LOSS,
    }
}

#[inline]
fn result_to_value(result: char) -> i8 {
    match result {
        RESULT_WIN => 1,
        RESULT_DRAW => 0,
        _ => -1,
    }
}

#[inline]
fn win_rate_for(result: char) -> f64 {
    match result {
        RESULT_WIN => 1.0,
        RESULT_DRAW => 0.5,
        _ => 0.0,
    }
}

/// Résultat terminal éventuel (victoire, plateau plein, aucun coup).
fn terminal_position(
    board: &Board,
    last_move: Option<Move>,
    current_player: i8,
) -> Option<SolvedPosition> {
    if let Some(winner) = check_winner(board) {
        let result = if winner == 0 {
            RESULT_DRAW
        } else if winner == current_player {
            RESULT_WIN
        } else {
            RESULT_LOSS
        };
        return Some(SolvedPosition {
            result,
            win_rate: win_rate_for(result),
            best_move: None,
            depth_remaining: 0,
        });
    }
    if board_full(board) {
        return Some(SolvedPosition {
            result: RESULT_DRAW,
            win_rate: 0.5,
            best_move: None,
            depth_remaining: 0,
        });
    }
    if frontier_moves(board, last_move, current_player).is_empty() {
        return Some(SolvedPosition {
            result: RESULT_LOSS,
            win_rate: 0.0,
            best_move: None,
            depth_remaining: 0,
        });
    }
    None
}

/// Sélection finale identique à l'ancien solveur (concordance stricte).
///
/// `child_results` : `(coup, résultat de l'enfant du point de vue de l'enfant, depth enfant)`,
/// dans l'ordre `frontier_moves`.
fn decide(child_results: &[(Move, char, u32)]) -> Option<SolvedPosition> {
    if child_results.is_empty() {
        return None;
    }

    let mut best_move: Option<Move> = None;
    let mut best_wr = -1.0f64;
    let mut has_win = false;
    let mut all_loss = true;

    for (mv, child_result, _) in child_results {
        let (my_result, my_wr) = match *child_result {
            RESULT_LOSS => (RESULT_WIN, 1.0),
            RESULT_WIN => (RESULT_LOSS, 0.0),
            _ => (RESULT_DRAW, 0.5),
        };

        if my_result == RESULT_WIN {
            has_win = true;
            all_loss = false;
            if my_wr > best_wr {
                best_wr = my_wr;
                best_move = Some(*mv);
            }
        } else if my_result == RESULT_DRAW {
            all_loss = false;
            if !has_win && my_wr > best_wr {
                best_wr = my_wr;
                best_move = Some(*mv);
            }
        } else if !has_win && best_move.is_none() {
            best_wr = my_wr;
            best_move = Some(*mv);
        }
    }

    let (result, win_rate) = if has_win {
        (RESULT_WIN, 1.0)
    } else if all_loss {
        (RESULT_LOSS, 0.0)
    } else {
        (RESULT_DRAW, 0.5)
    };

    if result == RESULT_LOSS {
        best_move = Some(child_results[0].0);
    } else if best_move.is_none() {
        best_move = Some(child_results[0].0);
    }

    let depth = 1 + child_results.iter().map(|(_, _, d)| *d).max().unwrap_or(0);

    Some(SolvedPosition {
        result,
        win_rate,
        best_move,
        depth_remaining: depth,
    })
}

/// Résolution 1 coup : tous les enfants doivent être connus de l'oracle (sinon `None` -> repli).
///
/// Court-circuit sur coup gagnant : dès qu'un coup gagne (ligne directe ou enfant perdant
/// pour l'adversaire) on conclut WIN avec ce coup comme meilleur coup (premier dans l'ordre).
pub fn resolve_via_children(
    board: &Board,
    player: i8,
    last_move: Option<Move>,
    oracle: &dyn ChildOracle,
) -> Option<SolvedPosition> {
    if let Some(term) = terminal_position(board, last_move, player) {
        return Some(term);
    }

    let moves = frontier_moves(board, last_move, player);
    let mut child_results: Vec<(Move, char, u32)> = Vec::with_capacity(moves.len());

    for mv in moves {
        if is_winning_move(board, mv, player) {
            // Court-circuit : premier coup gagnant dans l'ordre = meilleur coup.
            child_results.push((mv, RESULT_LOSS, 0));
            return decide(&child_results);
        }
        let opponent = 3 - player;
        let nb = apply_move(board, mv, player);
        match oracle.lookup(&nb, opponent, Some(mv)) {
            Some(cv) => {
                if cv.result == RESULT_LOSS {
                    // Enfant perdant pour l'adversaire => on gagne ; court-circuit.
                    child_results.push((mv, RESULT_LOSS, cv.depth));
                    return decide(&child_results);
                }
                child_results.push((mv, cv.result, cv.depth));
            }
            None => return None,
        }
    }

    decide(&child_results)
}

pub struct RetrogradeSolver {
    max_empty: usize,
    max_nodes: usize,
    val_cache: HashMap<u128, (i8, u32)>,
    nodes_explored: usize,
}

impl RetrogradeSolver {
    pub fn new(max_empty: usize) -> Self {
        let empty_hint = max_empty.max(12);
        Self {
            max_empty,
            max_nodes: node_budget(empty_hint, 1),
            val_cache: HashMap::with_capacity(4096),
            nodes_explored: 0,
        }
    }

    pub fn for_board(max_empty: usize, empty_cells: usize) -> Self {
        Self::for_board_scaled(max_empty, empty_cells, 1)
    }

    pub fn for_board_scaled(max_empty: usize, empty_cells: usize, budget_mult: usize) -> Self {
        let depth = max_empty.max(empty_cells);
        Self {
            max_empty: depth,
            max_nodes: node_budget(depth, budget_mult),
            val_cache: HashMap::with_capacity(4096),
            nodes_explored: 0,
        }
    }

    pub fn clear_cache(&mut self) {
        self.val_cache.clear();
        self.nodes_explored = 0;
    }

    fn should_solve(&self, board: &Board) -> bool {
        empty_cells(board) <= self.max_empty
    }

    fn position_key(board: &Board, player: i8, last_move: Option<Move>) -> u128 {
        let mut key: u128 = 0;
        for r in 0..BOARD_SIZE {
            for c in 0..BOARD_SIZE {
                let cell = (board[r][c] + 1) as u128;
                key = key * 3 + cell;
            }
        }
        key = key * 3 + (player as u128);
        if let Some((lr, lc)) = last_move {
            key = key * 49 + (lr * BOARD_SIZE + lc) as u128 + 1;
        }
        key
    }

    /// Coups ordonnés pour l'élagage (proximité du centre) — n'affecte pas le résultat.
    fn ordered_moves(board: &Board, last_move: Option<Move>, player: i8) -> Vec<Move> {
        let mut moves = frontier_moves(board, last_move, player);
        moves.sort_by_key(|&(r, c)| {
            let dr = (r as i32 - 3).abs();
            let dc = (c as i32 - 3).abs();
            dr.max(dc)
        });
        moves
    }

    /// Compat : ancien point d'entrée (worker HTTP), sans oracle.
    pub fn solve_position(
        &mut self,
        board: &Board,
        current_player: i8,
        last_move: Option<Move>,
    ) -> Option<SolvedPosition> {
        self.solve_with_oracle(board, current_player, last_move, None)
    }

    /// Résolution racine : collecte les enfants (recherche alpha-bêta + oracle aux nœuds)
    /// puis applique la sélection `decide` (concordance stricte du meilleur coup).
    pub fn solve_with_oracle(
        &mut self,
        board: &Board,
        current_player: i8,
        last_move: Option<Move>,
        oracle: Option<&dyn ChildOracle>,
    ) -> Option<SolvedPosition> {
        if !self.should_solve(board) {
            return None;
        }
        if let Some(term) = terminal_position(board, last_move, current_player) {
            return Some(term);
        }

        let moves = frontier_moves(board, last_move, current_player);
        let mut child_results: Vec<(Move, char, u32)> = Vec::with_capacity(moves.len());
        let opponent = 3 - current_player;

        for mv in moves {
            if is_winning_move(board, mv, current_player) {
                child_results.push((mv, RESULT_LOSS, 0));
                continue;
            }
            let nb = apply_move(board, mv, current_player);
            let empty_child = empty_cells(&nb);
            let child_val = match self.value_ab(&nb, opponent, Some(mv), -1, 1, oracle) {
                Some(v) => Some(v),
                None => {
                    // Repli budget étendu (équivalent ancien sous-solveur ×3).
                    let mut sub =
                        RetrogradeSolver::for_board_scaled(self.max_empty, empty_child, 3);
                    sub.value_ab(&nb, opponent, Some(mv), -1, 1, oracle)
                }
            };
            match child_val {
                Some((cv, cd)) => child_results.push((mv, value_to_result(cv), cd)),
                None => continue,
            }
        }

        decide(&child_results)
    }

    /// Negamax 3-valeurs (-1/0/+1) du point de vue de `player`, élagage alpha-bêta.
    /// Renvoie `(valeur, depth)` ; `None` si le budget de nœuds est dépassé (indécidable).
    fn value_ab(
        &mut self,
        board: &Board,
        player: i8,
        last_move: Option<Move>,
        mut alpha: i8,
        beta: i8,
        oracle: Option<&dyn ChildOracle>,
    ) -> Option<(i8, u32)> {
        if self.nodes_explored >= self.max_nodes {
            return None;
        }
        self.nodes_explored += 1;

        if let Some(term) = terminal_position(board, last_move, player) {
            return Some((result_to_value(term.result), 0));
        }

        if let Some(o) = oracle {
            if let Some(cv) = o.lookup(board, player, last_move) {
                return Some((result_to_value(cv.result), cv.depth));
            }
        }

        let key = Self::position_key(board, player, last_move);
        if let Some(&cached) = self.val_cache.get(&key) {
            return Some(cached);
        }

        let opponent = 3 - player;
        let mut best = -2i8;
        let mut best_depth = 0u32;
        let mut incomplete = false;
        let mut cutoff = false;

        for mv in Self::ordered_moves(board, last_move, player) {
            if is_winning_move(board, mv, player) {
                best = 1;
                best_depth = 1;
                cutoff = true;
                break;
            }
            let nb = apply_move(board, mv, player);
            match self.value_ab(&nb, opponent, Some(mv), -beta, -alpha, oracle) {
                None => incomplete = true,
                Some((cv, cd)) => {
                    let v = -cv;
                    let d = cd + 1;
                    if v > best || (v == best && d > best_depth) {
                        best = v;
                        best_depth = d;
                    }
                    if v > alpha {
                        alpha = v;
                    }
                    if alpha >= beta {
                        cutoff = true;
                        break;
                    }
                }
            }
        }

        // Victoire prouvée : exacte, quel que soit l'état des autres branches.
        if best == 1 {
            self.val_cache.insert(key, (1, best_depth));
            return Some((1, best_depth));
        }
        // Une branche indécidable empêche de conclure NUL/PERTE.
        if incomplete {
            return None;
        }
        if best == -2 {
            // Aucun coup exploitable (cas terminal déjà filtré) — perte.
            return Some((-1, 0));
        }
        // Coupure alpha-bêta : valeur seulement bornée, ne pas mémoriser comme exacte.
        if !cutoff {
            self.val_cache.insert(key, (best, best_depth));
        }
        Some((best, best_depth))
    }
}

fn node_budget(depth: usize, mult: usize) -> usize {
    let base = 500_000usize;
    let scaled = base.saturating_mul(depth).div_ceil(10);
    let m = mult.max(1);
    scaled.saturating_mul(m).clamp(base, 16_000_000)
}

#[cfg(test)]
mod tests {
    use super::*;

    struct EmptyOracle;
    impl ChildOracle for EmptyOracle {
        fn lookup(&self, _: &Board, _: i8, _: Option<Move>) -> Option<ChildValue> {
            None
        }
    }

    /// Oracle qui déclare tous les enfants perdants (du point de vue de l'enfant).
    struct AllLossOracle;
    impl ChildOracle for AllLossOracle {
        fn lookup(&self, _: &Board, _: i8, _: Option<Move>) -> Option<ChildValue> {
            Some(ChildValue {
                result: RESULT_LOSS,
                depth: 2,
            })
        }
    }

    #[test]
    fn empty_board_should_solve_when_max_empty_49() {
        let board = [[0i8; BOARD_SIZE]; BOARD_SIZE];
        let solver = RetrogradeSolver::new(49);
        assert!(solver.should_solve(&board));
    }

    #[test]
    fn endgame_position_solves() {
        let mut board = [[0i8; BOARD_SIZE]; BOARD_SIZE];
        for r in 0..6 {
            for c in 0..7 {
                board[r][c] = if (r + c) % 2 == 0 { 1 } else { 2 };
            }
        }
        let mut solver = RetrogradeSolver::new(12);
        assert!(solver.solve_position(&board, 1, Some((5, 6))).is_some());
    }

    #[test]
    fn immediate_winning_move_detected_by_search() {
        // Trois pions alignés pour le joueur 1 : (3,0),(3,1),(3,2) ; (3,3) gagne.
        // Les autres voisins du dernier coup sont occupés => (3,3) est le seul coup légal.
        let mut board = [[0i8; BOARD_SIZE]; BOARD_SIZE];
        board[3][0] = 1;
        board[3][1] = 1;
        board[3][2] = 1;
        for &(r, c) in &[(2, 1), (2, 2), (2, 3), (4, 1), (4, 2), (4, 3)] {
            board[r][c] = 2;
        }
        let mut solver = RetrogradeSolver::new(45);
        let solved = solver
            .solve_with_oracle(&board, 1, Some((3, 2)), None)
            .expect("coup gagnant");
        assert_eq!(solved.result, RESULT_WIN);
        assert_eq!(solved.best_move, Some((3, 3)));
    }

    #[test]
    fn resolve_via_children_wins_when_child_is_loss() {
        // Aucun coup gagnant direct, mais tous les enfants perdants pour l'adversaire => WIN.
        let mut board = [[0i8; BOARD_SIZE]; BOARD_SIZE];
        board[3][3] = 1;
        let solved =
            resolve_via_children(&board, 2, Some((3, 3)), &AllLossOracle).expect("résolu");
        assert_eq!(solved.result, RESULT_WIN);
    }

    #[test]
    fn resolve_via_children_needs_known_children() {
        // Aucun coup gagnant direct + oracle vide => indécidable (repli attendu).
        let mut board = [[0i8; BOARD_SIZE]; BOARD_SIZE];
        board[3][3] = 1;
        board[2][2] = 2;
        assert!(resolve_via_children(&board, 1, Some((2, 2)), &EmptyOracle).is_none());
    }
}
