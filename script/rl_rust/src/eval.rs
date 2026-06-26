//! Évaluation vs Minimax level_5 via subprocess Python.

use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::Duration;

use anyhow::{Context, Result};
use formation_worker::game::{Board, Move, BOARD_SIZE};
use rand::rngs::StdRng;
use rand::SeedableRng;
use serde::{Deserialize, Serialize};

use crate::game_session::GameSession;
use crate::mcts::MctsLite;
use crate::policy::LinearPolicy;

#[derive(Serialize)]
struct MoveRequest {
    board: Vec<Vec<i8>>,
    current_player: i8,
    last_move: Option<[usize; 2]>,
    bot_id: String,
}

#[derive(Deserialize)]
struct MoveResponse {
    row: usize,
    col: usize,
}

pub struct EvalConfig {
    pub games: usize,
    pub mcts_sims: u32,
    pub python: String,
    pub script_path: PathBuf,
    pub project_root: PathBuf,
    pub bot_id: String,
    pub timeout: Duration,
}

impl Default for EvalConfig {
    fn default() -> Self {
        Self {
            games: 20,
            mcts_sims: 12,
            python: "py".to_string(),
            script_path: PathBuf::from("script/rl_rust/eval_minimax.py"),
            project_root: PathBuf::from("."),
            bot_id: "level_5".to_string(),
            timeout: Duration::from_secs(120),
        }
    }
}

fn board_to_json(board: &Board) -> Vec<Vec<i8>> {
    board
        .iter()
        .map(|row| row.to_vec())
        .collect()
}

pub fn call_minimax_move(cfg: &EvalConfig, session: &GameSession) -> Result<Option<Move>> {
    let req = MoveRequest {
        board: board_to_json(&session.board),
        current_player: session.current_player,
        last_move: session.last_move.map(|(r, c)| [r, c]),
        bot_id: cfg.bot_id.clone(),
    };
    let input = serde_json::to_string(&req)?;
    let script = if cfg.script_path.is_absolute() {
        cfg.script_path.clone()
    } else {
        cfg.project_root.join(&cfg.script_path)
    };

    let mut child = Command::new(&cfg.python)
        .arg("-3")
        .arg(&script)
        .arg("move")
        .current_dir(&cfg.project_root)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .with_context(|| "lancement eval_minimax.py")?;

    if let Some(stdin) = child.stdin.as_mut() {
        stdin.write_all(input.as_bytes())?;
    }

    let output = child.wait_with_output()?;
    if !output.status.success() {
        let err = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!("eval_minimax.py échec: {err}");
    }

    let resp: MoveResponse = serde_json::from_slice(&output.stdout)?;
    Ok(Some((resp.row, resp.col)))
}

pub fn evaluate_vs_minimax(
    policy: &LinearPolicy,
    cfg: &EvalConfig,
    seed: u64,
) -> Result<EvalResult> {
    let mut rng = StdRng::seed_from_u64(seed);
    let mcts = MctsLite {
        sims_per_move: cfg.mcts_sims,
    };

    let mut rl_wins = 0u32;
    let mut bot_wins = 0u32;
    let mut draws = 0u32;

    for g in 0..cfg.games {
        let mut session = GameSession::new();
        let rl_player: i8 = if g % 2 == 0 { 1 } else { 2 };

        while !session.is_terminal() && session.move_count < 100 {
            let is_rl_turn = session.current_player == rl_player;
            let mv = if is_rl_turn {
                mcts
                    .choose_move(policy, &session, &mut rng)
                    .or_else(|| {
                        policy.best_move(
                            &session.board,
                            &session.legal_moves(),
                            session.current_player,
                            session.last_move,
                        )
                    })
            } else {
                call_minimax_move(cfg, &session)?
            };

            let Some(chosen) = mv else { break };
            if !session.apply(chosen) {
                break;
            }
        }

        match session.winner() {
            Some(w) if w == rl_player => rl_wins += 1,
            Some(_) => bot_wins += 1,
            None => draws += 1,
        }
    }

    Ok(EvalResult {
        games: cfg.games,
        rl_wins,
        bot_wins,
        draws,
        win_rate: rl_wins as f64 / cfg.games.max(1) as f64,
    })
}

#[derive(Clone, Debug)]
pub struct EvalResult {
    pub games: usize,
    pub rl_wins: u32,
    pub bot_wins: u32,
    pub draws: u32,
    pub win_rate: f64,
}

pub fn resolve_paths(data_dir: &Path) -> (PathBuf, PathBuf) {
    let rl_dir = data_dir
        .parent()
        .map(|p| p.to_path_buf())
        .unwrap_or_else(|| PathBuf::from("script/rl_rust"));

    let script = rl_dir.join("eval_minimax.py");

    let mut root = rl_dir
        .parent()
        .and_then(|script_dir| script_dir.parent())
        .map(|p| p.to_path_buf())
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or_else(|| {
            std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
        });

    if !script.exists() {
        if let Ok(cwd) = std::env::current_dir() {
            let alt = cwd.join("script/rl_rust/eval_minimax.py");
            if alt.exists() {
                root = cwd;
                return (alt, root);
            }
        }
    }

    (script, root)
}

#[allow(dead_code)]
fn empty_board() -> Board {
    [[0i8; BOARD_SIZE]; BOARD_SIZE]
}
