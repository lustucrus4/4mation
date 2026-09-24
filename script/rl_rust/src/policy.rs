//! Policy softmax linéaire sur features de coups.

use std::fs::File;
use std::io::{BufReader, BufWriter};
use std::path::Path;

use anyhow::{Context, Result};
use formation_worker::game::{Board, Move};
use rand::distributions::{Distribution, WeightedIndex};
use rand::Rng;
use serde::{Deserialize, Serialize};

use crate::features::{move_features, position_features, FEATURE_DIM, POS_DIM};
use crate::game_session::GameSession;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct LinearPolicy {
    pub weights: Vec<f64>,
    pub bias: f64,
    pub version: u64,
    pub steps: u64,
}

impl Default for LinearPolicy {
    fn default() -> Self {
        Self {
            weights: vec![0.0; FEATURE_DIM],
            bias: 0.0,
            version: 0,
            steps: 0,
        }
    }
}

impl LinearPolicy {
    pub fn new_random(rng: &mut impl Rng) -> Self {
        let mut p = Self::default();
        for w in &mut p.weights {
            *w = rng.gen_range(-0.05..0.05);
        }
        p.bias = rng.gen_range(-0.02..0.02);
        p
    }

    pub fn score(&self, feats: &[f64; FEATURE_DIM]) -> f64 {
        let mut s = self.bias;
        for (w, f) in self.weights.iter().zip(feats.iter()) {
            s += w * f;
        }
        s
    }

    pub fn logits(
        &self,
        board: &Board,
        moves: &[Move],
        player: i8,
        last_move: Option<Move>,
    ) -> Vec<f64> {
        moves
            .iter()
            .map(|&mv| self.score(&move_features(board, mv, player, last_move)))
            .collect()
    }

    pub fn probs(
        &self,
        board: &Board,
        moves: &[Move],
        player: i8,
        last_move: Option<Move>,
        temperature: f64,
    ) -> Vec<f64> {
        if moves.is_empty() {
            return vec![];
        }
        let logits = self.logits(board, moves, player, last_move);
        let t = temperature.max(1e-6);
        let max_l = logits.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
        let exp: Vec<f64> = logits.iter().map(|l| ((l - max_l) / t).exp()).collect();
        let sum: f64 = exp.iter().sum();
        exp.iter().map(|e| e / sum).collect()
    }

    pub fn sample_move(
        &self,
        rng: &mut impl Rng,
        board: &Board,
        moves: &[Move],
        player: i8,
        last_move: Option<Move>,
        temperature: f64,
    ) -> Option<Move> {
        if moves.is_empty() {
            return None;
        }
        let probs = self.probs(board, moves, player, last_move, temperature);
        let idx = WeightedIndex::new(&probs).ok()?.sample(rng);
        Some(moves[idx])
    }

    pub fn best_move(
        &self,
        board: &Board,
        moves: &[Move],
        player: i8,
        last_move: Option<Move>,
    ) -> Option<Move> {
        if moves.is_empty() {
            return None;
        }
        let logits = self.logits(board, moves, player, last_move);
        let (idx, _) = logits
            .iter()
            .enumerate()
            .max_by(|a, b| a.1.partial_cmp(b.1).unwrap())
            .unwrap();
        Some(moves[idx])
    }

    pub fn save(&self, path: &Path) -> Result<()> {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let file = File::create(path).with_context(|| format!("création {path:?}"))?;
        serde_json::to_writer_pretty(BufWriter::new(file), self)?;
        Ok(())
    }

    pub fn load(path: &Path) -> Result<Self> {
        let file = File::open(path).with_context(|| format!("ouverture {path:?}"))?;
        let p: Self = serde_json::from_reader(BufReader::new(file))?;
        Ok(p)
    }
}

#[derive(Clone, Debug)]
pub struct TrajectoryStep {
    pub features: [f64; FEATURE_DIM],
    pub pos_features: [f64; POS_DIM],
    pub reward: f64,
    pub player: i8,
}

/// Policy unifiée : MLP (défaut) ou linéaire (legacy).
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum PolicyNet {
    Linear {
        weights: Vec<f64>,
        bias: f64,
        version: u64,
        steps: u64,
    },
    Mlp {
        w1: Vec<f64>,
        b1: Vec<f64>,
        w2: Vec<f64>,
        b2: Vec<f64>,
        w3: Vec<f64>,
        b3: f64,
        #[serde(default)]
        vw1: Vec<f64>,
        #[serde(default)]
        vb1: Vec<f64>,
        #[serde(default)]
        vw2: Vec<f64>,
        #[serde(default = "default_bv2_policy")]
        bv2: f64,
        version: u64,
        steps: u64,
    },
}

fn default_bv2_policy() -> f64 {
    0.0
}

impl Default for PolicyNet {
    fn default() -> Self {
        Self::new_mlp_random()
    }
}

impl PolicyNet {
    pub fn new_mlp_random() -> Self {
        let m = crate::mlp::MlpPolicy::new_random(&mut rand::thread_rng());
        Self::Mlp {
            w1: m.w1,
            b1: m.b1,
            w2: m.w2,
            b2: m.b2,
            w3: m.w3,
            b3: m.b3,
            vw1: m.vw1,
            vb1: m.vb1,
            vw2: m.vw2,
            bv2: m.bv2,
            version: m.version,
            steps: m.steps,
        }
    }

    pub fn value(&self, session: &GameSession, perspective: i8) -> f64 {
        let pos = position_features(&session.board, perspective, session.last_move);
        if let Some(m) = self.mlp_view() {
            return m.value_from_pos(&pos);
        }
        // Legacy linéaire : heuristique simple
        if let Some(w) = session.winner() {
            return if w == perspective { 1.0 } else { -1.0 };
        }
        pos[5] - pos[4] + pos[6] - pos[7]
    }

    fn mlp_to_policy(m: &crate::mlp::MlpPolicy) -> Self {
        Self::Mlp {
            w1: m.w1.clone(),
            b1: m.b1.clone(),
            w2: m.w2.clone(),
            b2: m.b2.clone(),
            w3: m.w3.clone(),
            b3: m.b3,
            vw1: m.vw1.clone(),
            vb1: m.vb1.clone(),
            vw2: m.vw2.clone(),
            bv2: m.bv2,
            version: m.version,
            steps: m.steps,
        }
    }

    pub fn version(&self) -> u64 {
        match self {
            Self::Linear { version, .. } | Self::Mlp { version, .. } => *version,
        }
    }

    fn mlp_view(&self) -> Option<crate::mlp::MlpPolicy> {
        if let Self::Mlp {
            w1,
            b1,
            w2,
            b2,
            w3,
            b3,
            vw1,
            vb1,
            vw2,
            bv2,
            version,
            steps,
        } = self
        {
            let mut m = crate::mlp::MlpPolicy {
                w1: w1.clone(),
                b1: b1.clone(),
                w2: w2.clone(),
                b2: b2.clone(),
                w3: w3.clone(),
                b3: *b3,
                vw1: if vw1.is_empty() {
                    default_vw1_mlp()
                } else {
                    vw1.clone()
                },
                vb1: if vb1.is_empty() {
                    default_vb1_mlp()
                } else {
                    vb1.clone()
                },
                vw2: if vw2.is_empty() {
                    default_vw2_mlp()
                } else {
                    vw2.clone()
                },
                bv2: *bv2,
                version: *version,
                steps: *steps,
            };
            Some(m)
        } else {
            None
        }
    }

    fn sync_mlp(&mut self, m: &crate::mlp::MlpPolicy) {
        if let Self::Mlp {
            w1,
            b1,
            w2,
            b2,
            w3,
            b3,
            vw1,
            vb1,
            vw2,
            bv2,
            version,
            steps,
        } = self
        {
            *w1 = m.w1.clone();
            *b1 = m.b1.clone();
            *w2 = m.w2.clone();
            *b2 = m.b2.clone();
            *w3 = m.w3.clone();
            *b3 = m.b3;
            *vw1 = m.vw1.clone();
            *vb1 = m.vb1.clone();
            *vw2 = m.vw2.clone();
            *bv2 = m.bv2;
            *version = m.version;
            *steps = m.steps;
        }
    }
}

fn default_vw1_mlp() -> Vec<f64> {
    vec![0.0; crate::mlp::VH * POS_DIM]
}
fn default_vb1_mlp() -> Vec<f64> {
    vec![0.0; crate::mlp::VH]
}
fn default_vw2_mlp() -> Vec<f64> {
    vec![0.0; crate::mlp::VH]
}

impl PolicyNet {

    fn linear_view(&self) -> Option<LinearPolicy> {
        if let Self::Linear {
            weights,
            bias,
            version,
            steps,
        } = self
        {
            Some(LinearPolicy {
                weights: weights.clone(),
                bias: *bias,
                version: *version,
                steps: *steps,
            })
        } else {
            None
        }
    }

    pub fn logits(
        &self,
        board: &Board,
        moves: &[Move],
        player: i8,
        last_move: Option<Move>,
    ) -> Vec<f64> {
        if let Some(m) = self.mlp_view() {
            return m.logits(board, moves, player, last_move);
        }
        if let Some(l) = self.linear_view() {
            return l.logits(board, moves, player, last_move);
        }
        vec![]
    }

    pub fn sample_move(
        &self,
        rng: &mut impl Rng,
        board: &Board,
        moves: &[Move],
        player: i8,
        last_move: Option<Move>,
        temperature: f64,
    ) -> Option<Move> {
        if let Some(m) = self.mlp_view() {
            return m.sample_move(rng, board, moves, player, last_move, temperature);
        }
        self.linear_view()?.sample_move(rng, board, moves, player, last_move, temperature)
    }

    pub fn best_move(
        &self,
        board: &Board,
        moves: &[Move],
        player: i8,
        last_move: Option<Move>,
    ) -> Option<Move> {
        if let Some(m) = self.mlp_view() {
            return m.best_move(board, moves, player, last_move);
        }
        self.linear_view()?.best_move(board, moves, player, last_move)
    }

    pub fn save(&self, path: &Path) -> Result<()> {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let file = File::create(path).with_context(|| format!("création {path:?}"))?;
        serde_json::to_writer_pretty(BufWriter::new(file), self)?;
        Ok(())
    }

    pub fn load(path: &Path) -> Result<Self> {
        let file = File::open(path).with_context(|| format!("ouverture {path:?}"))?;
        let raw: serde_json::Value = serde_json::from_reader(BufReader::new(file))?;
        if raw.get("kind").is_some() {
            return Ok(serde_json::from_value(raw)?);
        }
        // Legacy linear checkpoint
        let linear: LinearPolicy = serde_json::from_value(raw)?;
        Ok(Self::Linear {
            weights: linear.weights,
            bias: linear.bias,
            version: linear.version,
            steps: linear.steps,
        })
    }
}

pub fn reinforce_update(policy: &mut PolicyNet, batch: &[TrajectoryStep], lr: f64, value_lr: f64) {
    if batch.is_empty() {
        return;
    }
    match policy {
        PolicyNet::Mlp { .. } => {
            if let Some(mut m) = policy.mlp_view() {
                crate::mlp::reinforce_update_mlp(&mut m, batch, lr, value_lr);
                policy.sync_mlp(&m);
            }
        }
        PolicyNet::Linear {
            weights,
            bias,
            version,
            steps,
        } => {
            let mut linear = LinearPolicy {
                weights: weights.clone(),
                bias: *bias,
                version: *version,
                steps: *steps,
            };
            reinforce_update_linear(&mut linear, batch, lr);
            *weights = linear.weights;
            *bias = linear.bias;
            *version = linear.version;
            *steps = linear.steps;
        }
    }
}

/// Mise à jour REINFORCE — policy linéaire legacy.
pub fn reinforce_update_linear(
    policy: &mut LinearPolicy,
    batch: &[TrajectoryStep],
    lr: f64,
) {
    if batch.is_empty() {
        return;
    }
    let baseline: f64 = batch.iter().map(|s| s.reward).sum::<f64>() / batch.len() as f64;

    for step in batch {
        let adv = step.reward - baseline;
        for (w, f) in policy.weights.iter_mut().zip(step.features.iter()) {
            *w += lr * adv * f;
            *w = w.clamp(-10.0, 10.0);
        }
        policy.bias = (policy.bias + lr * adv).clamp(-5.0, 5.0);
    }
    policy.steps += 1;
    policy.version += 1;
}
