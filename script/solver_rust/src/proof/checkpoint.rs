//! Checkpoint JSON du solveur de preuve (`4mation-proof`).
//!
//! Le solveur de preuve n'a pas de tablebase : son état utile tient dans une table de
//! transposition (TT) en mémoire, perdue à l'arrêt. Ce fichier persiste ce qui est
//! **réellement reprenable sans risque** :
//!
//! - les ouvertures (orbites D₄) déjà **tranchées**, avec leur valeur exacte : une fois
//!   `wdl` renvoie W/D/L, la preuve est complète et peut être rejouée telle quelle ;
//! - la **profondeur déjà tentée** par ouverture non tranchée, pour reprendre à la
//!   profondeur suivante (l'approfondissement itératif est monotone : une profondeur
//!   qui n'a rien prouvé reste à tenter plus profond).
//!
//! Ce qui n'est PAS reprenable est documenté honnêtement : le contenu de la TT
//! (millions d'entrées de hachage) n'est pas sérialisé. Une reprise recalcule donc les
//! sous-arbres non couverts par les orbites prouvées ; elle évite seulement de
//! rechercher à nouveau les ouvertures déjà tranchées et les profondeurs trop faibles.

use std::fs;
use std::io;
use std::path::Path;

use serde::{Deserialize, Serialize};
use std::time::{SystemTime, UNIX_EPOCH};

/// Version du format. À incrémenter si la structure change.
pub const CHECKPOINT_VERSION: u32 = 1;

/// Avancement d'une ouverture (un représentant par orbite D₄).
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct OrbitProgress {
    pub row: u8,
    pub col: u8,
    /// `pending`, `searching`, `win`, `draw` ou `loss`.
    pub status: String,
    /// Valeur pour le joueur 1 si prouvée (1 victoire, 0 nulle, -1 défaite).
    pub value_for_first: Option<i8>,
    /// Prochaine profondeur à tenter (dernière tentative + 1, ou la même si interrompue).
    pub next_depth: i16,
    /// Secondes écoulées sur cette ouverture (informatif).
    pub elapsed_sec: f64,
}

impl OrbitProgress {
    pub fn pending(row: u8, col: u8) -> Self {
        Self {
            row,
            col,
            status: "pending".into(),
            value_for_first: None,
            next_depth: 1,
            elapsed_sec: 0.0,
        }
    }

    pub fn is_proven(&self) -> bool {
        self.value_for_first.is_some()
    }
}

/// État complet d'une session de preuve, sérialisé en JSON.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ProgressCheckpoint {
    pub version: u32,
    pub threads: usize,
    pub tt_mb: usize,
    /// Horodatage Unix (secondes) de la dernière écriture.
    pub updated_at_epoch: u64,
    /// Résultat global pour le joueur 1, si atteint.
    pub result: Option<i8>,
    /// Meilleur premier coup prouvé, `[ligne, colonne]`.
    pub best: Option<[u8; 2]>,
    pub orbits: Vec<OrbitProgress>,
}

impl ProgressCheckpoint {
    pub fn new(threads: usize, tt_mb: usize) -> Self {
        Self {
            version: CHECKPOINT_VERSION,
            threads,
            tt_mb,
            updated_at_epoch: 0,
            result: None,
            best: None,
            orbits: Vec::new(),
        }
    }

    pub fn find(&self, row: u8, col: u8) -> Option<&OrbitProgress> {
        self.orbits.iter().find(|o| o.row == row && o.col == col)
    }

    /// Écriture atomique : fichier temporaire puis renommage, pour ne jamais
    /// laisser un checkpoint tronqué si le processus est tué pendant l'écriture.
    pub fn save(&self, path: &Path) -> io::Result<()> {
        if let Some(parent) = path.parent() {
            if !parent.as_os_str().is_empty() {
                fs::create_dir_all(parent)?;
            }
        }
        let json = serde_json::to_vec_pretty(self).map_err(io::Error::other)?;
        let tmp = path.with_extension("json.tmp");
        fs::write(&tmp, json)?;
        fs::rename(&tmp, path)?;
        Ok(())
    }

    pub fn load(path: &Path) -> io::Result<Self> {
        let data = fs::read(path)?;
        serde_json::from_slice(&data).map_err(io::Error::other)
    }

    /// Vrai si le checkpoint a été produit avec la même configuration de recherche.
    /// Une différence n'empêche pas la reprise, mais elle est signalée.
    pub fn matches_config(&self, threads: usize, tt_mb: usize) -> bool {
        self.threads == threads && self.tt_mb == tt_mb
    }
}

pub fn now_epoch() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tmp_path(name: &str) -> std::path::PathBuf {
        std::env::temp_dir().join(format!(
            "4mation_cp_{}_{}.json",
            std::process::id(),
            name
        ))
    }

    #[test]
    fn roundtrip_preserves_proven_orbits() {
        let path = tmp_path("roundtrip");
        let mut cp = ProgressCheckpoint::new(8, 512);
        let mut o = OrbitProgress::pending(3, 3);
        o.status = "win".into();
        o.value_for_first = Some(1);
        o.next_depth = 12;
        o.elapsed_sec = 4.5;
        cp.orbits.push(o);
        cp.orbits.push(OrbitProgress::pending(0, 0));
        cp.result = Some(1);
        cp.best = Some([3, 3]);
        cp.updated_at_epoch = now_epoch();

        cp.save(&path).expect("save");
        let back = ProgressCheckpoint::load(&path).expect("load");
        let _ = fs::remove_file(&path);

        assert_eq!(back.version, CHECKPOINT_VERSION);
        assert_eq!(back.result, Some(1));
        assert_eq!(back.best, Some([3, 3]));
        let proven = back.find(3, 3).expect("orbite 3,3");
        assert!(proven.is_proven());
        assert_eq!(proven.value_for_first, Some(1));
        assert_eq!(proven.next_depth, 12);
        assert!(!back.find(0, 0).unwrap().is_proven());
    }

    #[test]
    fn config_mismatch_is_detected() {
        let cp = ProgressCheckpoint::new(16, 1024);
        assert!(cp.matches_config(16, 1024));
        assert!(!cp.matches_config(8, 1024));
        assert!(!cp.matches_config(16, 512));
    }
}
