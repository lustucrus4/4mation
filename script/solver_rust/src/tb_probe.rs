//! Lecture de la tablebase SQLite comme sonde exacte pour le moteur.
//!
//! La table `positions` stocke le résultat du point de vue du joueur au trait
//! (`W` victoire, `D` nulle, `L` défaite) ainsi que son meilleur coup.
//! La clé est le hash canonique minimal sur les 8 symétries du carré, identique
//! à celui produit par `position_hasher.py`.

use std::path::Path;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;

use rusqlite::{Connection, OpenFlags};

use crate::engine::{position_key, Probe};

pub struct SqliteProbe {
    conn: Mutex<Connection>,
    hits: AtomicU64,
    misses: AtomicU64,
}

impl SqliteProbe {
    pub fn open(path: &Path) -> rusqlite::Result<Self> {
        let conn = Connection::open_with_flags(
            path,
            OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX,
        )?;
        Ok(Self {
            conn: Mutex::new(conn),
            hits: AtomicU64::new(0),
            misses: AtomicU64::new(0),
        })
    }

    /// Nombre de positions trouvées et manquantes depuis l'ouverture.
    pub fn stats(&self) -> (u64, u64) {
        (
            self.hits.load(Ordering::Relaxed),
            self.misses.load(Ordering::Relaxed),
        )
    }

    fn hash(p1: u64, p2: u64, side: u8, last: u8) -> String {
        format!("{:016x}", position_key(p1, p2, side, last))
    }
}

/// Convertit la colonne `result` en valeur pour le joueur au trait.
fn to_wdl(value: &str) -> Option<i8> {
    match value.trim() {
        "W" | "w" | "win" | "1" => Some(1),
        "D" | "d" | "draw" | "0" => Some(0),
        "L" | "l" | "loss" | "2" => Some(-1),
        _ => None,
    }
}

impl Probe for SqliteProbe {
    fn wdl(&self, p1: u64, p2: u64, side: u8, last: u8) -> Option<i8> {
        let key = Self::hash(p1, p2, side, last);
        let ok = self.conn.lock().ok()?;
        let row: Option<String> = ok
            .prepare_cached("SELECT result FROM positions WHERE hash=?1")
            .ok()?
            .query_row([&key], |r| r.get(0))
            .ok();
        match row.as_deref().and_then(to_wdl) {
            Some(v) => {
                self.hits.fetch_add(1, Ordering::Relaxed);
                Some(v)
            }
            None => {
                self.misses.fetch_add(1, Ordering::Relaxed);
                None
            }
        }
    }

    fn best(&self, p1: u64, p2: u64, side: u8, last: u8) -> Option<u8> {
        let key = Self::hash(p1, p2, side, last);
        let ok = self.conn.lock().ok()?;
        let row: Option<(i64, i64)> = ok
            .prepare_cached(
                "SELECT best_move_row, best_move_col FROM positions \
                 WHERE hash=?1 AND best_move_row IS NOT NULL AND best_move_row >= 0",
            )
            .ok()?
            .query_row([&key], |r| Ok((r.get(0)?, r.get(1)?)))
            .ok();
        let (r, c) = row?;
        if !(0..7).contains(&r) || !(0..7).contains(&c) {
            return None;
        }
        Some((r * 7 + c) as u8)
    }
}

#[cfg(test)]
mod tests {
    use super::to_wdl;

    #[test]
    fn lit_les_trois_resultats() {
        assert_eq!(to_wdl("W"), Some(1));
        assert_eq!(to_wdl("D"), Some(0));
        assert_eq!(to_wdl("L"), Some(-1));
        assert_eq!(to_wdl("?"), None);
    }
}
