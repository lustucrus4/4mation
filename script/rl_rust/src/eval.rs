//! Évaluation vs Minimax level_5 via un processus Python persistant.
//!
//! Le bot adverse (`eval_minimax.py`) est lancé **une seule fois** en mode `daemon` :
//! un coup coûtait auparavant un démarrage de Python (imports numpy + moteur + bots),
//! soit ~1 s par demi-coup, ce qui dominait tout le reste.
//!
//! Toute anomalie est fatale : un coup absent ou illégal remontait auparavant comme une
//! *nulle*, ce qui faisait passer un harnais cassé pour une défense parfaite.

use std::io::{BufRead, BufReader, BufWriter, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
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
    row: Option<usize>,
    col: Option<usize>,
    error: Option<String>,
}

impl MoveResponse {
    fn into_move(self) -> Result<Move> {
        if let Some(err) = self.error {
            anyhow::bail!("bot Python en erreur : {err}");
        }
        match (self.row, self.col) {
            (Some(r), Some(c)) => Ok((r, c)),
            _ => anyhow::bail!("réponse du bot Python sans coup"),
        }
    }
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
            timeout: Duration::from_secs(600),
            max_moves: 120,
            use_az_mcts: true,
        }
    }
}

fn board_to_json(board: &Board) -> Vec<Vec<i8>> {
    board.iter().map(|row| row.to_vec()).collect()
}

/// Processus Python longue durée (`eval_minimax.py daemon`) — évite 1 spawn/coup.
pub struct MinimaxBridge {
    child: Child,
    stdin: BufWriter<ChildStdin>,
    stdout: BufReader<ChildStdout>,
}

impl MinimaxBridge {
    pub fn spawn(cfg: &EvalConfig) -> Result<Self> {
        let script = if cfg.script_path.is_absolute() {
            cfg.script_path.clone()
        } else {
            cfg.project_root.join(&cfg.script_path)
        };
        let mut command = Command::new(&cfg.python);
        if cfg.python == "py" {
            command.arg("-3");
        }
        let mut child = command
            .arg("-u")
            .arg(&script)
            .arg("daemon")
            .current_dir(&cfg.project_root)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            // Hérité plutôt que pipé : un pipe stderr jamais lu bloquerait le daemon.
            .stderr(Stdio::inherit())
            .spawn()
            .with_context(|| format!("lancement du daemon {script:?}"))?;

        let stdin = child.stdin.take().context("stdin daemon")?;
        let stdout = child.stdout.take().context("stdout daemon")?;
        Ok(Self {
            child,
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
        let input = serde_json::to_string(&req)?;
        writeln!(self.stdin, "{input}")?;
        self.stdin.flush()?;

        let mut line = String::new();
        let read = self.stdout.read_line(&mut line)?;
        if read == 0 {
            anyhow::bail!("daemon d'évaluation terminé (flux fermé)");
        }
        let resp: MoveResponse = serde_json::from_str(line.trim())
            .with_context(|| format!("réponse illisible du daemon : {}", line.trim()))?;
        resp.into_move().map(Some)
    }
}

impl Drop for MinimaxBridge {
    fn drop(&mut self) {
        let _ = self.stdin.write_all(b"
");
        let _ = self.stdin.flush();
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
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
    let mut truncated = 0u32;
    // Les résultats par siège : dans ce jeu le premier joueur est nettement avantagé,
    // un score global de 50 % peut donc ne rien dire du réseau. Ce qui compte, c'est
    // le score du réseau **quand il commence** et **quand il subit**.
    let mut seat = [SeatStats::default(); 2];

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

        let bucket = &mut seat[(rl_player - 1) as usize];
        bucket.games += 1;
        let plies = session.move_count;
        if session.is_terminal() {
            match session.winner() {
                Some(w) if w == rl_player => {
                    rl_wins += 1;
                    bucket.wins += 1;
                    tracing::info!("partie {g} : réseau = joueur {rl_player}, gagne en {plies} demi-coups");
                }
                Some(w) => {
                    bot_wins += 1;
                    bucket.losses += 1;
                    tracing::info!(
                        "partie {g} : réseau = joueur {rl_player}, perd (joueur {w}) en {plies} demi-coups"
                    );
                }
                None => {
                    draws += 1;
                    bucket.draws += 1;
                    tracing::info!("partie {g} : réseau = joueur {rl_player}, nulle en {plies} demi-coups");
                }
            }
        } else {
            truncated += 1;
            draws += 1;
            bucket.draws += 1;
            tracing::info!("partie {g} : réseau = joueur {rl_player}, coupée à {plies} demi-coups");
        }
    }

    if truncated > 0 {
        tracing::warn!("{truncated} partie(s) coupée(s) à la limite de demi-coups, comptées comme nulles");
    }

    Ok(EvalResult {
        games: cfg.games,
        rl_wins,
        bot_wins,
        draws,
        truncated,
        win_rate: rl_wins as f64 / cfg.games.max(1) as f64,
        seat,
    })
}

/// Résultats du réseau pour un siège donné (1 = il commence, 2 = il subit).
#[derive(Clone, Copy, Debug, Default)]
pub struct SeatStats {
    pub games: u32,
    pub wins: u32,
    pub draws: u32,
    pub losses: u32,
}

impl SeatStats {
    /// Score espéré (victoire = 1, nulle = 0,5), la grandeur du jeu.
    pub fn score(&self) -> f64 {
        if self.games == 0 {
            return 0.0;
        }
        (self.wins as f64 + 0.5 * self.draws as f64) / self.games as f64
    }
}

#[derive(Clone, Debug)]
pub struct EvalResult {
    pub games: usize,
    pub rl_wins: u32,
    pub bot_wins: u32,
    pub draws: u32,
    /// Parties arrêtées à la limite de demi-coups (`max_moves`) faute de vainqueur.
    pub truncated: u32,
    pub win_rate: f64,
    /// Index 0 : réseau au premier coup, index 1 : réseau en second.
    pub seat: [SeatStats; 2],
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
