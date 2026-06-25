//! Exploration BFS avant + rétrograde parents — port de `exhaustive_explorer.py`.

use std::collections::{HashSet, VecDeque};

use crate::game::{
    apply_move, board_full, check_winner, empty_cells, frontier_moves, is_connected, Board,
    Position, Move, BOARD_SIZE,
};
use crate::hasher::PositionHasher;

pub const MAX_EMPTY_LEVELS: [usize; 5] = [12, 20, 30, 40, 49];

/// Limite de nœuds BFS explorés par lot (évite de bloquer quand la base est déjà énorme).
pub const MAX_NODES_PER_BATCH: usize = 250_000;
pub const MAX_NODES_MATURE: usize = 40_000;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ExplorationMode {
    Retrograde,
    Forward,
}

fn is_terminal(board: &Board, last_move: Option<Move>, player: i8) -> bool {
    if check_winner(board).is_some() {
        return true;
    }
    if board_full(board) {
        return true;
    }
    frontier_moves(board, last_move, player).is_empty()
}

fn parent_last_moves(
    board: &Board,
    player: i8,
    target_move: Move,
) -> Vec<Option<Move>> {
    if empty_cells(board) == BOARD_SIZE * BOARD_SIZE {
        return vec![None];
    }

    let mut found = Vec::new();
    for row in 0..BOARD_SIZE {
        for col in 0..BOARD_SIZE {
            if board[row][col] == 0 {
                continue;
            }
            let lm = (row, col);
            let moves = frontier_moves(board, Some(lm), player);
            if moves.iter().any(|&m| m == target_move) {
                found.push(Some(lm));
            }
        }
    }

    let moves_fallback = frontier_moves(board, None, player);
    if moves_fallback.iter().any(|&m| m == target_move) && !found.iter().any(|x| x.is_none()) {
        found.push(None);
    }

    found
}

pub fn generate_parents(
    board: &Board,
    current_player: i8,
    last_move: Option<Move>,
    max_empty: usize,
) -> Vec<Position> {
    let Some((lr, lc)) = last_move else {
        return Vec::new();
    };

    let mover = board[lr][lc];
    if mover != 3 - current_player || mover == 0 {
        return Vec::new();
    }

    let mut board_parent = *board;
    board_parent[lr][lc] = 0;
    let parent_player = mover;

    if empty_cells(&board_parent) > max_empty {
        return Vec::new();
    }

    // Invariant de légalité : une position atteignable a tous ses pions en un seul
    // bloc 8-connexe. Si retirer ce pion déconnecte le plateau (ou isole un pion),
    // le parent est illégal — on l'élague pour ne pas polluer la base.
    if !is_connected(&board_parent) {
        return Vec::new();
    }

    let mut parents = Vec::new();
    for plm in parent_last_moves(&board_parent, parent_player, (lr, lc)) {
        parents.push((board_parent, parent_player, plm));
    }
    parents
}

/// État persistant de l'explorateur (checkpoint en mémoire).
pub struct ExplorerState {
    pub max_empty: usize,
    pub level_idx: usize,
    pub mode: ExplorationMode,
    pub known: HashSet<String>,
    pub bfs_seen: HashSet<String>,
    pub retro_seen: HashSet<String>,
    bfs_queue: VecDeque<Position>,
    retro_queue: VecDeque<Position>,
    bfs_initialized: bool,
}

impl ExplorerState {
    pub fn new(max_empty_start: usize, known: HashSet<String>) -> Self {
        let level_idx = MAX_EMPTY_LEVELS
            .iter()
            .position(|&l| l >= max_empty_start)
            .unwrap_or(MAX_EMPTY_LEVELS.len() - 1);
        let max_empty = MAX_EMPTY_LEVELS[level_idx];

        Self {
            max_empty,
            level_idx,
            mode: ExplorationMode::Retrograde,
            known,
            bfs_seen: HashSet::new(),
            retro_seen: HashSet::new(),
            bfs_queue: VecDeque::new(),
            retro_queue: VecDeque::new(),
            bfs_initialized: false,
        }
    }

    /// Sur une base déjà massive, évite de re-scanner tout le niveau 12 (déjà saturé).
    pub fn skip_completed_levels(&mut self, known_count: usize) {
        if known_count < 500_000 {
            return;
        }
        let target_idx = if known_count >= 850_000 {
            1
        } else if known_count >= 650_000 {
            1
        } else {
            0
        };
        if target_idx <= self.level_idx {
            return;
        }
        self.level_idx = target_idx;
        self.max_empty = MAX_EMPTY_LEVELS[target_idx];
        self.mode = ExplorationMode::Retrograde;
        self.bfs_initialized = false;
        self.bfs_seen.clear();
        self.retro_seen.clear();
        self.retro_queue.clear();
        tracing::info!(
            "Base mature — exploration démarrée à max_empty={} ({} positions connues)",
            self.max_empty,
            known_count
        );
    }

    pub fn is_exhausted(&self) -> bool {
        match self.mode {
            ExplorationMode::Forward => self.bfs_initialized && self.bfs_queue.is_empty(),
            ExplorationMode::Retrograde => self.retro_queue.is_empty(),
        }
    }

    pub fn init_bfs(&mut self) {
        let start: Position = ([[0i8; BOARD_SIZE]; BOARD_SIZE], 1, None);
        let sh = PositionHasher::hash_key(&start.0, start.1, start.2);
        self.bfs_seen.insert(sh);
        self.bfs_queue.clear();
        self.bfs_queue.push_back(start);
        self.bfs_initialized = true;
    }

    /// Mode rétrograde de frontière : étend la base connue vers l'ouverture
    /// (parents = +1 case vide) jusqu'au plafond `cap`, sans grille de niveaux.
    pub fn set_frontier_mode(&mut self, cap: usize) {
        self.max_empty = cap;
        self.mode = ExplorationMode::Retrograde;
    }

    /// Ajoute à la file rétrograde les parents (non connus) des graines fournies.
    /// Retourne le nombre de nouveaux parents mis en file.
    pub fn extend_retrograde(&mut self, seeds: &[Position]) -> usize {
        let mut added = 0usize;
        for (board, player, last_move) in seeds {
            for parent in generate_parents(board, *player, *last_move, self.max_empty) {
                let ph = PositionHasher::hash_key(&parent.0, parent.1, parent.2);
                if self.known.contains(&ph) || self.retro_seen.contains(&ph) {
                    continue;
                }
                self.retro_seen.insert(ph);
                self.retro_queue.push_back(parent);
                added += 1;
            }
        }
        added
    }

    pub fn retro_queue_len(&self) -> usize {
        self.retro_queue.len()
    }

    pub fn seed_retrograde(&mut self, seeds: &[Position]) {
        self.retro_queue.clear();
        for pos in seeds {
            let (board, player, last_move) = pos;
            for parent in generate_parents(board, *player, *last_move, self.max_empty) {
                let h = PositionHasher::hash_key(&parent.0, parent.1, parent.2);
                if self.known.contains(&h) || self.retro_seen.contains(&h) {
                    continue;
                }
                self.retro_seen.insert(h);
                self.retro_queue.push_back(parent);
            }
        }
    }

    /// Produit jusqu'à `target` nouvelles positions à résoudre.
    pub fn next_batch(&mut self, target: usize, retro_seeds: &[Position]) -> Vec<Position> {
        self.next_batch_limited(target, retro_seeds, MAX_NODES_PER_BATCH)
    }

    pub fn next_batch_limited(
        &mut self,
        target: usize,
        retro_seeds: &[Position],
        node_limit: usize,
    ) -> Vec<Position> {
        let mut out = Vec::with_capacity(target.min(4096));

        if self.mode == ExplorationMode::Forward {
            if !self.bfs_initialized {
                self.init_bfs();
            }
            let mut nodes_scanned = 0usize;
            while out.len() < target && nodes_scanned < node_limit {
                let Some((board, player, last_move)) = self.bfs_queue.pop_front() else {
                    break;
                };
                nodes_scanned += 1;
                let h = PositionHasher::hash_key(&board, player, last_move);

                if empty_cells(&board) <= self.max_empty && !self.known.contains(&h) {
                    self.known.insert(h.clone());
                    out.push((board, player, last_move));
                    if out.len() >= target {
                        break;
                    }
                }

                if is_terminal(&board, last_move, player) {
                    continue;
                }

                for mv in frontier_moves(&board, last_move, player) {
                    let nb = apply_move(&board, mv, player);
                    let opp = 3 - player;
                    let ch = PositionHasher::hash_key(&nb, opp, Some(mv));
                    if self.bfs_seen.contains(&ch) {
                        continue;
                    }
                    self.bfs_seen.insert(ch);
                    self.bfs_queue.push_back((nb, opp, Some(mv)));
                }
            }
        } else {
            if self.retro_queue.is_empty() {
                self.seed_retrograde(retro_seeds);
            }
            while out.len() < target {
                let Some((board, player, last_move)) = self.retro_queue.pop_front() else {
                    break;
                };
                let h = PositionHasher::hash_key(&board, player, last_move);

                if self.known.contains(&h) {
                    continue;
                }

                // Garde de légalité : on n'émet jamais une position non-connexe (illégale),
                // quelle que soit la provenance (graine, cascade, backlog).
                if empty_cells(&board) <= self.max_empty && is_connected(&board) {
                    self.known.insert(h.clone());
                    out.push((board, player, last_move));
                    if out.len() >= target {
                        break;
                    }
                }

                for parent in generate_parents(&board, player, last_move, self.max_empty) {
                    let ph = PositionHasher::hash_key(&parent.0, parent.1, parent.2);
                    if self.known.contains(&ph) || self.retro_seen.contains(&ph) {
                        continue;
                    }
                    self.retro_seen.insert(ph);
                    self.retro_queue.push_back(parent);
                }
            }
        }

        out
    }

    /// Bascule de mode/niveau quand l'exploration courante est épuisée.
    pub fn advance_phase(&mut self) -> bool {
        if self.mode == ExplorationMode::Retrograde {
            self.mode = ExplorationMode::Forward;
            self.bfs_initialized = false;
            tracing::info!("Exploration → mode forward (max_empty={})", self.max_empty);
            return true;
        }
        if self.level_idx + 1 < MAX_EMPTY_LEVELS.len() {
            self.level_idx += 1;
            self.max_empty = MAX_EMPTY_LEVELS[self.level_idx];
            self.mode = ExplorationMode::Retrograde;
            self.retro_queue.clear();
            tracing::info!("Niveau suivant — max_empty={}", self.max_empty);
            return true;
        }
        // Recyclage complet
        self.level_idx = 0;
        self.max_empty = MAX_EMPTY_LEVELS[0];
        self.mode = ExplorationMode::Retrograde;
        self.bfs_seen.clear();
        self.retro_seen.clear();
        self.retro_queue.clear();
        self.bfs_initialized = false;
        tracing::info!("Recyclage exploration — max_empty={}", self.max_empty);
        false
    }
}
