//! Audit et purge des lignes « fantômes » de la table `positions`.
//!
//! La base contient des états impossibles, hérités d'anciens bugs de génération
//! (cf. `explorer.rs` et `solver_rust/README.md`). Ces lignes ne faussent pas le jeu
//! — un vrai coup s'appuie toujours sur un dernier coup cohérent — mais elles doublent
//! le volume et polluent les statistiques. Ce module les identifie ligne par ligne.
//!
//! Défaut : **DRY-RUN**. Aucune écriture. Le drapeau explicite `--purge-ghosts`
//! déclenche la suppression par lots, dans une transaction par lot.
//!
//! Une ligne est classée dans **une seule** catégorie (la première qui matche, par
//! ordre de gravité), ce qui garantit que le jeu de suppression est un partitionnement
//! exact : pas de double comptage, pas de ligne oubliée.

use std::path::Path;
use std::time::Instant;

use anyhow::Result;

use crate::game::{
    board_from_blob, empty_cells, is_connected, parse_board, Board, Move, BOARD_SIZE,
};
use crate::local_db::{LocalDb, RawPositionRow};

/// Catégorie d'incohérence d'une ligne de `positions`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum GhostKind {
    /// Ni `board_blob` ni `board_json` exploitable : la ligne ne décrit aucune position.
    PlateauAbsent,
    /// `current_player` NULL.
    JoueurAbsent,
    /// `current_player` hors {1, 2}.
    JoueurInvalide,
    /// Une cellule vaut autre chose que 0, 1 ou 2.
    CelluleInvalide,
    /// Un dernier coup est posé sur un plateau vide.
    PlateauVideAvecDernierCoup,
    /// Une seule des deux coordonnées du dernier coup est renseignée.
    DernierCoupPartiel,
    /// Le dernier coup sort du plateau 7×7.
    DernierCoupHorsLimites,
    /// Plateau non vide sans dernier coup (impossible en jeu réel).
    PlateauNonVideSansDernierCoup,
    /// La case du dernier coup est vide.
    DernierCoupCaseVide,
    /// La case du dernier coup ne porte pas un pion de l'adversaire du joueur au trait.
    DernierCoupMauvaiseCouleur,
    /// Plateau vide mais joueur au trait ≠ 1 (le premier coup est toujours au joueur 1).
    PlateauVideJoueurNonInitial,
    /// Le nombre de pions ne respecte pas l'alternance imposée par le joueur au trait.
    ParitePions,
    /// Le plateau n'est pas 8-connexe : un pion isolé n'est jamais atteignable.
    PlateauNonConnexe,
}

impl GhostKind {
    /// Toutes les catégories, dans l'ordre d'affichage du rapport.
    /// (L'ordre de `classify` en diffère sur deux points : une cellule invalide est vue
    /// avant un joueur absent, et les deux cas de plateau vide sont départagés entre eux.)
    pub const ALL: [GhostKind; 13] = [
        GhostKind::PlateauAbsent,
        GhostKind::JoueurAbsent,
        GhostKind::JoueurInvalide,
        GhostKind::CelluleInvalide,
        GhostKind::PlateauVideAvecDernierCoup,
        GhostKind::DernierCoupPartiel,
        GhostKind::DernierCoupHorsLimites,
        GhostKind::PlateauNonVideSansDernierCoup,
        GhostKind::DernierCoupCaseVide,
        GhostKind::DernierCoupMauvaiseCouleur,
        GhostKind::PlateauVideJoueurNonInitial,
        GhostKind::ParitePions,
        GhostKind::PlateauNonConnexe,
    ];

    pub fn index(self) -> usize {
        Self::ALL.iter().position(|&k| k == self).unwrap()
    }

    pub fn label(self) -> &'static str {
        match self {
            GhostKind::PlateauAbsent => "plateau absent",
            GhostKind::JoueurAbsent => "joueur au trait absent",
            GhostKind::JoueurInvalide => "joueur au trait invalide",
            GhostKind::CelluleInvalide => "cellule invalide",
            GhostKind::PlateauVideAvecDernierCoup => "plateau vide avec dernier coup",
            GhostKind::DernierCoupPartiel => "dernier coup partiel",
            GhostKind::DernierCoupHorsLimites => "dernier coup hors limites",
            GhostKind::PlateauNonVideSansDernierCoup => "plateau non vide sans dernier coup",
            GhostKind::DernierCoupCaseVide => "case du dernier coup vide",
            GhostKind::DernierCoupMauvaiseCouleur => "dernier coup de mauvaise couleur",
            GhostKind::PlateauVideJoueurNonInitial => "plateau vide joueur ≠ 1",
            GhostKind::ParitePions => "parité de pions incohérente",
            GhostKind::PlateauNonConnexe => "plateau non connexe",
        }
    }
}

fn decode_board(row: &RawPositionRow) -> Option<Board> {
    if let Some(blob) = &row.board_blob {
        if !blob.is_empty() {
            return Some(board_from_blob(blob));
        }
    }
    if let Some(json) = &row.board_json {
        if !json.is_empty() && json != "null" {
            let value: serde_json::Value = serde_json::from_str(json).unwrap_or(serde_json::Value::Null);
            if value.is_array() {
                return Some(parse_board(&value));
            }
        }
    }
    None
}

fn lm_row_present(row: &RawPositionRow) -> bool {
    row.last_move_row.is_some_and(|v| v >= 0)
}

fn lm_col_present(row: &RawPositionRow) -> bool {
    row.last_move_col.is_some_and(|v| v >= 0)
}

/// Dernier coup décodable et dans les limites du plateau.
fn last_move_of(row: &RawPositionRow) -> Option<Move> {
    match (row.last_move_row, row.last_move_col) {
        (Some(r), Some(c)) if r >= 0 && c >= 0 => {
            let (r, c) = (r as usize, c as usize);
            if r < BOARD_SIZE && c < BOARD_SIZE {
                return Some((r, c));
            }
            None
        }
        _ => None,
    }
}

fn last_move_partial(row: &RawPositionRow) -> bool {
    lm_row_present(row) != lm_col_present(row)
}

fn last_move_any(row: &RawPositionRow) -> bool {
    lm_row_present(row) || lm_col_present(row)
}

/// Classe une ligne. `None` = ligne cohérente.
pub fn classify(row: &RawPositionRow) -> Option<GhostKind> {
    use GhostKind::*;

    let Some(board) = decode_board(row) else {
        return Some(PlateauAbsent);
    };
    for r in 0..BOARD_SIZE {
        for c in 0..BOARD_SIZE {
            let v = board[r][c];
            if !(0..=2).contains(&v) {
                return Some(CelluleInvalide);
            }
        }
    }

    let Some(player) = row.current_player else {
        return Some(JoueurAbsent);
    };
    if player != 1 && player != 2 {
        return Some(JoueurInvalide);
    }
    let player = player as i8;

    if last_move_partial(row) {
        return Some(DernierCoupPartiel);
    }
    if last_move_any(row) && last_move_of(row).is_none() {
        return Some(DernierCoupHorsLimites);
    }
    let last_move = last_move_of(row);

    let n1 = board.iter().flatten().filter(|&&v| v == 1).count();
    let n2 = board.iter().flatten().filter(|&&v| v == 2).count();
    let total = n1 + n2;

    if total == 0 {
        if last_move.is_some() {
            return Some(PlateauVideAvecDernierCoup);
        }
        if player != 1 {
            return Some(PlateauVideJoueurNonInitial);
        }
        return None;
    }

    let Some((lr, lc)) = last_move else {
        return Some(PlateauNonVideSansDernierCoup);
    };
    let piece = board[lr][lc];
    if piece == 0 {
        return Some(DernierCoupCaseVide);
    }
    if piece != 3 - player {
        return Some(DernierCoupMauvaiseCouleur);
    }

    let expected_n1 = if player == 2 { n2 + 1 } else { n2 };
    if n1 != expected_n1 {
        return Some(ParitePions);
    }
    if !is_connected(&board) {
        return Some(PlateauNonConnexe);
    }
    None
}

/// Configuration de l'audit/purge.
pub struct GhostAuditConfig {
    /// `false` = dry-run (défaut), `true` = suppression réelle.
    pub purge: bool,
    /// Nombre maximal de lignes parcourues (0 = toute la table).
    pub limit: u64,
    /// Nombre de lignes affichées en échantillon.
    pub sample: usize,
    /// Hashes par transaction de suppression (borné par la limite SQLite).
    pub batch_delete: usize,
}

impl Default for GhostAuditConfig {
    fn default() -> Self {
        Self {
            purge: false,
            limit: 0,
            sample: 5,
            batch_delete: 500,
        }
    }
}

#[derive(Default)]
pub struct GhostAuditStats {
    pub scanned: u64,
    pub ghosts: u64,
    pub purged: u64,
    pub per_kind: [u64; GhostKind::ALL.len()],
    pub elapsed_secs: f64,
}

impl GhostAuditStats {
    pub fn ghosts_of(&self, kind: GhostKind) -> u64 {
        self.per_kind[kind.index()]
    }
}

/// Parcourt `positions` (pagination par clé), classe chaque ligne et, si `purge`,
/// supprime les fantômes par lots transactionnels. Retourne le bilan.
pub fn run_ghost_audit(db: &LocalDb, cfg: &GhostAuditConfig) -> Result<GhostAuditStats> {
    const PAGE: usize = 20_000;
    let start = Instant::now();
    let mut stats = GhostAuditStats::default();
    let mut samples: Vec<String> = Vec::new();
    let mut cursor = String::new();
    let mut last_log = Instant::now();

    loop {
        if cfg.limit != 0 && stats.scanned >= cfg.limit {
            break;
        }
        let page = db.page_positions_raw(&cursor, PAGE)?;
        if page.is_empty() {
            break;
        }
        cursor = page.last().map(|r| r.hash.clone()).unwrap_or(cursor);

        let mut to_delete: Vec<String> = Vec::new();
        for row in &page {
            if cfg.limit != 0 && stats.scanned >= cfg.limit {
                break;
            }
            stats.scanned += 1;
            let Some(kind) = classify(row) else {
                continue;
            };
            stats.ghosts += 1;
            stats.per_kind[kind.index()] += 1;
            if samples.len() < cfg.sample {
                samples.push(format_sample(row, kind));
            }
            if cfg.purge {
                to_delete.push(row.hash.clone());
            }
        }

        if cfg.purge && !to_delete.is_empty() {
            let batch = cfg.batch_delete.clamp(1, 900);
            for chunk in to_delete.chunks(batch) {
                stats.purged += db.delete_positions_batch(chunk)? as u64;
            }
        }

        if last_log.elapsed().as_secs_f64() >= 5.0 {
            tracing::info!(
                "audit fantômes — {} lignes lues, {} fantômes{}",
                stats.scanned,
                stats.ghosts,
                if cfg.purge {
                    format!(", {} supprimées", stats.purged)
                } else {
                    String::new()
                }
            );
            last_log = Instant::now();
        }
    }

    stats.elapsed_secs = start.elapsed().as_secs_f64();
    print_report(&stats, &samples, cfg);
    Ok(stats)
}

fn format_sample(row: &RawPositionRow, kind: GhostKind) -> String {
    let board = decode_board(row);
    let player = row
        .current_player
        .map(|p| p.to_string())
        .unwrap_or_else(|| "NULL".into());
    let last = match last_move_of(row) {
        Some((r, c)) => format!("({r},{c})"),
        None => match (row.last_move_row, row.last_move_col) {
            (None, None) => "aucun".into(),
            (r, c) => format!("({:?},{:?})", r, c),
        },
    };
    let empties = board.as_ref().map(empty_cells).unwrap_or(0);
    let mut out = format!(
        "  hash={} | {} | joueur={} | dernier coup={} | {} vides",
        row.hash,
        kind.label(),
        player,
        last,
        empties
    );
    if let Some(b) = board {
        out.push('\n');
        out.push_str(&render(&b));
    }
    out
}

/// Rendu texte d'un plateau : `.` vide, `X` joueur 1, `O` joueur 2.
fn render(board: &Board) -> String {
    let mut s = String::with_capacity(BOARD_SIZE * (BOARD_SIZE + 1) + 2);
    for r in 0..BOARD_SIZE {
        s.push_str("    ");
        for c in 0..BOARD_SIZE {
            s.push(match board[r][c] {
                1 => 'X',
                2 => 'O',
                _ => '.',
            });
        }
        s.push('\n');
    }
    s
}

fn print_report(stats: &GhostAuditStats, samples: &[String], cfg: &GhostAuditConfig) {
    let mode = if cfg.purge { "PURGE" } else { "DRY-RUN" };
    let limit = if cfg.limit == 0 {
        "toute la table".to_string()
    } else {
        format!("limite {} lignes", cfg.limit)
    };
    println!();
    println!("===== Audit lignes fantômes ({mode}) — {limit} =====");
    println!("Positions parcourues : {}", stats.scanned);
    println!(
        "Lignes fantômes      : {} ({:.2} %)",
        stats.ghosts,
        if stats.scanned == 0 {
            0.0
        } else {
            100.0 * stats.ghosts as f64 / stats.scanned as f64
        }
    );
    if cfg.purge {
        println!("Lignes supprimées    : {}", stats.purged);
    }
    println!("Durée                : {:.1} s", stats.elapsed_secs);
    println!("Détail par catégorie :");
    for kind in GhostKind::ALL {
        let n = stats.ghosts_of(kind);
        if n > 0 {
            println!("  {:<38} {:>12}", kind.label(), n);
        }
    }
    if !samples.is_empty() {
        println!();
        println!("Échantillon :");
        for s in samples {
            println!("{s}");
        }
    }
    println!("=======================================================");
    println!();
}

/// Ouvre la base (lecture seule en dry-run) et lance l'audit.
pub fn run_and_report(path: &Path, cfg: &GhostAuditConfig) -> Result<GhostAuditStats> {
    let db = if cfg.purge {
        LocalDb::open(path)?
    } else {
        LocalDb::open_readonly(path)?
    };
    run_ghost_audit(&db, cfg)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn row(
        board: Board,
        player: Option<i32>,
        lmr: Option<i32>,
        lmc: Option<i32>,
    ) -> RawPositionRow {
        RawPositionRow {
            hash: "0".repeat(16),
            board_blob: Some(crate::game::board_to_blob(&board)),
            board_json: None,
            current_player: player,
            last_move_row: lmr,
            last_move_col: lmc,
        }
    }

    #[test]
    fn empty_board_first_move_is_clean() {
        let b = [[0i8; BOARD_SIZE]; BOARD_SIZE];
        assert_eq!(classify(&row(b, Some(1), None, None)), None);
    }

    #[test]
    fn empty_board_with_last_move_is_ghost() {
        let b = [[0i8; BOARD_SIZE]; BOARD_SIZE];
        assert_eq!(
            classify(&row(b, Some(1), Some(3), Some(3))),
            Some(GhostKind::PlateauVideAvecDernierCoup)
        );
    }

    #[test]
    fn non_empty_without_last_move_is_ghost() {
        let mut b = [[0i8; BOARD_SIZE]; BOARD_SIZE];
        b[3][3] = 1;
        assert_eq!(
            classify(&row(b, Some(2), None, None)),
            Some(GhostKind::PlateauNonVideSansDernierCoup)
        );
    }

    #[test]
    fn wrong_color_last_move_is_ghost() {
        // Un seul pion du joueur 1, mais c'est au joueur 1 de jouer : le dernier coup
        // appartiendrait à l'adversaire, donc la couleur est fausse.
        let mut b = [[0i8; BOARD_SIZE]; BOARD_SIZE];
        b[3][3] = 1;
        assert_eq!(
            classify(&row(b, Some(1), Some(3), Some(3))),
            Some(GhostKind::DernierCoupMauvaiseCouleur)
        );
    }

    #[test]
    fn legal_two_moves_position_is_clean() {
        // X(3,3) puis O(3,4), au joueur 1 : parité 1/1, dernier coup O, connexe.
        let mut b = [[0i8; BOARD_SIZE]; BOARD_SIZE];
        b[3][3] = 1;
        b[3][4] = 2;
        assert_eq!(classify(&row(b, Some(1), Some(3), Some(4))), None);
    }

    #[test]
    fn parity_mismatch_is_ghost() {
        // Deux pions X et un pion O avec joueur 1 au trait : impossible.
        let mut b = [[0i8; BOARD_SIZE]; BOARD_SIZE];
        b[3][3] = 1;
        b[3][4] = 1;
        b[2][3] = 2;
        assert_eq!(
            classify(&row(b, Some(1), Some(2), Some(3))),
            Some(GhostKind::ParitePions)
        );
    }

    #[test]
    fn disconnected_board_is_ghost() {
        // Parité correcte (X=1, O=1, joueur 1) mais les deux pions ne se touchent pas.
        let mut b = [[0i8; BOARD_SIZE]; BOARD_SIZE];
        b[0][0] = 1;
        b[6][6] = 2;
        assert_eq!(
            classify(&row(b, Some(1), Some(6), Some(6))),
            Some(GhostKind::PlateauNonConnexe)
        );
    }

    #[test]
    fn missing_player_is_ghost() {
        let mut b = [[0i8; BOARD_SIZE]; BOARD_SIZE];
        b[3][3] = 1;
        assert_eq!(
            classify(&row(b, None, Some(3), Some(3))),
            Some(GhostKind::JoueurAbsent)
        );
    }

    #[test]
    fn absent_board_is_ghost() {
        let mut r = row([[0i8; BOARD_SIZE]; BOARD_SIZE], Some(1), None, None);
        r.board_blob = None;
        r.board_json = None;
        assert_eq!(classify(&r), Some(GhostKind::PlateauAbsent));
    }

    #[test]
    fn partial_last_move_is_ghost() {
        let mut b = [[0i8; BOARD_SIZE]; BOARD_SIZE];
        b[3][3] = 1;
        b[3][4] = 2;
        assert_eq!(
            classify(&row(b, Some(1), Some(3), None)),
            Some(GhostKind::DernierCoupPartiel)
        );
    }

    #[test]
    fn out_of_bounds_last_move_is_ghost() {
        let mut b = [[0i8; BOARD_SIZE]; BOARD_SIZE];
        b[3][3] = 1;
        b[3][4] = 2;
        assert_eq!(
            classify(&row(b, Some(1), Some(9), Some(4))),
            Some(GhostKind::DernierCoupHorsLimites)
        );
    }
}
