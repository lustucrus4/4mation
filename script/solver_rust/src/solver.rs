//! Solveur rétrograde — port de retrograde_solver.py.

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

pub struct RetrogradeSolver {
    max_empty: usize,
    max_nodes: usize,
    cache: HashMap<u128, SolvedPosition>,
    nodes_explored: usize,
}

impl RetrogradeSolver {
    pub fn new(max_empty: usize) -> Self {
        Self {
            max_empty,
            max_nodes: 500_000,
            cache: HashMap::with_capacity(4096),
            nodes_explored: 0,
        }
    }

    pub fn clear_cache(&mut self) {
        self.cache.clear();
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

    fn terminal(
        &self,
        board: &Board,
        last_move: Option<Move>,
        current_player: i8,
    ) -> Option<SolvedPosition> {
        if let Some(winner) = check_winner(board) {
            let (result, win_rate) = if winner == 0 {
                (RESULT_DRAW, 0.5)
            } else if winner == current_player {
                (RESULT_WIN, 1.0)
            } else {
                (RESULT_LOSS, 0.0)
            };
            return Some(SolvedPosition {
                result,
                win_rate,
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

        let moves = frontier_moves(board, last_move, current_player);
        if moves.is_empty() {
            return Some(SolvedPosition {
                result: RESULT_LOSS,
                win_rate: 0.0,
                best_move: None,
                depth_remaining: 0,
            });
        }

        None
    }

    pub fn solve_position(
        &mut self,
        board: &Board,
        current_player: i8,
        last_move: Option<Move>,
    ) -> Option<SolvedPosition> {
        if !self.should_solve(board) {
            return None;
        }
        if self.nodes_explored >= self.max_nodes {
            return None;
        }
        self.nodes_explored += 1;

        let h = Self::position_key(board, current_player, last_move);
        if let Some(cached) = self.cache.get(&h) {
            return Some(cached.clone());
        }

        if let Some(term) = self.terminal(board, last_move, current_player) {
            self.cache.insert(h, term.clone());
            return Some(term);
        }

        let moves = frontier_moves(board, last_move, current_player);
        let mut child_results: Vec<(Move, SolvedPosition)> = Vec::with_capacity(moves.len());

        for mv in moves {
            let opponent = 3 - current_player;
            let child = if is_winning_move(board, mv, current_player) {
                SolvedPosition {
                    result: RESULT_LOSS,
                    win_rate: 0.0,
                    best_move: None,
                    depth_remaining: 0,
                }
            } else {
                let nb = apply_move(board, mv, current_player);
                let solved = self.solve_position(&nb, opponent, Some(mv))?;
                solved
            };
            child_results.push((mv, child));
        }

        let mut best_move: Option<Move> = None;
        let mut best_wr = -1.0f64;
        let mut has_win = false;
        let mut all_loss = true;

        for (mv, child) in &child_results {
            let (my_result, my_wr) = match child.result {
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

        let depth = 1 + child_results
            .iter()
            .map(|(_, c)| c.depth_remaining)
            .max()
            .unwrap_or(0);

        let solved = SolvedPosition {
            result,
            win_rate,
            best_move,
            depth_remaining: depth,
        };
        self.cache.insert(h, solved.clone());
        Some(solved)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::game::parse_board;

    #[test]
    fn empty_board_is_drawish_frontier() {
        let board = [[0i8; BOARD_SIZE]; BOARD_SIZE];
        let mut solver = RetrogradeSolver::new(49);
        let result = solver.solve_position(&board, 1, None);
        assert!(result.is_some());
    }

    #[test]
    fn parse_and_solve_small() {
        let json: serde_json::Value = serde_json::json!([
            [0, 0, 0, 0, 0, 0, 0],
            [0, 1, 2, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0]
        ]);
        let board = parse_board(&json);
        let mut solver = RetrogradeSolver::new(49);
        assert!(solver.solve_position(&board, 1, Some((1, 2))).is_some());
    }
}
