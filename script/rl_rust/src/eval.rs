//! Évaluation vs Minimax level_5 (processus Python persistant).

use std::io::{BufRead, BufReader, BufWriter, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::time::Duration;

use anyhow::{Context, Result};
use formation_worker::game::{Board, Move, BOARD_SIZE};
use rand::rngs::StdRng;
use rand::SeedableRng;
use serde::{Deserialize, Serialize};

use crate::az_mcts::MctsAz;
use crate::game_session::GameSession;
use crate::mcts::MctsLite;
use crate::policy::PolicyNet;

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

#[derive(Clone)]
pub struct EvalConfig {
    pub games: usize,
    pub mcts_sims: u32,
    pub python: String,
    pub script_path: PathBuf,
    pub project_root: PathBuf,
    pub bot_id: String,
    pub timeout: Duration,
    pub max_moves: u32,
    pub use_az_mcts: bool,
}

impl Default for EvalConfig {
    fn default() -> Self {
        Self {
            games: 12,
            mcts_sims: 16,
            python: "py".to_string(),
            script_path: PathBuf::from("script/rl_rust/eval_minimax.py"),
            project_root: PathBuf::from("."),
            bot_id: "level_5".to_string(),
            timeout: Duration::from_secs(120),
            max_moves: 120,
            use_az_mcts: true,
        }
    }
}

/// Processus Python longue durée (`eval_minimax.py daemon`) — évite 1 spawn/coup.
pub struct MinimaxBridge {
    _child: Child,
    stdin: BufWriter<ChildStdin>,
    stdout: BufReader<std::process::ChildStdout>,
}

impl MinimaxBridge {
    pub fn spawn(cfg: &EvalConfig) -> Result<Self> {
        let script = if cfg.script_path.is_absolute() {
            cfg.script_path.clone()
        } else {
            cfg.project_root.join(&cfg.script_path)
        };

        let mut child = Command::new(&cfg.python)
            .arg("-3")
            .arg("-u")
            .arg(&script)
            .arg("daemon")
            .current_dir(&cfg.project_root)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .with_context(|| format!("lancement daemon {script:?}"))?;

        let stdin = child.stdin.take().context("stdin daemon")?;
        let stdout = child.stdout.take().context("stdout daemon")?;

        Ok(Self {
            _child: child,
            stdin: BufWriter::new(stdin),
            stdout: BufReader::new(stdout),
        })
    }

    pub fn choose_move(&mut self, cfg: &EvalConfig, session: &GameSession) -> Result<Option<Move>> {
        let req = MoveRequest {
            board: board_to_json(&session.board),
            current_player: session.current_player,
            last_move: session.last_move.map(|(r, c)| [r, c]),
            bot_id: cfg.bot_id.clone(),
        };
        let line = serde_json::to_string(&req)?;
        self.stdin.write_all(line.as_bytes())?;
        self.stdin.write_all(b"\n")?;
        self.stdin.flush()?;

        let mut resp_line = String::new();
        self.stdout.read_line(&mut resp_line)?;
        if resp_line.trim().is_empty() {
            anyhow::bail!("daemon Python: réponse vide");
        }
        let resp: MoveResponse = serde_json::from_str(resp_line.trim())
            .context("daemon Python: JSON invalide")?;
        Ok(Some((resp.row, resp.col)))
    }
}

fn board_to_json(board: &Board) -> Vec<Vec<i8>> {
    board.iter().map(|row| row.to_vec()).collect()
}

pub fn evaluate_vs_minimax(
    policy: &PolicyNet,
    cfg: &EvalConfig,
    bridge: &mut MinimaxBridge,
    seed: u64,
) -> Result<EvalResult> {
    let mut rng = StdRng::seed_from_u64(seed);
    let mcts = MctsLite {
        sims_per_move: cfg.mcts_sims,
    };
    let az = MctsAz {
        sims: cfg.mcts_sims,
    };

    let mut rl_wins = 0u32;
    let mut bot_wins = 0u32;
    let mut draws = 0u32;

    for g in 0..cfg.games {
        let mut session = GameSession::new();
        let rl_player: i8 = if g % 2 == 0 { 1 } else { 2 };

        while !session.is_terminal() && session.move_count < cfg.max_moves {
            let is_rl_turn = session.current_player == rl_player;
            let side: &str = if is_rl_turn { "agent" } else { cfg.bot_id.as_str() };
            let mv = if is_rl_turn {
                if cfg.use_az_mcts && cfg.mcts_sims > 0 {
                    az.choose_move(policy, &session, &mut rng)
                } else if cfg.mcts_sims > 0 {
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
                    policy.best_move(
                        &session.board,
                        &session.legal_moves(),
                        session.current_player,
                        session.last_move,
                    )
                }
            } else {
                bridge.choose_move(cfg, &session)?
            };

            let Some(chosen) = mv else {
                // Plus aucun coup jouable : fin de partie légitime.
                if session.legal_moves().is_empty() {
                    break;
                }
                anyhow::bail!(
                    "eval: {side} n'a proposé aucun coup (coup n°{})",
                    session.move_count + 1
                );
            };
            // Un coup refusé est un bug de protocole (adversaire qui répond sur une
            // autre position, par exemple), pas une fin de partie : compter une nulle
            // ici masquerait la panne derrière un harnais silencieusement cassé.
            if !session.apply(chosen) {
                anyhow::bail!(
                    "eval: {side} a joué un coup illégal {:?} (coup n°{}), coups légaux {:?}",
                    chosen,
                    session.move_count + 1,
                    session.legal_moves()
                );
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

pub fn resolve_paths(_data_dir: &Path) -> (PathBuf, PathBuf) {
    let rl_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let script = rl_dir.join("eval_minimax.py");
    let project_root = rl_dir
        .parent()
        .and_then(|script_dir| script_dir.parent())
        .map(|p| p.to_path_buf())
        .unwrap_or_else(|| rl_dir.clone());
    (script, project_root)
}

#[allow(dead_code)]
fn empty_board() -> Board {
    [[0i8; BOARD_SIZE]; BOARD_SIZE]
}
