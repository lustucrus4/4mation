//! Policy softmax linéaire sur features de coups.

use std::fs::File;
use std::io::{BufReader, BufWriter};
use std::path::Path;

use anyhow::{Context, Result};
use formation_worker::game::{Board, Move};
use rand::distributions::{Distribution, WeightedIndex};
use rand::Rng;
use serde::{Deserialize, Serialize};

use crate::features::{move_features, FEATURE_DIM};

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

/// Mise à jour REINFORCE sur un batch de trajectoires.
pub fn reinforce_update(
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
        }
        policy.bias += lr * adv;
    }
    policy.steps += 1;
    policy.version += 1;
}

#[derive(Clone, Debug)]
pub struct TrajectoryStep {
    pub features: [f64; FEATURE_DIM],
    pub reward: f64,
    pub player: i8,
}
