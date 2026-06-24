//! Types partagés claim/submit (worker HTTP et solveur local).

use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, Deserialize)]
pub struct ClaimedPosition {
    pub hash: String,
    pub board_json: Value,
    pub player: i32,
    pub last_move: Option<LastMove>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct LastMove {
    pub row: i32,
    pub col: i32,
}

#[derive(Debug, Serialize)]
pub struct SubmitPayload {
    pub hash: String,
    pub result: char,
    pub win_rate: f64,
    pub best_move: Option<SubmitMove>,
    pub depth_remaining: u32,
    pub board_json: Value,
    pub player: i32,
    pub last_move: Option<LastMove>,
    pub worker_id: String,
}

#[derive(Debug, Serialize)]
pub struct SubmitMove {
    pub row: i32,
    pub col: i32,
}

pub fn parse_last_move(raw: &Option<LastMove>) -> Option<(usize, usize)> {
    raw.as_ref().and_then(|lm| {
        if lm.row < 0 {
            None
        } else {
            Some((lm.row as usize, lm.col.max(0) as usize))
        }
    })
}

pub fn last_move_to_api(mv: Option<(usize, usize)>) -> Option<LastMove> {
    mv.map(|(r, c)| LastMove {
        row: r as i32,
        col: c as i32,
    })
}
