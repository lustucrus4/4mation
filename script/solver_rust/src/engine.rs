//! Moteur de jeu : recherche alpha-bêta avec table de transposition.
//!
//! Deux usages :
//! - bot : meilleur coup dans un temps imparti ;
//! - analyse : valeur de chaque coup, avec le drapeau `exact` quand la
//!   recherche n'a pas coupé la branche.
//!
//! Convention de score « mat en N » : une victoire vaut `WIN - ply`, une
//! défaite `-(WIN - ply)`. Un gain rapide marque donc plus qu'un gain tardif,
//! et une défaite lointaine marque plus qu'une défaite immédiate — l'algorithme
//! choisit naturellement le gain le plus court et la résistance la plus longue.
//! Les scores heuristiques restent très en dessous de `MATE_MARGIN`.

use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, Instant};

use crate::proof::{
    canon_key, collect_moves, empty_hashes, has_four, idx, mask_start, move_mask, prune_symmetric,
    sort_moves, tt_key, MoveBuf, CELLS, N,
};

/// Score d'une victoire immédiate (moins la distance en demi-coups).
pub const WIN: i32 = 100_000;
const INF: i32 = 1_000_000;
/// Au-delà de ce seuil, le score décrit un mat forcé, pas une estimation.
pub const MATE_MARGIN: i32 = WIN - 200;

const BOUND_EXACT: u8 = 0;
const BOUND_LOWER: u8 = 1;
const BOUND_UPPER: u8 = 2;

// Masques de départ des suites de 3 et de 2, par direction.
// Ils empêchent une suite de traverser le bord et de compter pour un alignement.
const H3: u64 = mask_start(6, 0, 4);
const V3: u64 = mask_start(4, 0, 6);
const D3: u64 = mask_start(4, 0, 4);
const A3: u64 = mask_start(4, 2, 6);
const H2: u64 = mask_start(6, 0, 5);
const V2: u64 = mask_start(5, 0, 6);
const D2: u64 = mask_start(5, 0, 5);
const A2: u64 = mask_start(5, 2, 6);

/// Valeur d'une case selon sa distance au centre. Le centre laisse le plus de
/// place aux suites futures ; les bords et les coins enferment la frontière.
const CENTRE: [i32; CELLS] = centre_weights();

const fn centre_weights() -> [i32; CELLS] {
    let mut w = [0i32; CELLS];
    let mut r = 0;
    while r < N {
        let mut c = 0;
        while c < N {
            let dr = if r > 3 { r - 3 } else { 3 - r };
            let dc = if c > 3 { c - 3 } else { 3 - c };
            w[idx(r, c)] = 6 - (dr + dc) as i32;
            c += 1;
        }
        r += 1;
    }
    w
}

/// Sonde de finale exacte (tablebase). `wdl` renvoie la valeur du point de vue
/// du joueur au trait : 1 victoire, 0 nulle, -1 défaite.
pub trait Probe: Send + Sync {
    fn wdl(&self, p1: u64, p2: u64, side: u8, last: u8) -> Option<i8>;
    /// Meilleur coup enregistré, s'il est connu.
    fn best(&self, _p1: u64, _p2: u64, _side: u8, _last: u8) -> Option<u8> {
        None
    }
}

/// Clé canonique d'une position, au format de la tablebase SQLite.
pub fn position_key(p1: u64, p2: u64, side: u8, last: u8) -> u64 {
    let (e1, e2) = empty_hashes();
    canon_key(p1, p2, side, last, e1, e2)
}

#[inline]
fn popcount(x: u64) -> i32 {
    x.count_ones() as i32
}

/// Pions alignés : suites de 3 et de 2, bords exclus.
#[inline]
fn line_score(bits: u64) -> i32 {
    let three = popcount((bits & (bits >> 1) & (bits >> 2)) & H3)
        + popcount((bits & (bits >> 7) & (bits >> 14)) & V3)
        + popcount((bits & (bits >> 8) & (bits >> 16)) & D3)
        + popcount((bits & (bits >> 6) & (bits >> 12)) & A3);
    let two = popcount((bits & (bits >> 1)) & H2)
        + popcount((bits & (bits >> 7)) & V2)
        + popcount((bits & (bits >> 8)) & D2)
        + popcount((bits & (bits >> 6)) & A2);
    three * 14 + two * 2
}

/// Nombre de coups disponibles qui complètent un alignement de 4.
/// Le masque de coups fait au plus 8 cases, ce test reste très court.
#[inline]
fn threats(player: u64, mask: u64) -> i32 {
    let mut n = 0;
    let mut b = mask;
    while b != 0 {
        let i = b.trailing_zeros();
        b &= b - 1;
        if has_four(player | (1u64 << i)) {
            n += 1;
        }
    }
    n
}

/// Évaluation heuristique, du point de vue du joueur au trait.
#[inline]
fn evaluate(p1: u64, p2: u64, side: u8, last: u8) -> i32 {
    let my = if side == 1 { p1 } else { p2 };
    let opp = if side == 1 { p2 } else { p1 };
    let mask = move_mask(p1, p2, side, last);
    // Une menace immédiate pèse plus que tout le reste : deux menaces
    // simultanées ne se bloquent pas d'un seul coup.
    let menaces = threats(my, mask) - threats(opp, mask);
    let lignes = line_score(my) - line_score(opp);
    let place = centralite(my) - centralite(opp);
    menaces * 60 + lignes + place * 3
}

/// Somme de la valeur de position des pions : le centre vaut plus que le bord.
#[inline]
fn centralite(bits: u64) -> i32 {
    let mut total = 0;
    let mut b = bits;
    while b != 0 {
        let i = b.trailing_zeros() as usize;
        b &= b - 1;
        total += CENTRE[i];
    }
    total
}

struct TtEntry {
    score: i32,
    depth: i16,
    bound: u8,
    mv: Option<u8>,
}

/// Table de transposition à deux mots par case.
///
/// `keys[i]` garde les bits hauts de la clé (tag), `data[i]` le reste.
/// L'index est les bits bas : tag + index reconstituent la clé, donc aucune
/// collision ne peut produire un faux positif. Une collision écrase l'entrée,
/// ce qui reste sûr — la position sera simplement recalculée.
pub(crate) struct Tt {
    keys: Vec<AtomicU64>,
    data: Vec<AtomicU64>,
    index_mask: u64,
    shift: u32,
    empty_p1: u64,
    empty_p2: u64,
}

const D_VALID: u64 = 1;
const D_MOVE_SHIFT: u32 = 1;
const D_DEPTH_SHIFT: u32 = 7;
const D_BOUND_SHIFT: u32 = 15;
const D_SCORE_SHIFT: u32 = 17;

impl Tt {
    pub fn new(tt_mb: usize) -> Self {
        let bytes = tt_mb.max(1) as u64 * 1024 * 1024;
        let mut entries = (bytes / 16).next_power_of_two();
        if entries < 1024 {
            entries = 1024;
        }
        let mut keys = Vec::with_capacity(entries as usize);
        let mut data = Vec::with_capacity(entries as usize);
        for _ in 0..entries {
            keys.push(AtomicU64::new(0));
            data.push(AtomicU64::new(0));
        }
        Self {
            keys,
            data,
            index_mask: entries - 1,
            // 64 bits de tag stockés à part : aucun risque de débordement.
            shift: entries.trailing_zeros(),
            empty_p1: empty_hashes().0,
            empty_p2: empty_hashes().1,
        }
    }

    /// Nombre de cases allouées.
    pub(crate) fn capacity(&self) -> usize {
        self.keys.len()
    }

    #[inline]
    fn slot(&self, key: u64) -> (usize, u64) {
        ((key & self.index_mask) as usize, key >> self.shift)
    }

    #[inline]
    fn probe(&self, key: u64) -> Option<TtEntry> {
        let (i, tag) = self.slot(key);
        if self.keys[i].load(Ordering::Acquire) != tag || tag == 0 {
            return None;
        }
        let raw = self.data[i].load(Ordering::Acquire);
        if raw & D_VALID == 0 {
            return None;
        }
        let mv = ((raw >> D_MOVE_SHIFT) & 0x3f) as u8;
        Some(TtEntry {
            score: (raw >> D_SCORE_SHIFT) as u32 as i32,
            depth: ((raw >> D_DEPTH_SHIFT) & 0xff) as i16,
            bound: ((raw >> D_BOUND_SHIFT) & 0x3) as u8,
            mv: if mv == 0 { None } else { Some(mv - 1) },
        })
    }

    #[inline]
    pub(crate) fn store(&self, key: u64, score: i32, depth: i16, bound: u8, mv: Option<u8>) {
        let (i, tag) = self.slot(key);
        if tag == 0 {
            return;
        }
        let old_tag = self.keys[i].load(Ordering::Acquire);
        if old_tag == tag {
            let old_depth = ((self.data[i].load(Ordering::Acquire) >> D_DEPTH_SHIFT) & 0xff) as i16;
            if old_depth > depth {
                return;
            }
        }
        let raw = D_VALID
            | (((mv.map(|m| m + 1).unwrap_or(0)) as u64) << D_MOVE_SHIFT)
            | ((depth as u64 & 0xff) << D_DEPTH_SHIFT)
            | ((bound as u64) << D_BOUND_SHIFT)
            | (((score as u32) as u64) << D_SCORE_SHIFT);
        self.keys[i].store(tag, Ordering::Release);
        self.data[i].store(raw, Ordering::Release);
    }
}

/// Score stocké : distance au mat rendue indépendante de la profondeur atteinte.
#[inline]
fn to_tt(score: i32, ply: i32) -> i32 {
    if score > MATE_MARGIN {
        score + ply
    } else if score < -MATE_MARGIN {
        score - ply
    } else {
        score
    }
}

#[inline]
fn from_tt(score: i32, ply: i32) -> i32 {
    if score > MATE_MARGIN {
        score - ply
    } else if score < -MATE_MARGIN {
        score + ply
    } else {
        score
    }
}

#[derive(Clone, Debug)]
pub struct MoveScore {
    pub mv: u8,
    /// Score après ce coup, du point de vue du joueur au trait.
    pub score: i32,
    /// `false` si le coup n'a pas été recherché en fenêtre pleine : le score est
    /// alors une borne supérieure, pas la valeur exacte.
    pub exact: bool,
}

#[derive(Debug)]
pub struct SearchResult {
    pub best: Option<u8>,
    /// Score de la position, du point de vue du joueur au trait.
    pub score: i32,
    /// Profondeur réellement terminée.
    pub depth: i16,
    pub nodes: u64,
    pub elapsed: Duration,
    /// `true` si la recherche s'est arrêtée au temps imparti sans finir.
    pub truncated: bool,
    pub moves: Vec<MoveScore>,
    /// Valeur exacte du résultat, quand elle est prouvée : mat forcé, ou lecture
    /// de la tablebase (une nulle exacte est une vraie information, elle ne doit
    /// pas être confondue avec « on ne sait pas »).
    pub proven_wdl: Option<i8>,
}

impl SearchResult {
    /// Résultat forcé, uniquement s'il est prouvé. `None` signifie « pas de
    /// preuve » : ce n'est pas une nulle, seulement une absence de résultat.
    pub fn wdl(&self) -> Option<i8> {
        self.proven_wdl
    }

    pub fn proven(&self) -> bool {
        self.proven_wdl.is_some()
    }

    /// Victoire forcée en ce nombre de demi-coups, si prouvée.
    pub fn mate_in(&self) -> Option<i32> {
        if self.score >= MATE_MARGIN {
            Some(WIN - self.score)
        } else if self.score <= -MATE_MARGIN {
            Some(WIN + self.score)
        } else {
            None
        }
    }
}

pub struct EngineConfig {
    pub tt_mb: usize,
    pub max_depth: i16,
    /// 0 = pas de limite de temps.
    pub time_ms: u64,
}

impl Default for EngineConfig {
    fn default() -> Self {
        Self {
            tt_mb: 128,
            max_depth: 32,
            time_ms: 1000,
        }
    }
}

pub struct Engine {
    cfg: EngineConfig,
    tt: Tt,
    probe: Option<Box<dyn Probe>>,
    /// Nombre de cases vides en dessous duquel la tablebase est consultée.
    probe_max_empty: usize,
    nodes: u64,
    deadline: Option<Instant>,
    stop: bool,
    skips: u64,
    exact_root: bool,
    all_root_moves: bool,
}

impl Engine {
    pub fn new(cfg: EngineConfig) -> Self {
        let tt = Tt::new(cfg.tt_mb);
        Self {
            cfg,
            tt,
            probe: None,
            probe_max_empty: 0,
            nodes: 0,
            deadline: None,
            stop: false,
            skips: 0,
            exact_root: false,
            all_root_moves: false,
        }
    }

    /// Quand il est actif, chaque coup de la racine est recherché en fenêtre
    /// pleine : les scores de tous les coups deviennent exacts, au prix d'une
    /// recherche plus lente. C'est le mode nécessaire à l'analyse d'une partie
    /// et à la construction de la théorie, où l'on veut comparer les coups
    /// entre eux et pas seulement connaître le meilleur.
    pub fn set_exact_root(&mut self, on: bool) {
        self.exact_root = on;
    }

    /// Quand il est actif, la racine n'est plus réduite par symétrie : le moteur
    /// rend un score pour **chaque** coup légal.
    ///
    /// L'élagage des coups symétriques de la racine est correct — deux coups
    /// symétriques ont la même valeur — mais il fait disparaître des coups de la
    /// liste. Un bot s'en moque (il ne joue que le meilleur), une interface
    /// d'analyse non : elle doit afficher les 49 coups du premier tour, pas les
    /// 10 orbites. Coût : une racine jusqu'à dix fois plus large, donc une
    /// profondeur atteinte plus faible à budget égal. L'élagage reste actif dans
    /// toute la recherche, en dessous de la racine.
    pub fn set_all_root_moves(&mut self, on: bool) {
        self.all_root_moves = on;
    }

    pub fn set_probe(&mut self, probe: Box<dyn Probe>, max_empty: usize) {
        self.probe = Some(probe);
        self.probe_max_empty = max_empty;
    }

    /// Change les limites pour la prochaine recherche sans reconstruire le moteur
    /// (la table de transposition est conservée).
    pub fn set_limits(&mut self, max_depth: i16, time_ms: u64) {
        self.cfg.max_depth = max_depth;
        self.cfg.time_ms = time_ms;
    }

    pub fn tt_capacity(&self) -> usize {
        self.tt.capacity()
    }

    /// Nombre d'appels à la tablebase ayant évité une recherche.
    pub fn skips(&self) -> u64 {
        self.skips
    }

    #[inline]
    fn time_up(&mut self) -> bool {
        if self.stop {
            return true;
        }
        if let Some(d) = self.deadline {
            if Instant::now() >= d {
                self.stop = true;
                return true;
            }
        }
        false
    }

    pub fn search(&mut self, p1: u64, p2: u64, side: u8, last: u8) -> SearchResult {
        self.nodes = 0;
        self.skips = 0;
        self.stop = false;
        self.deadline = if self.cfg.time_ms == 0 {
            None
        } else {
            Some(Instant::now() + Duration::from_millis(self.cfg.time_ms))
        };
        let start = Instant::now();

        // Finale déjà résolue : la tablebase donne le coup et la valeur exacte
        // sans aucune recherche.
        if let Some(pr) = &self.probe {
            let occ = p1 | p2;
            if CELLS - occ.count_ones() as usize <= self.probe_max_empty {
                if let Some(v) = pr.wdl(p1, p2, side, last) {
                    self.skips += 1;
                    let score = match v {
                        1 => WIN - 1,
                        -1 => -(WIN - 1),
                        _ => 0,
                    };
                    let best = pr.best(p1, p2, side, last).filter(|m| {
                        move_mask(p1, p2, side, last) & (1u64 << *m) != 0
                    });
                    return SearchResult {
                        best,
                        score,
                        depth: 0,
                        nodes: 0,
                        elapsed: start.elapsed(),
                        truncated: false,
                        moves: best
                            .map(|m| {
                                vec![MoveScore {
                                    mv: m,
                                    score,
                                    exact: true,
                                }]
                            })
                            .unwrap_or_default(),
                        proven_wdl: Some(v),
                    };
                }
            }
        }

        let mut best: Option<u8> = None;
        let mut score = 0;
        let mut moves: Vec<MoveScore> = Vec::new();
        let mut depth_done: i16 = 0;
        let mut truncated = false;

        let mut depth: i16 = 1;
        while depth <= self.cfg.max_depth {
            let (best_d, score_d, list_d) = self.search_root(p1, p2, side, last, depth);
            if self.stop {
                truncated = true;
                break;
            }
            best = best_d;
            score = score_d;
            moves = list_d;
            depth_done = depth;
            // Un mat forcé est trouvé : inutile de descendre plus loin.
            if score.abs() >= MATE_MARGIN {
                break;
            }
            depth += 1;
        }

        // Un mat forcé est une preuve ; une estimation n'en est pas une.
        let proven_wdl = if score >= MATE_MARGIN {
            Some(1)
        } else if score <= -MATE_MARGIN {
            Some(-1)
        } else {
            None
        };

        SearchResult {
            best,
            score,
            depth: depth_done,
            nodes: self.nodes,
            elapsed: start.elapsed(),
            truncated,
            moves,
            proven_wdl,
        }
    }

    /// Renvoie (meilleur coup, score, détail par coup).
    fn search_root(
        &mut self,
        p1: u64,
        p2: u64,
        side: u8,
        last: u8,
        depth: i16,
    ) -> (Option<u8>, i32, Vec<MoveScore>) {
        let my = if side == 1 { p1 } else { p2 };
        let opp = if side == 1 { p2 } else { p1 };
        let mask = move_mask(p1, p2, side, last);
        if mask == 0 {
            // Aucun coup jouable : le joueur au trait perd, comme dans le solveur.
            return (None, -(WIN), Vec::new());
        }
        let mut buf: MoveBuf = collect_moves(mask);
        sort_moves(&mut buf, my, opp);
        if !self.all_root_moves {
            prune_symmetric(&mut buf, p1, p2, last);
        }

        let key = tt_key(p1, p2, side, last, self.tt.empty_p1, self.tt.empty_p2);
        if let Some(e) = self.tt.probe(key) {
            if let Some(tm) = e.mv {
                for i in 0..buf.n {
                    if buf.m[i] == tm {
                        buf.m.swap(0, i);
                        break;
                    }
                }
            }
        }

        let mut alpha = -INF;
        let mut best: Option<u8> = None;
        let mut list: Vec<MoveScore> = Vec::with_capacity(buf.n);
        let mut aborted = false;

        for i in 0..buf.n {
            let mv = buf.m[i];
            let bit = 1u64 << mv;
            let score = if has_four(my | bit) {
                WIN - 1
            } else {
                let (c1, c2) = if side == 1 {
                    (p1 | bit, p2)
                } else {
                    (p1, p2 | bit)
                };
                // Fenêtre pleine en mode analyse : aucune coupure entre coups de
                // la racine, donc un score exact pour chacun.
                let beta = if self.exact_root { INF } else { -alpha };
                let s = -self.negamax(c1, c2, 3 - side, mv, depth - 1, -INF, beta, 1);
                if self.stop {
                    aborted = true;
                    break;
                }
                s
            };
            let exact = self.exact_root || score > alpha;
            if score > alpha {
                alpha = score;
                best = Some(mv);
            }
            list.push(MoveScore { mv, score, exact });
        }

        if !aborted && best.is_some() {
            self.tt
                .store(key, to_tt(alpha, 0), depth, BOUND_EXACT, best);
        }
        (best, alpha, list)
    }

    fn negamax(
        &mut self,
        p1: u64,
        p2: u64,
        side: u8,
        last: u8,
        depth: i16,
        alpha: i32,
        beta: i32,
        ply: i32,
    ) -> i32 {
        self.nodes += 1;
        if self.nodes & 1023 == 0 && self.time_up() {
            return alpha;
        }
        if self.stop {
            return alpha;
        }

        let my = if side == 1 { p1 } else { p2 };
        let opp = if side == 1 { p2 } else { p1 };
        if has_four(opp) {
            return -(WIN - ply);
        }
        if has_four(my) {
            return WIN - ply;
        }
        let occ = p1 | p2;
        let stones = occ.count_ones() as usize;
        if stones == CELLS {
            return 0;
        }
        let mask = move_mask(p1, p2, side, last);
        if mask == 0 {
            return -(WIN - ply);
        }

        if let Some(pr) = &self.probe {
            if CELLS - stones <= self.probe_max_empty {
                if let Some(v) = pr.wdl(p1, p2, side, last) {
                    self.skips += 1;
                    return match v {
                        1 => WIN - ply,
                        -1 => -(WIN - ply),
                        _ => 0,
                    };
                }
            }
        }

        if depth <= 0 {
            return evaluate(p1, p2, side, last);
        }

        let key = tt_key(p1, p2, side, last, self.tt.empty_p1, self.tt.empty_p2);
        let mut tt_move = None;
        if let Some(e) = self.tt.probe(key) {
            tt_move = e.mv;
            if e.depth >= depth {
                let s = from_tt(e.score, ply);
                match e.bound {
                    BOUND_EXACT => return s,
                    BOUND_LOWER if s >= beta => return s,
                    BOUND_UPPER if s <= alpha => return s,
                    _ => {}
                }
            }
        }

        let mut buf = collect_moves(mask);
        sort_moves(&mut buf, my, opp);
        prune_symmetric(&mut buf, p1, p2, last);
        if let Some(tm) = tt_move {
            for i in 0..buf.n {
                if buf.m[i] == tm {
                    buf.m.swap(0, i);
                    break;
                }
            }
        }

        let mut best = -INF;
        let mut best_mv: Option<u8> = None;
        let mut bound = BOUND_UPPER;
        let mut a = alpha;

        for i in 0..buf.n {
            let mv = buf.m[i];
            let bit = 1u64 << mv;
            let score = if has_four(my | bit) {
                WIN - (ply + 1)
            } else {
                let (c1, c2) = if side == 1 {
                    (p1 | bit, p2)
                } else {
                    (p1, p2 | bit)
                };
                let s = -self.negamax(c1, c2, 3 - side, mv, depth - 1, -beta, -a, ply + 1);
                if self.stop {
                    return alpha;
                }
                s
            };

            if score > best {
                best = score;
                best_mv = Some(mv);
            }
            if score > a {
                a = score;
                bound = BOUND_EXACT;
            }
            if a >= beta {
                bound = BOUND_LOWER;
                break;
            }
        }

        // Une entrée plus profonde est plus fiable : on ne l'écrase pas.
        if best_mv.is_some() {
            self.tt
                .store(key, to_tt(best, ply), depth, bound, best_mv);
        }
        best
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::proof::{collect_moves, idx};

    fn bit(r: usize, c: usize) -> u64 {
        1u64 << idx(r, c)
    }

    fn engine(depth: i16) -> Engine {
        Engine::new(EngineConfig {
            tt_mb: 8,
            max_depth: depth,
            time_ms: 0,
        })
    }

    /// Minimax naïf : aucune table de transposition, aucune coupure alpha-bêta,
    /// aucun élagage de symétrie. Sert de référence absolue — il est assez lent
    /// pour être évidemment correct, et c'est le seul juge fiable du moteur.
    fn naive(p1: u64, p2: u64, side: u8, last: u8, depth: i16, ply: i32) -> i32 {
        let my = if side == 1 { p1 } else { p2 };
        let opp = if side == 1 { p2 } else { p1 };
        if has_four(opp) {
            return -(WIN - ply);
        }
        if has_four(my) {
            return WIN - ply;
        }
        if (p1 | p2).count_ones() as usize == CELLS {
            return 0;
        }
        let mask = move_mask(p1, p2, side, last);
        if mask == 0 {
            return -(WIN - ply);
        }
        if depth <= 0 {
            return evaluate(p1, p2, side, last);
        }
        let buf = collect_moves(mask);
        let mut best = -INF;
        for i in 0..buf.n {
            let mv = buf.m[i];
            let b = 1u64 << mv;
            let s = if has_four(my | b) {
                WIN - (ply + 1)
            } else {
                let (c1, c2) = if side == 1 {
                    (p1 | b, p2)
                } else {
                    (p1, p2 | b)
                };
                -naive(c1, c2, 3 - side, mv, depth - 1, ply + 1)
            };
            if s > best {
                best = s;
            }
        }
        best
    }

    /// Positions de référence : ouverture, début de milieu de partie, tactique.
    fn reference_positions() -> Vec<((u64, u64, u8, u8), i16)> {
        let centre = idx(3, 3) as u8;
        vec![
            // Plateau vide : les deux camps découvrent.
            ((0, 0, 1, 255), 3),
            // Après le premier coup au centre.
            ((bit(3, 3), 0, 2, centre), 4),
            // Milieu de partie : les deux joueurs ont bâti une diagonale.
            (
                (
                    bit(3, 3) | bit(2, 3) | bit(4, 4) | bit(1, 2),
                    bit(3, 4) | bit(2, 4) | bit(4, 3) | bit(1, 3),
                    1,
                    idx(1, 3) as u8,
                ),
                5,
            ),
            // Menace de gain immédiat pour le joueur au trait.
            ((bit(3, 1) | bit(3, 2) | bit(3, 3), bit(2, 3), 1, idx(2, 3) as u8), 4),
        ]
    }

    #[test]
    fn trouve_un_gain_immediat() {
        // Joueur 1 aligne (3,1) (3,2) (3,3) ; le dernier coup adverse (2,3)
        // rend (3,4) jouable et complète l'alignement.
        let p1 = bit(3, 1) | bit(3, 2) | bit(3, 3);
        let p2 = bit(2, 3);
        let mut e = engine(6);
        let r = e.search(p1, p2, 1, idx(2, 3) as u8);
        assert_eq!(r.best, Some(idx(3, 4) as u8), "le gain en un coup doit être trouvé");
        assert!(r.score >= MATE_MARGIN);
        assert_eq!(r.wdl(), Some(1));
        assert_eq!(r.mate_in(), Some(1));
    }

    #[test]
    fn les_menaces_ne_sont_reelles_que_sur_la_frontiere() {
        // Le joueur 2 aligne (3,1) (3,2) (3,3) et le dernier coup est (3,3).
        // (3,4) semble gagner, mais le joueur 1 peut simplement éloigner la
        // frontière : depuis (4,2) ou (2,2), (3,4) n'est plus adjacent au
        // dernier coup, donc plus jouable. Le moteur ne doit donc PAS voir de
        // menace mortelle ici.
        let p1 = bit(6, 6) | bit(6, 5);
        let p2 = bit(3, 1) | bit(3, 2) | bit(3, 3);
        let mut e = engine(8);
        let r = e.search(p1, p2, 1, idx(3, 3) as u8);
        assert_ne!(r.wdl(), Some(-1), "aucune défaite forcée : la frontière peut s'échapper");
    }

    #[test]
    fn alpha_beta_egale_minimax_naif() {
        // Le cœur de la validation : sur chaque position et chaque profondeur,
        // la recherche optimisée doit rendre EXACTEMENT le score de la
        // recherche naïve. Toute erreur dans la table de transposition,
        // l'ordonnancement, les bornes ou l'élagage de symétrie casse ce test.
        for ((p1, p2, side, last), max_depth) in reference_positions() {
            for depth in 1..=max_depth {
                let mut e = engine(depth);
                let r = e.search(p1, p2, side, last);
                let expected = naive(p1, p2, side, last, depth, 0);
                assert_eq!(
                    r.score, expected,
                    "profondeur {depth} : moteur {} contre minimax naïf {}",
                    r.score, expected
                );
                // La recherche s'arrête plus tôt quand un mat est prouvé.
                assert!(
                    r.depth <= depth,
                    "profondeur annoncée {} > profondeur demandée {depth}",
                    r.depth
                );
                if r.score.abs() < MATE_MARGIN {
                    assert_eq!(r.depth, depth, "aucun mat : la profondeur demandée doit être terminée");
                }
            }
        }
    }

    #[test]
    fn le_meilleur_coup_est_legal_et_recherche() {
        let (p1, p2) = (
            bit(3, 3) | bit(2, 3) | bit(4, 4) | bit(1, 2),
            bit(3, 4) | bit(2, 4) | bit(4, 3) | bit(1, 3),
        );
        let last = idx(1, 3) as u8;
        let mut e = engine(5);
        let r = e.search(p1, p2, 1, last);
        let best = r.best.expect("un coup doit être proposé");
        let mask = move_mask(p1, p2, 1, last);
        assert!(mask & (1u64 << best) != 0, "le coup proposé doit être dans le masque légal");
        assert!(
            r.moves.iter().any(|m| m.mv == best),
            "le meilleur coup doit figurer dans le détail"
        );
    }

    #[test]
    fn plateau_vide_recherche_sans_planter() {
        let mut e = Engine::new(EngineConfig {
            tt_mb: 16,
            max_depth: 6,
            time_ms: 0,
        });
        let r = e.search(0, 0, 1, 255);
        assert!(r.best.is_some());
        // Pas de défaite prouvée au premier coup, et le détail est complet.
        assert_ne!(r.wdl(), Some(-1));
        assert!(!r.moves.is_empty());
    }

    #[test]
    fn recherche_deterministe_meme_avec_la_table_de_transposition() {
        let (p1, p2) = (
            bit(3, 3) | bit(2, 3) | bit(4, 4) | bit(1, 2),
            bit(3, 4) | bit(2, 4) | bit(4, 3) | bit(1, 3),
        );
        let last = idx(1, 3) as u8;
        let mut e = engine(5);
        let a = e.search(p1, p2, 1, last);
        // Deuxième recherche : la table de transposition est déjà remplie, le
        // résultat doit être identique.
        let b = e.search(p1, p2, 1, last);
        assert_eq!(a.score, b.score);
        assert_eq!(a.best, b.best);
    }

    #[test]
    fn respecte_la_limite_de_temps() {
        let mut e = Engine::new(EngineConfig {
            tt_mb: 8,
            max_depth: 40,
            time_ms: 250,
        });
        let start = Instant::now();
        let r = e.search(bit(3, 3), 0, 2, idx(3, 3) as u8);
        assert!(start.elapsed() < Duration::from_millis(2500), "temps respecté");
        assert!(r.best.is_some());
        assert!(r.truncated);
    }

    #[test]
    fn le_mode_analyse_donne_le_score_exact_de_chaque_coup() {
        // En analyse, chaque coup de la racine est comparé aux autres : son
        // score doit être la valeur exacte, pas une simple borne.
        let p1 = bit(3, 3) | bit(2, 3) | bit(4, 4) | bit(1, 2);
        let p2 = bit(3, 4) | bit(2, 4) | bit(4, 3) | bit(1, 3);
        let (side, last) = (1u8, idx(1, 3) as u8);
        let depth = 4i16;

        let mut e = engine(depth);
        e.set_exact_root(true);
        let r = e.search(p1, p2, side, last);
        assert!(!r.moves.is_empty());

        for m in &r.moves {
            assert!(m.exact, "tous les scores doivent être marqués exacts en mode analyse");
            let b = 1u64 << m.mv;
            let (c1, c2) = if side == 1 {
                (p1 | b, p2)
            } else {
                (p1, p2 | b)
            };
            let attendu = -naive(c1, c2, 3 - side, m.mv, depth - 1, 1);
            assert_eq!(
                m.score, attendu,
                "coup ({}, {}) : score {} au lieu de {}",
                m.mv as usize / 7,
                m.mv as usize % 7,
                m.score,
                attendu
            );
        }
    }

    #[test]
    fn le_score_du_meilleur_coup_est_le_maximum() {
        let mut e = engine(6);
        let r = e.search(bit(3, 3), 0, 2, idx(3, 3) as u8);
        assert!(!r.moves.is_empty());
        let max = r.moves.iter().map(|m| m.score).max().unwrap();
        assert_eq!(r.score, max, "le score de la position est le maximum des coups");
        assert!(r.moves[0].score >= r.moves[r.moves.len() - 1].score);
    }
}
