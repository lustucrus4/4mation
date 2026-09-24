//! Recherche exacte depuis l'ouverture.
//!
//! Le solveur rétrograde stocke chaque position de fin de partie. Cet espace
//! grossit trop vite pour une machine locale. Ici on prouve victoire / nulle /
//! défaite en ne visitant que les positions utiles, chacune une seule fois.
//!
//! Réductions :
//! - symétries du carré (4 rotations × miroir) : une seule clé par orbite ;
//! - transpositions : le même plateau atteint par un autre ordre de coups
//!   n'est pas recalculé (table de transposition) ;
//! - à la racine, un seul représentant par orbite (10 coups au lieu de 49).
//!
//! Les motifs simplement décalés (même forme, autre case) ne sont pas fusionnés :
//! sur un 7×7, se rapprocher d'un bord change les coups possibles et les
//! alignements. Les fusionner donnerait un résultat faux.

use std::collections::VecDeque;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use crate::game::BOARD_SIZE;
#[cfg(test)]
use crate::game::{check_winner, Board};
use crate::hasher::{ZOBRIST_CELL, ZOBRIST_P1, ZOBRIST_P2};
#[cfg(test)]
use crate::hasher::PositionHasher;

pub(crate) const N: usize = BOARD_SIZE;
pub(crate) const CELLS: usize = N * N;
const UNKNOWN: i8 = 2;

const H_START: u64 = mask_start(6, 0, 3);
const V_START: u64 = mask_start(3, 0, 6);
const D_START: u64 = mask_start(3, 0, 3);
const A_START: u64 = mask_anti_start();
const NEIGHBORS: [u64; CELLS] = neighbor_masks();
const MAP: [[u8; CELLS]; 8] = symmetry_maps();

pub(crate) const fn idx(r: usize, c: usize) -> usize {
    r * N + c
}

pub(crate) const fn mask_start(max_r: usize, min_c: usize, max_c: usize) -> u64 {
    let mut m = 0u64;
    let mut r = 0;
    while r <= max_r {
        let mut c = min_c;
        while c <= max_c {
            m |= 1u64 << idx(r, c);
            c += 1;
        }
        r += 1;
    }
    m
}

const fn mask_anti_start() -> u64 {
    let mut m = 0u64;
    let mut r = 0;
    while r <= 3 {
        let mut c = 3;
        while c <= 6 {
            m |= 1u64 << idx(r, c);
            c += 1;
        }
        r += 1;
    }
    m
}

const fn neighbor_masks() -> [u64; CELLS] {
    let mut masks = [0u64; CELLS];
    let mut r: i32 = 0;
    while r < N as i32 {
        let mut c: i32 = 0;
        while c < N as i32 {
            let mut m = 0u64;
            let mut dr = -1;
            while dr <= 1 {
                let mut dc = -1;
                while dc <= 1 {
                    if !(dr == 0 && dc == 0) {
                        let nr = r + dr;
                        let nc = c + dc;
                        if nr >= 0 && nr < N as i32 && nc >= 0 && nc < N as i32 {
                            m |= 1u64 << idx(nr as usize, nc as usize);
                        }
                    }
                    dc += 1;
                }
                dr += 1;
            }
            masks[idx(r as usize, c as usize)] = m;
            c += 1;
        }
        r += 1;
    }
    masks
}

const fn tr_cell(r: usize, c: usize, sym: usize) -> (usize, usize) {
    let (r, c) = match sym {
        0 => (r, c),
        1 => (c, N - 1 - r),
        2 => (N - 1 - r, N - 1 - c),
        3 => (N - 1 - c, r),
        _ => {
            let fr = r;
            let fc = N - 1 - c;
            match sym {
                4 => (fr, fc),
                5 => (fc, N - 1 - fr),
                6 => (N - 1 - fr, N - 1 - fc),
                _ => (N - 1 - fc, fr),
            }
        }
    };
    (r, c)
}

const fn symmetry_maps() -> [[u8; CELLS]; 8] {
    let mut map = [[0u8; CELLS]; 8];
    let mut s = 0;
    while s < 8 {
        let mut i = 0;
        while i < CELLS {
            let (nr, nc) = tr_cell(i / N, i % N, s);
            map[s][i] = idx(nr, nc) as u8;
            i += 1;
        }
        s += 1;
    }
    map
}

#[inline]
fn map_bits(bits: u64, sym: usize) -> u64 {
    let mut out = 0u64;
    let mut b = bits;
    while b != 0 {
        let i = b.trailing_zeros() as usize;
        b &= b - 1;
        out |= 1u64 << MAP[sym][i];
    }
    out
}

/// Quatre pions alignés. Les masques empêchent un alignement de traverser le bord.
#[inline]
pub fn has_four(bits: u64) -> bool {
    let h = bits & (bits >> 1) & (bits >> 2) & (bits >> 3);
    if h & H_START != 0 {
        return true;
    }
    let v = bits & (bits >> 7) & (bits >> 14) & (bits >> 21);
    if v & V_START != 0 {
        return true;
    }
    let d = bits & (bits >> 8) & (bits >> 16) & (bits >> 24);
    if d & D_START != 0 {
        return true;
    }
    let a = bits & (bits >> 6) & (bits >> 12) & (bits >> 18);
    a & A_START != 0
}

fn hash_full(p1: u64, p2: u64, side: u8, last: u8) -> u64 {
    let mut h = 0u64;
    for i in 0..CELLS {
        let piece = if (p1 >> i) & 1 == 1 {
            1
        } else if (p2 >> i) & 1 == 1 {
            2
        } else {
            0
        };
        h ^= ZOBRIST_CELL[i * 3 + piece];
    }
    h ^= if side == 1 { ZOBRIST_P1 } else { ZOBRIST_P2 };
    if last != 255 {
        h ^= (last as u64) << 32;
    }
    h
}

pub(crate) fn empty_hashes() -> (u64, u64) {
    (hash_full(0, 0, 1, 255), hash_full(0, 0, 2, 255))
}

#[inline]
fn hash_pos(p1: u64, p2: u64, side: u8, last: u8, empty_p1: u64, empty_p2: u64) -> u64 {
    let mut h = if side == 1 { empty_p1 } else { empty_p2 };
    let mut b = p1;
    while b != 0 {
        let i = b.trailing_zeros() as usize;
        b &= b - 1;
        h ^= ZOBRIST_CELL[i * 3] ^ ZOBRIST_CELL[i * 3 + 1];
    }
    let mut b = p2;
    while b != 0 {
        let i = b.trailing_zeros() as usize;
        b &= b - 1;
        h ^= ZOBRIST_CELL[i * 3] ^ ZOBRIST_CELL[i * 3 + 2];
    }
    if last != 255 {
        h ^= (last as u64) << 32;
    }
    h
}

/// Clé canonique : minimum des 8 hashs de symétrie. C'est la clé utilisée par
/// la tablebase SQLite (`position_hasher.py`), donc celle des lectures de finale.
#[inline]
pub(crate) fn canon_key(p1: u64, p2: u64, side: u8, last: u8, empty_p1: u64, empty_p2: u64) -> u64 {
    let mut best = u64::MAX;
    for sym in 0..8 {
        let a = map_bits(p1, sym);
        let b = map_bits(p2, sym);
        let l = if last == 255 {
            255
        } else {
            MAP[sym][last as usize]
        };
        let h = hash_pos(a, b, side, l, empty_p1, empty_p2);
        if h < best {
            best = h;
        }
    }
    best
}

/// Clé interne : une symétrie (forme lexico minimale), puis un seul hash.
/// Plus rapide que le minimum de 8 hashes, et tout aussi unique pour la table.
#[inline]
pub(crate) fn tt_key(p1: u64, p2: u64, side: u8, last: u8, empty_p1: u64, empty_p2: u64) -> u64 {
    let mut best_a = p1;
    let mut best_b = p2;
    let mut best_l = last;
    for sym in 1..8 {
        let a = map_bits(p1, sym);
        let b = map_bits(p2, sym);
        let l = if last == 255 {
            255
        } else {
            MAP[sym][last as usize]
        };
        if a < best_a || (a == best_a && (b < best_b || (b == best_b && l < best_l))) {
            best_a = a;
            best_b = b;
            best_l = l;
        }
    }
    hash_pos(best_a, best_b, side, best_l, empty_p1, empty_p2)
}

#[inline]
pub fn move_mask(p1: u64, p2: u64, side: u8, last: u8) -> u64 {
    let occ = p1 | p2;
    if occ == 0 {
        return (1u64 << CELLS) - 1;
    }
    if last != 255 {
        let near = NEIGHBORS[last as usize] & !occ;
        if near != 0 {
            return near;
        }
    }
    let opp = if side == 1 { p2 } else { p1 };
    let mut m = 0u64;
    let mut b = opp;
    while b != 0 {
        let i = b.trailing_zeros() as usize;
        b &= b - 1;
        m |= NEIGHBORS[i];
    }
    m & !occ
}

#[inline]
fn fixes(p1: u64, p2: u64, last: u8, sym: usize) -> bool {
    if map_bits(p1, sym) != p1 || map_bits(p2, sym) != p2 {
        return false;
    }
    last == 255 || MAP[sym][last as usize] == last
}

fn line_strength(my: u64, mv: u8) -> i16 {
    let r0 = (mv / N as u8) as i32;
    let c0 = (mv % N as u8) as i32;
    let mut best = 1i16;
    const DIRS: [(i32, i32); 4] = [(0, 1), (1, 0), (1, 1), (1, -1)];
    for (dr, dc) in DIRS {
        let mut n = 1i16;
        for sign in [-1, 1] {
            let mut r = r0 + dr * sign;
            let mut c = c0 + dc * sign;
            while (0..N as i32).contains(&r)
                && (0..N as i32).contains(&c)
                && (my >> idx(r as usize, c as usize)) & 1 == 1
            {
                n += 1;
                r += dr * sign;
                c += dc * sign;
            }
        }
        if n > best {
            best = n;
        }
    }
    best
}

fn opponent_wins_next(opp: u64, occ: u64, mv: u8) -> bool {
    let after = occ | (1u64 << mv);
    let mut b = NEIGHBORS[mv as usize] & !after;
    while b != 0 {
        let i = b.trailing_zeros();
        b &= b - 1;
        if has_four(opp | (1u64 << i)) {
            return true;
        }
    }
    false
}

fn order_key(my: u64, opp: u64, mv: u8) -> i16 {
    let with = my | (1u64 << mv);
    if has_four(with) {
        return 20_000;
    }
    let mut score: i16 = 0;
    if !opponent_wins_next(opp, my | opp, mv) {
        score += 1_000;
    }
    let r = (mv / N as u8) as i16;
    let c = (mv % N as u8) as i16;
    score + line_strength(my, mv) * 8 - ((r - 3).abs() + (c - 3).abs())
}

pub(crate) struct MoveBuf {
    pub(crate) m: [u8; 64],
    pub(crate) n: usize,
}

pub(crate) fn collect_moves(mask: u64) -> MoveBuf {
    let mut buf = MoveBuf { m: [0; 64], n: 0 };
    let mut b = mask;
    while b != 0 {
        let i = b.trailing_zeros() as u8;
        b &= b - 1;
        buf.m[buf.n] = i;
        buf.n += 1;
    }
    buf
}

pub(crate) fn sort_moves(buf: &mut MoveBuf, my: u64, opp: u64) {
    let n = buf.n;
    let mut keys = [0i16; 64];
    for i in 0..n {
        keys[i] = order_key(my, opp, buf.m[i]);
    }
    for i in 1..n {
        let mv = buf.m[i];
        let key = keys[i];
        let mut j = i;
        while j > 0 && keys[j - 1] < key {
            buf.m[j] = buf.m[j - 1];
            keys[j] = keys[j - 1];
            j -= 1;
        }
        buf.m[j] = mv;
        keys[j] = key;
    }
}

pub(crate) fn prune_symmetric(buf: &mut MoveBuf, p1: u64, p2: u64, last: u8) {
    let mut stab = [false; 8];
    let mut any = false;
    for sym in 1..8 {
        stab[sym] = fixes(p1, p2, last, sym);
        any |= stab[sym];
    }
    if !any {
        return;
    }
    let mut kept = [0u8; 64];
    let mut kn = 0usize;
    for i in 0..buf.n {
        let mv = buf.m[i];
        let mut dup = false;
        for sym in 1..8 {
            if stab[sym] && kept[..kn].contains(&MAP[sym][mv as usize]) {
                dup = true;
                break;
            }
        }
        if !dup {
            kept[kn] = mv;
            kn += 1;
        }
    }
    buf.m = kept;
    buf.n = kn;
}

struct Tt {
    /// Entrée = tag (bits hauts de la clé) + score. L'index est les bits bas :
    /// tag + index reconstituent la clé 64 bits, donc pas de faux positif.
    slots: Vec<AtomicU64>,
    mask: u64,
    shift: u32,
    empty_p1: u64,
    empty_p2: u64,
}

impl Tt {
    fn new(tt_mb: usize) -> Self {
        let bytes = tt_mb.max(1) as u64 * 1024 * 1024;
        let mut slots_n = (bytes / 8).next_power_of_two();
        if slots_n < 1024 {
            slots_n = 1024;
        }
        let mut slots = Vec::with_capacity(slots_n as usize);
        for _ in 0..slots_n {
            slots.push(AtomicU64::new(0));
        }
        let (empty_p1, empty_p2) = empty_hashes();
        Self {
            slots,
            mask: slots_n - 1,
            shift: slots_n.trailing_zeros(),
            empty_p1,
            empty_p2,
        }
    }

    #[inline]
    fn index_tag(&self, key: u64) -> (usize, u64) {
        ((key & self.mask) as usize, key >> self.shift)
    }

    #[inline]
    fn probe(&self, key: u64) -> Option<i8> {
        let (i, tag) = self.index_tag(key);
        let raw = self.slots[i].load(Ordering::Acquire);
        if raw == 0 || (raw >> 8) != tag {
            return None;
        }
        Some(match (raw & 0xff) as u8 {
            1 => -1,
            2 => 0,
            3 => 1,
            _ => return None,
        })
    }

    #[inline]
    fn store(&self, key: u64, score: i8) {
        let code: u64 = match score {
            -1 => 1,
            0 => 2,
            1 => 3,
            _ => return,
        };
        let (i, tag) = self.index_tag(key);
        // tag 0 + code 0 serait vide : un score stocké a toujours code ≠ 0.
        self.slots[i].store((tag << 8) | code, Ordering::Release);
    }
}

struct Ctrl {
    nodes: AtomicU64,
    stop: AtomicBool,
    start: Instant,
    limit: Option<Duration>,
}

impl Ctrl {
    fn bump(&self) {
        // Compteur thread-local pour ne pas saturer l'atomique à chaque nœud.
        thread_local! {
            static LOCAL: std::cell::Cell<u32> = const { std::cell::Cell::new(0) };
        }
        LOCAL.with(|c| {
            let n = c.get() + 1;
            if n >= 2048 {
                self.nodes.fetch_add(2048, Ordering::Relaxed);
                c.set(0);
                if let Some(limit) = self.limit {
                    if self.start.elapsed() >= limit {
                        self.stop.store(true, Ordering::Relaxed);
                    }
                }
            } else {
                c.set(n);
            }
        });
    }

    fn stopped(&self) -> bool {
        self.stop.load(Ordering::Relaxed)
    }
}

fn label_score(v: i8) -> &'static str {
    match v {
        1 => "victoire",
        0 => "nulle",
        -1 => "défaite",
        _ => "inconnu",
    }
}

fn merge_scores(a: i8, b: i8) -> i8 {
    if a == 1 || b == 1 {
        return 1;
    }
    if a == UNKNOWN || b == UNKNOWN {
        return UNKNOWN;
    }
    a.max(b)
}

fn search_moves(
    ctrl: &Ctrl,
    tt: &Tt,
    p1: u64,
    p2: u64,
    side: u8,
    my: u64,
    buf: &MoveBuf,
    lo: usize,
    hi: usize,
    depth: i16,
    split: u8,
    cut: &AtomicBool,
) -> i8 {
    if cut.load(Ordering::Relaxed) || ctrl.stopped() {
        return UNKNOWN;
    }
    if hi - lo >= 2 && split > 0 {
        let mid = lo + (hi - lo) / 2;
        let (left, right) = rayon::join(
            || search_moves(ctrl, tt, p1, p2, side, my, buf, lo, mid, depth, split - 1, cut),
            || search_moves(ctrl, tt, p1, p2, side, my, buf, mid, hi, depth, split - 1, cut),
        );
        return merge_scores(left, right);
    }

    let mut best: i8 = -1;
    let mut unknown = false;
    for i in lo..hi {
        if cut.load(Ordering::Relaxed) || ctrl.stopped() {
            return UNKNOWN;
        }
        let mv = buf.m[i];
        let bit = 1u64 << mv;
        if has_four(my | bit) {
            cut.store(true, Ordering::Relaxed);
            return 1;
        }
        let (c1, c2) = if side == 1 {
            (p1 | bit, p2)
        } else {
            (p1, p2 | bit)
        };
        let child = wdl(ctrl, tt, c1, c2, 3 - side, mv, depth - 1, split);
        if child == UNKNOWN {
            unknown = true;
            continue;
        }
        if -child == 1 {
            cut.store(true, Ordering::Relaxed);
            return 1;
        }
        if -child == 0 {
            best = 0;
        }
    }
    if unknown {
        UNKNOWN
    } else {
        best
    }
}

fn wdl(ctrl: &Ctrl, tt: &Tt, p1: u64, p2: u64, side: u8, last: u8, depth: i16, split: u8) -> i8 {
    ctrl.bump();
    if ctrl.stopped() {
        return UNKNOWN;
    }

    let key = tt_key(p1, p2, side, last, tt.empty_p1, tt.empty_p2);
    if let Some(score) = tt.probe(key) {
        return score;
    }

    let my = if side == 1 { p1 } else { p2 };
    let opp = if side == 1 { p2 } else { p1 };
    if has_four(opp) {
        tt.store(key, -1);
        return -1;
    }
    if has_four(my) {
        tt.store(key, 1);
        return 1;
    }
    if (p1 | p2).count_ones() == CELLS as u32 {
        tt.store(key, 0);
        return 0;
    }

    let mask = move_mask(p1, p2, side, last);
    if mask == 0 {
        tt.store(key, -1);
        return -1;
    }
    if depth <= 0 {
        return UNKNOWN;
    }

    let mut buf = collect_moves(mask);
    sort_moves(&mut buf, my, opp);
    prune_symmetric(&mut buf, p1, p2, last);

    let cut = AtomicBool::new(false);
    let outcome = search_moves(ctrl, tt, p1, p2, side, my, &buf, 0, buf.n, depth, split, &cut);
    if outcome == UNKNOWN {
        return UNKNOWN;
    }
    tt.store(key, outcome);
    outcome
}

#[derive(Clone, Debug)]
pub struct OpeningMove {
    pub row: u8,
    pub col: u8,
    /// 1 victoire, 0 nulle, -1 défaite, pour le joueur qui vient de jouer ce coup.
    /// `None` si la recherche a été interrompue avant la preuve.
    pub value_for_first: Option<i8>,
}

#[derive(Debug)]
pub struct ProofReport {
    /// Résultat pour le joueur 1. `None` si la preuve n'est pas finie.
    pub result: Option<i8>,
    pub best: Option<(u8, u8)>,
    pub moves: Vec<OpeningMove>,
    pub nodes: u64,
    pub elapsed: Duration,
    pub orbits: usize,
}

pub struct ProofConfig {
    pub threads: usize,
    pub tt_mb: usize,
    /// 0 = jusqu'à la preuve complète.
    pub seconds: u64,
    pub live: Option<Arc<ProofLive>>,
}

/// État lu par le dashboard. Mis à jour entre les profondeurs, pas dans la boucle chaude.
pub struct ProofLive {
    inner: Mutex<LiveInner>,
    started: Instant,
}

struct OrbitLive {
    row: u8,
    col: u8,
    /// `pending`, `searching`, `win`, `draw`, `loss`.
    status: &'static str,
}

struct DepthStat {
    depth: i32,
    nodes: u64,
    secs: f64,
}

struct LiveInner {
    phase: &'static str,
    message: String,
    depth: i32,
    row: u8,
    col: u8,
    orbits: Vec<OrbitLive>,
    result: Option<i8>,
    best: Option<(u8, u8)>,
    nodes: u64,
    nps: f64,
    samples: VecDeque<f64>,
    depths: Vec<DepthStat>,
    open_depth: Option<(i32, u64, f64)>,
    /// Secondes depuis le démarrage, au début de l'ouverture en cours.
    opening_t0: Option<f64>,
    threads: usize,
    tt_mb: usize,
}

impl ProofLive {
    pub fn new(threads: usize, tt_mb: usize) -> Arc<Self> {
        Arc::new(Self {
            started: Instant::now(),
            inner: Mutex::new(LiveInner {
                phase: "boot",
                message: "Démarrage".into(),
                depth: 0,
                row: 3,
                col: 3,
                orbits: Vec::new(),
                result: None,
                best: None,
                nodes: 0,
                nps: 0.0,
                samples: VecDeque::with_capacity(120),
                depths: Vec::new(),
                open_depth: None,
                opening_t0: None,
                threads,
                tt_mb,
            }),
        })
    }

    pub fn set_message(&self, phase: &'static str, message: impl Into<String>) {
        if let Ok(mut g) = self.inner.lock() {
            g.phase = phase;
            g.message = message.into();
        }
    }

    pub fn set_orbits(&self, orbits: &[(u8, u8)]) {
        if let Ok(mut g) = self.inner.lock() {
            g.orbits = orbits
                .iter()
                .map(|&(row, col)| OrbitLive {
                    row,
                    col,
                    status: "pending",
                })
                .collect();
        }
    }

    pub fn begin_opening(&self, row: u8, col: u8) {
        if let Ok(mut g) = self.inner.lock() {
            g.phase = "search";
            g.row = row;
            g.col = col;
            g.message = format!("Ouverture ligne {row}, colonne {col}");
            g.opening_t0 = Some(self.started.elapsed().as_secs_f64());
            for orbit in &mut g.orbits {
                if orbit.row == row && orbit.col == col && orbit.status == "pending" {
                    orbit.status = "searching";
                }
            }
        }
    }

    pub fn begin_depth(&self, depth: i32, nodes: u64) {
        if let Ok(mut g) = self.inner.lock() {
            let now = self.started.elapsed().as_secs_f64();
            if let Some((d, n0, t0)) = g.open_depth.take() {
                g.depths.push(DepthStat {
                    depth: d,
                    nodes: nodes.saturating_sub(n0),
                    secs: (now - t0).max(0.0),
                });
                if g.depths.len() > 40 {
                    g.depths.remove(0);
                }
            }
            g.depth = depth;
            g.open_depth = Some((depth, nodes, now));
            g.nodes = nodes;
        }
    }

    pub fn finish_orbit(&self, row: u8, col: u8, value_for_first: i8) {
        if let Ok(mut g) = self.inner.lock() {
            let status = match value_for_first {
                1 => "win",
                0 => "draw",
                _ => "loss",
            };
            for orbit in &mut g.orbits {
                if orbit.row == row && orbit.col == col {
                    orbit.status = status;
                }
            }
            g.message = format!(
                "Ouverture ({row}, {col}) : {}",
                label_score(value_for_first)
            );
        }
    }

    pub fn finish(&self, result: Option<i8>, best: Option<(u8, u8)>, nodes: u64) {
        if let Ok(mut g) = self.inner.lock() {
            let now = self.started.elapsed().as_secs_f64();
            if let Some((d, n0, t0)) = g.open_depth.take() {
                g.depths.push(DepthStat {
                    depth: d,
                    nodes: nodes.saturating_sub(n0),
                    secs: (now - t0).max(0.0),
                });
            }
            g.nodes = nodes;
            g.result = result;
            g.best = best;
            g.phase = if result.is_some() { "done" } else { "partial" };
            g.message = match result {
                Some(1) => "Victoire du joueur 1 prouvée".into(),
                Some(0) => "Nulle prouvée".into(),
                Some(_) => "Défaite du joueur 1 prouvée".into(),
                None => "Preuve interrompue".into(),
            };
        }
    }

    pub fn tick(&self, nodes: u64) {
        if let Ok(mut g) = self.inner.lock() {
            let secs = self.started.elapsed().as_secs_f64().max(0.001);
            g.nodes = nodes;
            g.nps = nodes as f64 / secs;
            let nps = g.nps;
            g.samples.push_back(nps);
            if g.samples.len() > 90 {
                g.samples.pop_front();
            }
        }
    }

    pub fn status_json(&self) -> serde_json::Value {
        let Ok(g) = self.inner.lock() else {
            return serde_json::json!({"phase": "error"});
        };
        let secs = self.started.elapsed().as_secs_f64();
        let eta = eta_next_depth(&g.depths);
        let current_secs = g
            .open_depth
            .map(|(_, _, t0)| (secs - t0).max(0.0))
            .unwrap_or(0.0);
        let openings_left = g
            .orbits
            .iter()
            .filter(|o| o.status == "pending" || o.status == "searching")
            .count();
        let opening_spent = g
            .opening_t0
            .map(|t0| (secs - t0).max(0.0))
            .unwrap_or(0.0);
        let finish = eta_finish(&g.depths, g.depth, current_secs, opening_spent, openings_left);
        serde_json::json!({
            "phase": g.phase,
            "message": g.message,
            "depth": g.depth,
            "max_depth": CELLS,
            "opening": {"row": g.row, "col": g.col},
            "nodes": g.nodes,
            "elapsed_sec": secs,
            "current_depth_sec": current_secs,
            "nps": g.nps,
            "eta_next_sec": eta,
            "eta_finish_sec": finish.as_ref().map(|e| e.all_sec),
            "eta_win_sec": finish.as_ref().map(|e| e.win_sec),
            "finish_horizon": finish.as_ref().map(|e| e.horizon),
            "openings_left": openings_left,
            "threads": g.threads,
            "tt_mb": g.tt_mb,
            "result": g.result,
            "best": g.best.map(|(r, c)| serde_json::json!({"row": r, "col": c})),
            "orbits": g.orbits.iter().map(|o| serde_json::json!({
                "row": o.row,
                "col": o.col,
                "status": o.status,
            })).collect::<Vec<_>>(),
            "samples": g.samples.iter().copied().collect::<Vec<_>>(),
            "depths": g.depths.iter().map(|d| serde_json::json!({
                "depth": d.depth,
                "nodes": d.nodes,
                "secs": d.secs,
            })).collect::<Vec<_>>(),
        })
    }
}

struct FinishEta {
    /// Temps restant si l'ouverture en cours est une victoire du joueur 1.
    win_sec: f64,
    /// Temps restant si chaque ouverture encore ouverte va jusqu'à l'horizon.
    all_sec: f64,
    horizon: i32,
}

/// Profondeur où l'on suppose que la valeur est connue.
/// Les parties se tranchent en pratique avant le coup 22. Si la recherche
/// dépasse déjà cet horizon, on le repousse de 4 coups.
fn proof_horizon(depth: i32) -> i32 {
    const BASE: i32 = 22;
    let target = if depth < BASE { BASE } else { depth + 4 };
    target.clamp(depth, CELLS as i32)
}

fn growth_ratio(depths: &[DepthStat]) -> Option<f64> {
    let secs: Vec<f64> = depths
        .iter()
        .filter(|d| d.secs >= 0.3)
        .map(|d| d.secs)
        .collect();
    match secs.len() {
        0 => None,
        1 => Some(3.5),
        n => {
            let r1 = secs[n - 1] / secs[n - 2].max(0.05);
            let ratio = if n >= 3 {
                let r2 = secs[n - 2] / secs[n - 3].max(0.05);
                (r1 + r2) / 2.0
            } else {
                r1
            };
            Some(ratio.clamp(1.25, 5.0))
        }
    }
}

fn eta_finish(
    depths: &[DepthStat],
    current_depth: i32,
    current_secs: f64,
    opening_spent: f64,
    openings_left: usize,
) -> Option<FinishEta> {
    if current_depth <= 0 {
        return None;
    }
    let ratio = growth_ratio(depths)?;
    let last = depths.iter().rev().find(|d| d.secs >= 0.3)?.secs;
    let horizon = proof_horizon(current_depth);
    let openings = openings_left.max(1);
    let predicted = last * ratio;
    let remaining_current = if current_secs + 1.0 < predicted {
        predicted - current_secs
    } else {
        (current_secs * 0.35).max(10.0)
    };
    let mut step = predicted;
    let mut after = 0.0;
    let mut depth = current_depth;
    while depth < horizon {
        step *= ratio;
        after += step;
        depth += 1;
        if after > 86_400.0 * 3_650.0 {
            break;
        }
    }
    let win_sec = remaining_current + after;
    let one_full = opening_spent + win_sec;
    let all_sec = win_sec + (openings - 1) as f64 * one_full;
    Some(FinishEta {
        win_sec,
        all_sec,
        horizon,
    })
}

fn eta_next_depth(depths: &[DepthStat]) -> Option<f64> {
    let n = depths.len();
    if n == 0 {
        return None;
    }
    let last = depths[n - 1].secs;
    if n == 1 {
        return Some(last * 3.5);
    }
    let prev = depths[n - 2].secs.max(0.05);
    let ratio = (last / prev).clamp(1.2, 8.0);
    Some(last * ratio)
}

impl Default for ProofConfig {
    fn default() -> Self {
        Self {
            threads: std::thread::available_parallelism()
                .map(|n| n.get())
                .unwrap_or(8),
            tt_mb: 1024,
            seconds: 0,
            live: None,
        }
    }
}

/// Prouve le résultat de la position de départ.
///
/// Seuls les coups d'ouverture géométriquement distincts (orbite D₄) sont
/// cherchés. Les 39 autres premiers coups sont des rotations ou des miroirs.
pub fn solve_opening(cfg: &ProofConfig) -> ProofReport {
    let started = Instant::now();
    if let Some(live) = &cfg.live {
        live.set_message(
            "boot",
            format!(
                "Allocation de la table ({} Mo)…",
                cfg.tt_mb.max(64)
            ),
        );
    }
    eprintln!(
        "Table de transposition : {} Mo, {} threads",
        cfg.tt_mb.max(64),
        cfg.threads.max(1)
    );
    let tt = Arc::new(Tt::new(cfg.tt_mb.max(64)));
    let ctrl = Arc::new(Ctrl {
        nodes: AtomicU64::new(0),
        stop: AtomicBool::new(false),
        start: Instant::now(),
        limit: if cfg.seconds == 0 {
            None
        } else {
            Some(Duration::from_secs(cfg.seconds))
        },
    });

    let mut root = collect_moves((1u64 << CELLS) - 1);
    sort_moves(&mut root, 0, 0);
    prune_symmetric(&mut root, 0, 0, 255);
    let orbits = root.n;
    if let Some(live) = &cfg.live {
        let pairs: Vec<(u8, u8)> = (0..root.n)
            .map(|i| {
                let mv = root.m[i];
                (mv / N as u8, mv % N as u8)
            })
            .collect();
        live.set_orbits(&pairs);
        live.set_message("search", "10 ouvertures distinctes (symétries retirées)");
    }
    eprintln!("Coups d'ouverture distincts : {orbits} (49 cases, symétries retirées)");

    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(cfg.threads.max(1))
        .build()
        .expect("pool de threads");

    let progress = Arc::new(AtomicBool::new(true));
    let progress_flag = Arc::clone(&progress);
    let ctrl_bg = Arc::clone(&ctrl);
    let live_bg = cfg.live.clone();
    let printer = std::thread::spawn(move || {
        let mut last_print = Instant::now();
        let mut last_tick = Instant::now();
        while progress_flag.load(Ordering::Relaxed) {
            std::thread::sleep(Duration::from_millis(200));
            if !progress_flag.load(Ordering::Relaxed) {
                break;
            }
            let nodes = ctrl_bg.nodes.load(Ordering::Relaxed);
            if last_tick.elapsed() >= Duration::from_millis(500) {
                if let Some(live) = &live_bg {
                    live.tick(nodes);
                }
                last_tick = Instant::now();
            }
            if last_print.elapsed() < Duration::from_secs(2) {
                continue;
            }
            last_print = Instant::now();
            let secs = ctrl_bg.start.elapsed().as_secs_f64().max(0.001);
            eprintln!(
                "  {nodes} nœuds — {:.2} M/s — {:.0} s",
                (nodes as f64) / secs / 1e6,
                secs
            );
            if let Some(limit) = ctrl_bg.limit {
                if ctrl_bg.start.elapsed() >= limit {
                    ctrl_bg.stop.store(true, Ordering::Relaxed);
                }
            }
        }
    });

    // Centre d'abord, jusqu'à preuve, puis l'ouverture suivante.
    // Les cœurs se partagent l'arbre de l'ouverture en cours.
    let mut values = vec![UNKNOWN; root.n];
    pool.install(|| {
        'openings: for i in 0..root.n {
            if ctrl.stopped() {
                break;
            }
            let mv = root.m[i];
            let row = mv / N as u8;
            let col = mv % N as u8;
            eprintln!("Ouverture ({row}, {col})");
            if let Some(live) = &cfg.live {
                live.begin_opening(row, col);
            }
            for depth in 1i16..=CELLS as i16 {
                if ctrl.stopped() {
                    break 'openings;
                }
                let nodes = ctrl.nodes.load(Ordering::Relaxed);
                if let Some(live) = &cfg.live {
                    live.begin_depth(depth as i32, nodes);
                }
                eprintln!("  profondeur {depth} — {nodes} nœuds");
                let v = wdl(&ctrl, &tt, 1u64 << mv, 0, 2, mv, depth - 1, 4);
                if v == UNKNOWN {
                    continue;
                }
                values[i] = v;
                if let Some(live) = &cfg.live {
                    live.finish_orbit(row, col, -v);
                }
                if -v == 1 {
                    eprintln!("Victoire du joueur 1 prouvée à la profondeur {depth}");
                    ctrl.stop.store(true, Ordering::Relaxed);
                } else {
                    eprintln!("Ouverture ({row}, {col}) prouvée : {}", label_score(-v));
                }
                break;
            }
        }
    });

    progress.store(false, Ordering::Relaxed);
    let _ = printer.join();

    let mut moves = Vec::with_capacity(values.len());
    let mut saw_unknown = false;
    let mut best_ours: Option<i8> = None;
    let mut best: Option<(u8, u8)> = None;
    for (i, child) in values.into_iter().enumerate() {
        let mv = root.m[i];
        let row = mv / N as u8;
        let col = mv % N as u8;
        if child == UNKNOWN {
            saw_unknown = true;
            moves.push(OpeningMove {
                row,
                col,
                value_for_first: None,
            });
            continue;
        }
        let ours = -child;
        best_ours = Some(best_ours.map(|b| b.max(ours)).unwrap_or(ours));
        if best_ours == Some(ours) {
            best = Some((row, col));
        }
        moves.push(OpeningMove {
            row,
            col,
            value_for_first: Some(ours),
        });
    }
    // Une victoire prouvée sur un seul premier coup suffit.
    // Une nulle n'est prouvée que si chaque premier coup l'est.
    let result = if best_ours == Some(1) {
        Some(1)
    } else if saw_unknown {
        None
    } else {
        best_ours
    };
    if result.is_none() {
        best = None;
    }
    if let Some(live) = &cfg.live {
        live.finish(result, best, ctrl.nodes.load(Ordering::Relaxed));
    }

    moves.sort_by(|a, b| {
        b.value_for_first
            .unwrap_or(-2)
            .cmp(&a.value_for_first.unwrap_or(-2))
            .then(a.row.cmp(&b.row))
            .then(a.col.cmp(&b.col))
    });

    ProofReport {
        result,
        best,
        moves,
        nodes: ctrl.nodes.load(Ordering::Relaxed),
        elapsed: started.elapsed(),
        orbits,
    }
}

#[cfg(test)]
fn cell_bit(r: usize, c: usize) -> u64 {
    1u64 << idx(r, c)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn board_of(p1: u64, p2: u64) -> Board {
        let mut board = [[0i8; N]; N];
        for i in 0..CELLS {
            if (p1 >> i) & 1 == 1 {
                board[i / N][i % N] = 1;
            } else if (p2 >> i) & 1 == 1 {
                board[i / N][i % N] = 2;
            }
        }
        board
    }

    #[test]
    fn four_in_a_row_matches_engine() {
        let cases = [
            [(0, 0), (0, 1), (0, 2), (0, 3)],
            [(2, 1), (3, 1), (4, 1), (5, 1)],
            [(0, 0), (1, 1), (2, 2), (3, 3)],
            [(0, 3), (1, 2), (2, 1), (3, 0)],
            [(6, 3), (6, 4), (6, 5), (6, 6)],
        ];
        for cells in cases {
            let mut bits = 0u64;
            for (r, c) in cells {
                bits |= cell_bit(r, c);
            }
            assert!(has_four(bits), "{cells:?}");
            let board = board_of(bits, 0);
            assert_eq!(check_winner(&board), Some(1));
        }
    }

    #[test]
    fn wrap_across_edge_is_not_a_win() {
        // (0,5)(0,6) puis la ligne suivante : pas un alignement horizontal.
        let bits = cell_bit(0, 5) | cell_bit(0, 6) | cell_bit(1, 0) | cell_bit(1, 1);
        assert!(!has_four(bits));
        assert_eq!(check_winner(&board_of(bits, 0)), None);
        let three = cell_bit(3, 2) | cell_bit(3, 3) | cell_bit(3, 4);
        assert!(!has_four(three));
    }

    #[test]
    fn hash_matches_existing_hasher() {
        let (e1, _) = empty_hashes();
        assert_eq!(
            format!("{e1:016x}"),
            PositionHasher::raw_hash_key(&[[0i8; N]; N], 1, None)
        );
        let p1 = cell_bit(1, 1);
        let h = hash_full(p1, 0, 2, idx(1, 1) as u8);
        let mut board = [[0i8; N]; N];
        board[1][1] = 1;
        assert_eq!(
            format!("{h:016x}"),
            PositionHasher::raw_hash_key(&board, 2, Some((1, 1)))
        );
    }

    #[test]
    fn rotation_shares_canonical_key_shift_does_not() {
        let (e1, e2) = empty_hashes();
        let corner = cell_bit(0, 0);
        let corner_rot = cell_bit(0, 6);
        let k1 = canon_key(corner, 0, 2, idx(0, 0) as u8, e1, e2);
        let k2 = canon_key(corner_rot, 0, 2, idx(0, 6) as u8, e1, e2);
        assert_eq!(k1, k2);

        let shifted = cell_bit(0, 1);
        let k3 = canon_key(shifted, 0, 2, idx(0, 1) as u8, e1, e2);
        assert_ne!(k1, k3, "un décalage d'une case n'est pas la même position");

        let center = cell_bit(3, 3);
        let k4 = canon_key(center, 0, 2, idx(3, 3) as u8, e1, e2);
        assert_ne!(k1, k4);

        let t1 = tt_key(corner, 0, 2, idx(0, 0) as u8, e1, e2);
        let t2 = tt_key(corner_rot, 0, 2, idx(0, 6) as u8, e1, e2);
        assert_eq!(t1, t2);
        let t3 = tt_key(shifted, 0, 2, idx(0, 1) as u8, e1, e2);
        assert_ne!(t1, t3);
    }

    #[test]
    fn opening_keeps_ten_orbits() {
        let mut buf = collect_moves((1u64 << CELLS) - 1);
        prune_symmetric(&mut buf, 0, 0, 255);
        assert_eq!(buf.n, 10);
    }

    #[test]
    fn immediate_win_is_proved() {
        let tt = Tt::new(64);
        let ctrl = Ctrl {
            nodes: AtomicU64::new(0),
            stop: AtomicBool::new(false),
            start: Instant::now(),
            limit: Some(Duration::from_secs(5)),
        };
        // Trois pions du joueur 1, le quatrième est adjacent au dernier coup.
        let p1 = cell_bit(3, 1) | cell_bit(3, 2) | cell_bit(3, 3);
        let v = wdl(&ctrl, &tt, p1, 0, 1, idx(3, 3) as u8, 4, 0);
        assert_eq!(v, 1);
    }

    #[test]
    fn canonical_key_matches_hasher() {
        let (e1, e2) = empty_hashes();
        let p1 = cell_bit(2, 5);
        let last = idx(2, 5) as u8;
        let key = canon_key(p1, 0, 2, last, e1, e2);
        let board = board_of(p1, 0);
        let hex = PositionHasher::hash_key(&board, 2, Some((2, 5)));
        assert_eq!(format!("{key:016x}"), hex);
    }

    #[test]
    fn finish_eta_counts_remaining_openings() {
        let depths = vec![
            DepthStat { depth: 15, nodes: 1, secs: 12.0 },
            DepthStat { depth: 16, nodes: 1, secs: 46.0 },
        ];
        let eta = eta_finish(&depths, 17, 20.0, 80.0, 10).unwrap();
        assert_eq!(eta.horizon, 22);
        assert!(eta.win_sec > 60.0);
        assert!(eta.all_sec > eta.win_sec * 5.0);
        let later = eta_finish(&depths, 17, 100.0, 160.0, 10).unwrap();
        assert!(later.win_sec < eta.win_sec);
        assert!(eta_finish(&[], 0, 0.0, 0.0, 10).is_none());
    }
}
