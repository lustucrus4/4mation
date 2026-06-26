//! Table de résultats en mémoire (tablebase chaude).
//!
//! `ResultTable` est l'artefact interrogé pendant la résolution : un dictionnaire
//! `zobrist canonique (u64) -> résultat empaqueté (u8)`. Elle est chargée une fois
//! au démarrage depuis `positions`, puis mise à jour à chaque position résolue.
//!
//! L'empaquetage tient sur un octet : bits 0-1 = résultat (L=0, D=1, W=2),
//! bits 2-7 = `depth_remaining` borné à 63 (≤ 49 cases vides en pratique).

use anyhow::Result;
use dashmap::DashMap;

use crate::game::{Board, Move};
use crate::hasher::PositionHasher;
use crate::local_db::LocalDb;
use crate::solver::{ChildOracle, ChildValue, RESULT_DRAW, RESULT_LOSS, RESULT_WIN};

const CODE_LOSS: u8 = 0;
const CODE_DRAW: u8 = 1;
const CODE_WIN: u8 = 2;

#[inline]
fn pack(result: char, depth: u32) -> u8 {
    let code = match result {
        RESULT_WIN => CODE_WIN,
        RESULT_DRAW => CODE_DRAW,
        _ => CODE_LOSS,
    };
    let d = depth.min(63) as u8;
    (d << 2) | code
}

#[inline]
fn unpack(v: u8) -> (char, u32) {
    let result = match v & 0b11 {
        CODE_WIN => RESULT_WIN,
        CODE_DRAW => RESULT_DRAW,
        _ => RESULT_LOSS,
    };
    let depth = (v >> 2) as u32;
    (result, depth)
}

pub struct ResultTable {
    map: DashMap<u64, u8>,
}

impl ResultTable {
    pub fn new() -> Self {
        Self {
            map: DashMap::new(),
        }
    }

    pub fn with_capacity(cap: usize) -> Self {
        Self {
            map: DashMap::with_capacity(cap),
        }
    }

    pub fn len(&self) -> usize {
        self.map.len()
    }

    pub fn is_empty(&self) -> bool {
        self.map.is_empty()
    }

    /// Charge toutes les positions résolues depuis la base (hash hex -> u64).
    pub fn load_from_db(db: &LocalDb) -> Result<Self> {
        let table = Self::with_capacity(1 << 20);
        db.for_each_solved(|hash, result, depth| {
            let res = result.chars().next().unwrap_or(RESULT_DRAW);
            table.insert_hash_hex(hash, res, depth.max(0) as u32);
        })?;
        Ok(table)
    }

    /// Insère via la clé hexadécimale stockée en base (déjà canonique).
    #[inline]
    pub fn insert_hash_hex(&self, hash: &str, result: char, depth: u32) {
        if let Ok(key) = u64::from_str_radix(hash, 16) {
            self.map.insert(key, pack(result, depth));
        }
    }

    /// Insère via une position (board, joueur, dernier coup), canonicalisée si besoin.
    #[inline]
    pub fn insert_position(
        &self,
        board: &Board,
        player: i8,
        last_move: Option<Move>,
        result: char,
        depth: u32,
    ) {
        let key = Self::key_for(board, player, last_move);
        self.map.insert(key, pack(result, depth));
    }

    /// Clé de lookup cohérente avec `PositionHasher::hash_key` (canonique si symétries actives).
    #[inline]
    pub fn key_for(board: &Board, player: i8, last_move: Option<Move>) -> u64 {
        if PositionHasher::symmetry_enabled() {
            let (b, p, lm) = crate::symmetry::canonical_position(board, player, last_move);
            PositionHasher::raw_zobrist_int(&b, p, lm)
        } else {
            PositionHasher::raw_zobrist_int(board, player, last_move)
        }
    }

    #[inline]
    pub fn get(&self, board: &Board, player: i8, last_move: Option<Move>) -> Option<(char, u32)> {
        let key = Self::key_for(board, player, last_move);
        self.map.get(&key).map(|v| unpack(*v))
    }
}

impl Default for ResultTable {
    fn default() -> Self {
        Self::new()
    }
}

impl ChildOracle for ResultTable {
    #[inline]
    fn lookup(&self, board: &Board, player: i8, last_move: Option<Move>) -> Option<ChildValue> {
        self.get(board, player, last_move)
            .map(|(result, depth)| ChildValue { result, depth })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pack_roundtrip() {
        for (res, depth) in [(RESULT_WIN, 7u32), (RESULT_LOSS, 0), (RESULT_DRAW, 49), (RESULT_WIN, 63)] {
            let (r, d) = unpack(pack(res, depth));
            assert_eq!(r, res);
            assert_eq!(d, depth);
        }
    }

    #[test]
    fn depth_is_capped() {
        let (_, d) = unpack(pack(RESULT_WIN, 1000));
        assert_eq!(d, 63);
    }

    #[test]
    fn insert_and_get_consistent() {
        use crate::game::BOARD_SIZE;
        let table = ResultTable::new();
        let mut board = [[0i8; BOARD_SIZE]; BOARD_SIZE];
        board[1][1] = 1;
        table.insert_position(&board, 2, Some((1, 1)), RESULT_WIN, 5);
        assert_eq!(table.get(&board, 2, Some((1, 1))), Some((RESULT_WIN, 5)));
    }
}
