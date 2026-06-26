//! Session de partie — état mutable pour self-play et évaluation.

use formation_worker::game::{
    apply_move, board_full, check_winner, frontier_moves, Board, Move, BOARD_SIZE,
};

#[derive(Clone, Debug)]
pub struct GameSession {
    pub board: Board,
    pub current_player: i8,
    pub last_move: Option<Move>,
    pub move_count: u32,
}

impl GameSession {
    pub fn new() -> Self {
        Self {
            board: [[0i8; BOARD_SIZE]; BOARD_SIZE],
            current_player: 1,
            last_move: None,
            move_count: 0,
        }
    }

    pub fn legal_moves(&self) -> Vec<Move> {
        frontier_moves(&self.board, self.last_move, self.current_player)
    }

    pub fn is_terminal(&self) -> bool {
        if check_winner(&self.board).is_some() {
            return true;
        }
        if board_full(&self.board) {
            return true;
        }
        self.legal_moves().is_empty()
    }

    pub fn winner(&self) -> Option<i8> {
        check_winner(&self.board)
    }

    pub fn apply(&mut self, mv: Move) -> bool {
        let legal = self.legal_moves();
        if !legal.contains(&mv) {
            return false;
        }
        self.board = apply_move(&self.board, mv, self.current_player);
        self.last_move = Some(mv);
        self.move_count += 1;
        self.current_player = 3 - self.current_player;
        true
    }

    /// Récompense terminal vue du joueur `perspective` (+1 win, -1 loss, 0 draw).
    pub fn terminal_reward(&self, perspective: i8) -> f64 {
        match self.winner() {
            Some(w) if w == perspective => 1.0,
            Some(_) => -1.0,
            None => 0.0,
        }
    }
}

impl Default for GameSession {
    fn default() -> Self {
        Self::new()
    }
}
