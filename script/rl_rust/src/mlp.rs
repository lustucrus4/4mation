//! Réseau MLP 12→64→32→1 pour scorer les coups.

use std::fs::File;
use std::io::{BufReader, BufWriter};
use std::path::Path;

use anyhow::{Context, Result};
use formation_worker::game::{Board, Move};
use rand::distributions::{Distribution, WeightedIndex};
use rand::Rng;
use serde::{Deserialize, Serialize};

use crate::features::{move_features, FEATURE_DIM, POS_DIM};

pub const H1: usize = 64;
pub const H2: usize = 32;
pub const VH: usize = 24;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct MlpPolicy {
    pub w1: Vec<f64>,
    pub b1: Vec<f64>,
    pub w2: Vec<f64>,
    pub b2: Vec<f64>,
    pub w3: Vec<f64>,
    pub b3: f64,
    /// Tête value (AlphaZero-lite) : position → VH → tanh
    #[serde(default = "default_vw1")]
    pub vw1: Vec<f64>,
    #[serde(default = "default_vb1")]
    pub vb1: Vec<f64>,
    #[serde(default = "default_vw2")]
    pub vw2: Vec<f64>,
    #[serde(default = "default_bv2")]
    pub bv2: f64,
    pub version: u64,
    pub steps: u64,
}

fn default_vw1() -> Vec<f64> {
    vec![0.0; VH * POS_DIM]
}
fn default_vb1() -> Vec<f64> {
    vec![0.0; VH]
}
fn default_vw2() -> Vec<f64> {
    vec![0.0; VH]
}
fn default_bv2() -> f64 {
    0.0
}

struct ForwardCache {
    feats: [f64; FEATURE_DIM],
    pre_h1: [f64; H1],
    h1: [f64; H1],
    pre_h2: [f64; H2],
    h2: [f64; H2],
    logit: f64,
}

impl Default for MlpPolicy {
    fn default() -> Self {
        Self::new_random(&mut rand::thread_rng())
    }
}

impl MlpPolicy {
    pub fn new_random(rng: &mut impl Rng) -> Self {
        let scale1 = (2.0 / FEATURE_DIM as f64).sqrt();
        let scale2 = (2.0 / H1 as f64).sqrt();
        let scale3 = (2.0 / H2 as f64).sqrt();

        let mut w1 = vec![0.0; H1 * FEATURE_DIM];
        for w in &mut w1 {
            *w = rng.gen_range(-scale1..scale1);
        }
        let mut w2 = vec![0.0; H2 * H1];
        for w in &mut w2 {
            *w = rng.gen_range(-scale2..scale2);
        }
        let mut w3 = vec![0.0; H2];
        for w in &mut w3 {
            *w = rng.gen_range(-scale3..scale3);
        }

        let mut vw2 = vec![0.0; VH];
        for w in &mut vw2 {
            *w = rng.gen_range(-scale3..scale3);
        }
        let mut vw1 = vec![0.0; VH * POS_DIM];
        let scale_v = (2.0 / POS_DIM as f64).sqrt();
        for w in &mut vw1 {
            *w = rng.gen_range(-scale_v..scale_v);
        }

        Self {
            w1,
            b1: vec![0.0; H1],
            w2,
            b2: vec![0.0; H2],
            w3,
            b3: 0.0,
            vw1,
            vb1: vec![0.0; VH],
            vw2,
            bv2: 0.0,
            version: 0,
            steps: 0,
        }
    }

    fn relu(x: f64) -> f64 {
        x.max(0.0)
    }

    fn relu_grad(x: f64) -> f64 {
        if x > 0.0 { 1.0 } else { 0.0 }
    }

    pub fn score(&self, feats: &[f64; FEATURE_DIM]) -> f64 {
        self.forward_cache(feats).logit
    }

    pub fn value_from_pos(&self, pos: &[f64; POS_DIM]) -> f64 {
        let mut pre = [0.0; VH];
        let mut h = [0.0; VH];
        for i in 0..VH {
            let mut s = self.vb1[i];
            for j in 0..POS_DIM {
                s += self.vw1[i * POS_DIM + j] * pos[j];
            }
            pre[i] = s;
            h[i] = Self::relu(s);
        }
        let mut logit = self.bv2;
        for i in 0..VH {
            logit += self.vw2[i] * h[i];
        }
        logit.tanh()
    }

    pub fn backward_value(&mut self, pos: &[f64; POS_DIM], target: f64, lr: f64) {
        let mut pre = [0.0; VH];
        let mut h = [0.0; VH];
        for i in 0..VH {
            let mut s = self.vb1[i];
            for j in 0..POS_DIM {
                s += self.vw1[i * POS_DIM + j] * pos[j];
            }
            pre[i] = s;
            h[i] = Self::relu(s);
        }
        let mut logit = self.bv2;
        for i in 0..VH {
            logit += self.vw2[i] * h[i];
        }
        let pred = logit.tanh();
        let grad_out = (pred - target).clamp(-1.0, 1.0);

        let d_logit = grad_out * (1.0 - pred * pred);
        for i in 0..VH {
            let gh = d_logit * self.vw2[i] * Self::relu_grad(pre[i]);
            self.vw2[i] -= lr * d_logit * h[i];
            self.vw2[i] = self.vw2[i].clamp(-5.0, 5.0);
            self.vb1[i] -= lr * gh;
            for j in 0..POS_DIM {
                self.vw1[i * POS_DIM + j] -= lr * gh * pos[j];
                self.vw1[i * POS_DIM + j] = self.vw1[i * POS_DIM + j].clamp(-5.0, 5.0);
            }
        }
        self.bv2 -= lr * d_logit;
        self.bv2 = self.bv2.clamp(-3.0, 3.0);
    }

    fn forward_cache(&self, feats: &[f64; FEATURE_DIM]) -> ForwardCache {
        let mut pre_h1 = [0.0; H1];
        let mut h1 = [0.0; H1];
        for i in 0..H1 {
            let mut s = self.b1[i];
            for j in 0..FEATURE_DIM {
                s += self.w1[i * FEATURE_DIM + j] * feats[j];
            }
            pre_h1[i] = s;
            h1[i] = Self::relu(s);
        }

        let mut pre_h2 = [0.0; H2];
        let mut h2 = [0.0; H2];
        for i in 0..H2 {
            let mut s = self.b2[i];
            for j in 0..H1 {
                s += self.w2[i * H1 + j] * h1[j];
            }
            pre_h2[i] = s;
            h2[i] = Self::relu(s);
        }

        let mut logit = self.b3;
        for i in 0..H2 {
            logit += self.w3[i] * h2[i];
        }

        ForwardCache {
            feats: *feats,
            pre_h1,
            h1,
            pre_h2,
            h2,
            logit,
        }
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

    pub fn backward_step(&mut self, feats: &[f64; FEATURE_DIM], advantage: f64, lr: f64) {
        let c = self.forward_cache(feats);
        let grad_out = advantage.clamp(-1.0, 1.0);

        let mut dh2 = [0.0; H2];
        for i in 0..H2 {
            dh2[i] = grad_out * self.w3[i];
            self.w3[i] += lr * grad_out * c.h2[i];
            self.w3[i] = self.w3[i].clamp(-5.0, 5.0);
        }
        self.b3 += lr * grad_out;
        self.b3 = self.b3.clamp(-3.0, 3.0);

        let mut dh1 = [0.0; H1];
        for i in 0..H2 {
            let gh = dh2[i] * Self::relu_grad(c.pre_h2[i]);
            self.b2[i] += lr * gh;
            for j in 0..H1 {
                dh1[j] += gh * self.w2[i * H1 + j];
                self.w2[i * H1 + j] += lr * gh * c.h1[j];
                self.w2[i * H1 + j] = self.w2[i * H1 + j].clamp(-5.0, 5.0);
            }
        }

        for i in 0..H1 {
            let gh = dh1[i] * Self::relu_grad(c.pre_h1[i]);
            self.b1[i] += lr * gh;
            for j in 0..FEATURE_DIM {
                self.w1[i * FEATURE_DIM + j] += lr * gh * c.feats[j];
                self.w1[i * FEATURE_DIM + j] =
                    self.w1[i * FEATURE_DIM + j].clamp(-5.0, 5.0);
            }
        }
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

pub fn reinforce_update_mlp(
    policy: &mut MlpPolicy,
    batch: &[crate::policy::TrajectoryStep],
    lr: f64,
    value_lr: f64,
) {
    if batch.is_empty() {
        return;
    }
    let baseline: f64 = batch.iter().map(|s| s.reward).sum::<f64>() / batch.len() as f64;
    for step in batch {
        policy.backward_step(&step.features, step.reward - baseline, lr);
        policy.backward_value(&step.pos_features, step.reward, value_lr);
    }
    policy.steps += 1;
    policy.version += 1;
}
