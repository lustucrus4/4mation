//! Balayage couche par couche : comble les trous de la tablebase.
//!
//! L'explorateur de frontière étend la base vers l'ouverture en partant toujours des
//! positions les plus ouvertes déjà connues. Comme la base s'arrête à la couche 12,
//! il génère les parents de la couche 12 puis monte vers 13, 14, 15… : les couches 8
//! à 11 restent trouées quel que soit le temps de calcul investi.
//!
//! Ce module fait l'inverse, et de façon exhaustive : il prend une couche complète,
//! génère *tous* ses parents, et les résout. Une couche complète en entrée donne une
//! couche complète en sortie.
//!
//! La résolution est immédiate : tous les enfants d'une position de la couche `n + 1`
//! appartiennent à la couche `n`, déjà connue, donc `resolve_via_children` répond sans
//! aucune recherche — quelques microsecondes par position au lieu d'un parcours
//! d'arbre. Le balayage est donc limité par les entrées/sorties, pas par le calcul.

use anyhow::Result;
use rayon::prelude::*;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;
use std::time::Instant;

use crate::explorer::generate_parents;
use crate::game::{board_to_blob, empty_cells, Position};
use crate::local_db::{LocalDb, SolvedRow};
use crate::result_table::ResultTable;
use crate::solver::resolve_via_children;
/// Positions sources lues par page (pagination par clé, sans `OFFSET`).
const PAGE: usize = 20_000;
/// Positions écrites par transaction.
const INSERT_CHUNK: usize = 4_000;

#[derive(Debug, Default, Clone, Copy)]
pub struct SweepStats {
    /// Positions de la couche source parcourues.
    pub children: u64,
    /// Parents générés, doublons compris.
    pub generated: u64,
    /// Positions écrites en base.
    pub inserted: u64,
    /// Parents déjà connus, ignorés (ou déjà cohérents en mode réparation).
    pub known: u64,
    /// Valeurs stockées incohérentes avec les enfants, réécrites (mode `--repair`).
    pub repaired: u64,
    /// Parents dont un enfant manquait : la couche source a un trou.
    pub incomplete: u64,
    pub elapsed_secs: f64,
}

impl SweepStats {
    pub fn rate(&self) -> f64 {
        self.inserted as f64 / self.elapsed_secs.max(0.001)
    }
}

/// Complète la couche `from + 1` à partir de la couche `from`.
///
/// `table` doit contenir au moins la couche `from` ; il est enrichi au fil du balayage,
/// ce qui sert aussi de déduplication globale : une position atteinte depuis plusieurs
/// enfants n'est résolue qu'une fois.
///
/// Avec `force = true` (mode réparation), les positions déjà connues ne sont plus
/// sautées : leur valeur est recalculée depuis les enfants et **réécrite si elle
/// diffère**. C'est le correctif des valeurs restées périmées après la correction d'un
/// enfant — un balayage normal les ignore à jamais, puisqu'elles sont « déjà là ». À
/// lancer **du bas vers le haut** (`--sweep-from 1 --repair`) pour propager les
/// corrections de proche en proche.
pub fn sweep_layer(
    db: &LocalDb,
    from: usize,
    table: &ResultTable,
    force: bool,
) -> Result<SweepStats> {
    let target = from + 1;
    let start = Instant::now();
    let mut cursor = String::new();
    let mut stats = SweepStats::default();

    let source = db.count_at_layer(from).unwrap_or(-1);
    tracing::info!(
        "Balayage : couche {from} → {target}, {source} positions sources{}",
        if force {
            " (réparation : valeurs réécrites si incohérentes)"
        } else {
            ""
        }
    );

    let known = AtomicU64::new(0);
    let incomplete = AtomicU64::new(0);
    let repaired = AtomicU64::new(0);

    loop {
        let page = db.load_layer_page(from, &cursor, PAGE)?;
        if page.is_empty() {
            break;
        }
        cursor = page.last().map(|p| p.0.clone()).unwrap_or(cursor);
        stats.children += page.len() as u64;

        let candidates: Vec<Position> = page
            .par_iter()
                .flat_map_iter(|(_, board, player, last_move, _)| {
                generate_parents(board, *player, *last_move, target).into_iter()
            })
            .collect();
        stats.generated += candidates.len() as u64;

        let rows: Vec<SolvedRow> = candidates
            .par_iter()
            .filter_map(|parent| {
                // Convention du reste de la base : on stocke la position canonique et
                // le meilleur coup exprimé dans ce même repère. `key_for` reproduit
                // exactement la clé de `PositionHasher::hash_key`.
                let (cb, cp, clm) =
                    crate::symmetry::canonical_position(&parent.0, parent.1, parent.2);
                let key = ResultTable::key_for(&cb, cp, clm);
                let existing = table.get(&cb, cp, clm).map(|(result, _)| result);
                if !force && existing.is_some() {
                    known.fetch_add(1, Ordering::Relaxed);
                    return None;
                }
                let Some(solved) = resolve_via_children(&cb, cp, clm, table) else {
                    incomplete.fetch_add(1, Ordering::Relaxed);
                    return None;
                };
                if let Some(previous) = existing {
                    if previous == solved.result {
                        // Déjà cohérent : rien à réécrire, on ne touche pas au disque.
                        known.fetch_add(1, Ordering::Relaxed);
                        return None;
                    }
                    // Valeur périmée (l'enfant a été corrigé après coup) : réécriture.
                    repaired.fetch_add(1, Ordering::Relaxed);
                }
                // Publication immédiate : les doublons suivants voient la valeur à jour.
                table.insert_position(&cb, cp, clm, solved.result, solved.depth_remaining);
                Some(SolvedRow {
                    hash: format!("{key:016x}"),
                    board_blob: board_to_blob(&cb),
                    player: cp,
                    last_move: clm,
                    result: solved.result,
                    win_rate: solved.win_rate,
                    best_move: solved.best_move,
                    depth_remaining: solved.depth_remaining,
                    empty_cells: empty_cells(&cb) as i32,
                })
            })
            .collect();

        stats.inserted += rows.len() as u64;
        for chunk in rows.chunks(INSERT_CHUNK) {
            db.bulk_insert_positions(chunk)?;
        }

        stats.known = known.load(Ordering::Relaxed);
        stats.incomplete = incomplete.load(Ordering::Relaxed);
        stats.repaired = repaired.load(Ordering::Relaxed);
        stats.elapsed_secs = start.elapsed().as_secs_f64();
        tracing::info!(
            "Couche {target} — {}/{} enfants lus, {} résolues ({:.0}/s), {} connues, {} réparées, {} inconnues",
            stats.children,
            source,
            stats.inserted,
            stats.rate(),
            stats.known,
            stats.repaired,
            stats.incomplete
        );
    }

    stats.elapsed_secs = start.elapsed().as_secs_f64();
    Ok(stats)
}

/// Diagnostic : parcourt *toute* la couche et classe les parents irrésolubles en deux
/// familles, car elles n'ont pas la même gravité :
///   - « alias fantôme » : le plateau du parent est résoluble sous un autre dernier coup,
///     donc l'échec ne vient que d'un dernier coup candidat impossible ;
///   - « vrai trou » : aucun dernier coup ne rend le plateau résoluble, donc au moins un
///     enfant réellement jouable manque à la base.
pub fn diagnose(db: &LocalDb, from: usize, limit: usize) -> Result<()> {
    let table = ResultTable::load_from_db(db)?;
    let target = from + 1;
    println!("Table chargée : {} positions", table.len());
    println!("Couche source {from} → parents {target}");

    let mut cursor = String::new();
    let mut scanned = 0u64;
    let mut alias = 0u64;
    let mut holes = 0u64;
    let mut holes_shown = 0usize;
    let mut pages = 0usize;

    loop {
        let page = db.load_layer_page(from, &cursor, PAGE)?;
        if page.is_empty() {
            break;
        }
        cursor = page.last().map(|p| p.0.clone()).unwrap_or(cursor);
        pages += 1;

        for (_, board, player, last_move, _) in &page {
            for parent in generate_parents(board, *player, *last_move, target) {
                scanned += 1;
                let (pb, pp, plm) =
                    crate::symmetry::canonical_position(&parent.0, parent.1, parent.2);
                if resolvable(&table, &pb, pp, plm) {
                    continue;
                }

                // Le plateau est-il résoluble sous un autre dernier coup ?
                let mut other = None;
                for r in 0..crate::game::BOARD_SIZE {
                    for c in 0..crate::game::BOARD_SIZE {
                        if pb[r][c] != 3 - pp {
                            continue;
                        }
                        if resolvable(&table, &pb, pp, Some((r, c))) {
                            other = Some((r, c));
                        }
                    }
                }

                match other {
                    Some(lm) => {
                        alias += 1;
                        tracing::debug!("alias {plm:?} → dernier coup valide {lm:?}");
                    }
                    None => {
                        holes += 1;
                        if holes_shown < limit {
                            holes_shown += 1;
                            println!();
                            println!(
                                "=== VRAI TROU {holes_shown} | joueur {pp} | dernier coup {plm:?} | {} vides",
                                empty_cells(&pb)
                            );
                            println!("{}", render(&pb));
                            for mv in crate::game::frontier_moves(&pb, plm, pp) {
                                if crate::game::is_winning_move(&pb, mv, pp) {
                                    break;
                                }
                                let nb = crate::game::apply_move(&pb, mv, pp);
                                let mark = if table.get(&nb, 3 - pp, Some(mv)).is_some() {
                                    "ok    "
                                } else {
                                    "ABSENT"
                                };
                                println!("    {mark} coup {mv:?}");
                            }
                        }
                    }
                }
            }
        }

        println!(
            "... {pages} pages | {scanned} parents | {alias} alias fantômes | {holes} vrais trous"
        );
    }

    println!();
    println!("BILAN couche {} → {} :", from, target);
    println!("  parents générés      : {scanned}");
    println!("  alias fantômes       : {alias}");
    println!("  vrais trous          : {holes}");
    Ok(())
}

/// Tous les enfants de `board` sont-ils résolubles (donc la position est-elle complète) ?
fn resolvable(
    table: &ResultTable,
    board: &crate::game::Board,
    player: i8,
    last_move: Option<crate::game::Move>,
) -> bool {
    for mv in crate::game::frontier_moves(board, last_move, player) {
        if crate::game::is_winning_move(board, mv, player) {
            return true;
        }
        let nb = crate::game::apply_move(board, mv, player);
        if table.get(&nb, 3 - player, Some(mv)).is_none() {
            return false;
        }
    }
    true
}

/// Vérifie la base : recalcule la valeur de chaque position depuis ses enfants et la
/// compare à la valeur stockée. Trois verdicts :
///   - `ok` : la valeur stockée est cohérente avec les enfants ;
///   - `faux` : elle les contredit — donnée à corriger (voir `--repair`) ;
///   - `indécidable` : au moins un enfant manque. Ces lignes sont soit des alias
///     fantômes (plateau résoluble sous un autre dernier coup, donc inoffensif), soit
///     de vrais trous (position inutilisable).
///
/// La vérification parallélise les lignes d'une même page : c'est de la lecture pure,
/// les compteurs sont atomiques. Sans cela, 30 M de positions prennent plus d'une heure
/// sur un seul cœur, ce qui décourage la re-vérification — et une base qu'on ne
/// revérifie pas dérive.
pub fn verify(db: &LocalDb, layers: std::ops::RangeInclusive<usize>, sample: usize) -> Result<()> {
    let table = ResultTable::load_from_db(db)?;
    println!("Table chargée : {} positions", table.len());

    let mut grand_ok = 0u64;
    let mut grand_faux = 0u64;
    let mut grand_ind = 0u64;
    let mut alias_sample_total = 0u64;
    let mut hole_sample_total = 0u64;
    let mut sampled_total = 0usize;

    for layer in layers {
        let mut cursor = String::new();
        let total = AtomicU64::new(0);
        let ok = AtomicU64::new(0);
        let faux = AtomicU64::new(0);
        let ind = AtomicU64::new(0);
        let shown = AtomicU64::new(0);
        let sampled = AtomicU64::new(0);
        let alias_sample = AtomicU64::new(0);
        let hole_sample = AtomicU64::new(0);
        let samples: Mutex<Vec<String>> = Mutex::new(Vec::new());

        loop {
            let page = db.load_layer_page(layer, &cursor, PAGE)?;
            if page.is_empty() {
                break;
            }
            cursor = page.last().map(|p| p.0.clone()).unwrap_or(cursor);

            page.par_iter().for_each(|(hash, board, player, last_move, stored)| {
                total.fetch_add(1, Ordering::Relaxed);
                let (cb, cp, clm) = crate::symmetry::canonical_position(board, *player, *last_move);
                match resolve_via_children(&cb, cp, clm, &table) {
                    Some(solved) => {
                        let sr = stored.chars().next().unwrap_or('D');
                        if solved.result == sr {
                            ok.fetch_add(1, Ordering::Relaxed);
                        } else {
                            faux.fetch_add(1, Ordering::Relaxed);
                            if shown.fetch_add(1, Ordering::Relaxed) < 5 {
                                if let Ok(mut guard) = samples.lock() {
                                    guard.push(format!(
                                        "  FAUX {hash} : stocké {sr}, recalculé {} ({} vides, joueur {cp})\n{}",
                                        solved.result,
                                        empty_cells(&cb),
                                        render(&cb)
                                    ));
                                }
                            }
                        }
                    }
                    None => {
                        ind.fetch_add(1, Ordering::Relaxed);
                        if sampled.fetch_add(1, Ordering::Relaxed) < sample as u64 {
                            let mut other = false;
                            for r in 0..crate::game::BOARD_SIZE {
                                for c in 0..crate::game::BOARD_SIZE {
                                    if cb[r][c] != 3 - cp {
                                        continue;
                                    }
                                    if resolvable(&table, &cb, cp, Some((r, c))) {
                                        other = true;
                                    }
                                }
                            }
                            if other {
                                alias_sample.fetch_add(1, Ordering::Relaxed);
                            } else {
                                hole_sample.fetch_add(1, Ordering::Relaxed);
                            }
                        }
                    }
                }
            });
        }

        if let Ok(guard) = samples.lock() {
            for line in guard.iter() {
                println!("{line}");
            }
        }

        let total = total.load(Ordering::Relaxed);
        let ok = ok.load(Ordering::Relaxed);
        let faux = faux.load(Ordering::Relaxed);
        let ind = ind.load(Ordering::Relaxed);
        let indecidables = sampled.load(Ordering::Relaxed);
        // Seuls les premiers `sample` indécidables sont réellement triés alias/trou ;
        // annoncer le total donnerait un échantillon bien plus gros qu'il ne l'est.
        let sampled = indecidables.min(sample as u64) as usize;
        let alias_sample = alias_sample.load(Ordering::Relaxed);
        let hole_sample = hole_sample.load(Ordering::Relaxed);

        println!(
            "couche {layer:>2} : {total:>11} lignes | {ok:>11} ok | {faux:>7} faux | {ind:>11} indécidables"
        );
        grand_ok += ok;
        grand_faux += faux;
        grand_ind += ind;
        alias_sample_total += alias_sample;
        hole_sample_total += hole_sample;
        sampled_total += sampled;
    }

    println!();
    println!("BILAN : {grand_ok} ok | {grand_faux} faux | {grand_ind} indécidables");
    if sampled_total > 0 {
        println!(
            "Échantillon de {sampled_total} indécidables (sur {grand_ind}) : {alias_sample_total} alias fantômes, {hole_sample_total} vrais trous"
        );
    }
    Ok(())
}

/// Rendu texte d'un plateau : `.` vide, `X` joueur 1, `O` joueur 2.
fn render(board: &crate::game::Board) -> String {
    use crate::game::BOARD_SIZE;
    let mut s = String::with_capacity(BOARD_SIZE * (BOARD_SIZE + 1));
    for r in 0..BOARD_SIZE {
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
