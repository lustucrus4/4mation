//! Client HTTP vers l'API solveur (connexion persistante reqwest).

use anyhow::{anyhow, Context, Result};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::time::Duration;
use tracing::{info, warn};

use crate::game::{parse_board, Board};
use crate::solver::{RetrogradeSolver, SolvedPosition};
pub use crate::work::{
    parse_last_move, ClaimedPosition, LastMove, SubmitMove, SubmitPayload,
};

const DEFAULT_TIMEOUT_SEC: u64 = 120;
const MAX_RETRIES: u32 = 4;

#[derive(Debug, Serialize)]
struct ClaimRequest<'a> {
    worker_id: &'a str,
    count: usize,
}

#[derive(Debug, Deserialize)]
struct ClaimResponse {
    success: bool,
    positions: Option<Vec<ClaimedPosition>>,
    error: Option<String>,
}

#[derive(Debug, Serialize)]
struct SubmitBatchRequest {
    worker_id: String,
    results: Vec<SubmitPayload>,
}

#[derive(Debug, Deserialize)]
struct SubmitBatchResponse {
    success: bool,
    submitted: Option<usize>,
    failed: Option<usize>,
    error: Option<String>,
}

#[derive(Debug, Deserialize)]
struct SubmitResponse {
    success: bool,
    error: Option<String>,
}

pub struct ApiClient {
    client: Client,
    base_url: String,
    token: Option<String>,
}

impl ApiClient {
    pub fn new(base_url: &str, token: Option<String>) -> Result<Self> {
        let client = Client::builder()
            .pool_max_idle_per_host(8)
            .tcp_keepalive(Duration::from_secs(30))
            .timeout(Duration::from_secs(DEFAULT_TIMEOUT_SEC))
            .build()
            .context("création client HTTP")?;
        Ok(Self {
            client,
            base_url: base_url.trim_end_matches('/').to_string(),
            token,
        })
    }

    fn auth_headers(&self) -> Vec<(&'static str, String)> {
        let mut h = vec![
            ("Content-Type", "application/json".to_string()),
            ("Accept", "application/json".to_string()),
        ];
        if let Some(ref t) = self.token {
            h.push(("X-Solver-Worker-Token", t.clone()));
        }
        h
    }

    async fn post_json<T: Serialize, R: for<'de> Deserialize<'de>>(
        &self,
        path: &str,
        body: &T,
    ) -> Result<R> {
        let url = format!("{}{}", self.base_url, path);
        let mut last_err: Option<anyhow::Error> = None;

        for attempt in 0..MAX_RETRIES {
            let mut req = self.client.post(&url).json(body);
            for (k, v) in self.auth_headers() {
                req = req.header(k, v);
            }
            match req.send().await {
                Ok(resp) => {
                    let status = resp.status();
                    let text = resp.text().await.unwrap_or_default();
                    if !status.is_success() {
                        return Err(anyhow!("HTTP {} : {}", status, text));
                    }
                    return serde_json::from_str(&text)
                        .with_context(|| format!("parse JSON depuis {}", url));
                }
                Err(e) => {
                    let retryable = e.is_connect() || e.is_timeout() || e.is_request();
                    last_err = Some(e.into());
                    if !retryable || attempt + 1 >= MAX_RETRIES {
                        break;
                    }
                    let sleep = Duration::from_millis(500 * 2u64.pow(attempt));
                    warn!("retry {} dans {:?} : {:?}", attempt + 1, sleep, last_err);
                    tokio::time::sleep(sleep).await;
                }
            }
        }
        Err(last_err.unwrap_or_else(|| anyhow!("requête échouée")))
    }

    pub async fn claim(&self, worker_id: &str, count: usize) -> Result<Vec<ClaimedPosition>> {
        let resp: ClaimResponse = self
            .post_json(
                "/api/solver/work/claim",
                &ClaimRequest { worker_id, count },
            )
            .await?;
        if !resp.success {
            return Err(anyhow!(
                "claim échoué : {}",
                resp.error.unwrap_or_else(|| "inconnu".into())
            ));
        }
        Ok(resp.positions.unwrap_or_default())
    }

    pub async fn submit_batch(
        &self,
        worker_id: &str,
        results: Vec<SubmitPayload>,
    ) -> Result<(usize, usize)> {
        if results.is_empty() {
            return Ok((0, 0));
        }
        let batch: SubmitBatchRequest = SubmitBatchRequest {
            worker_id: worker_id.to_string(),
            results,
        };

        let url = format!("{}/api/solver/work/submit-batch", self.base_url);
        let mut req = self.client.post(&url).json(&batch);
        for (k, v) in self.auth_headers() {
            req = req.header(k, v);
        }

        match req.send().await {
            Ok(resp) if resp.status().is_success() => {
                let text = resp.text().await?;
                let parsed: SubmitBatchResponse = serde_json::from_str(&text)?;
                if parsed.success {
                    return Ok((
                        parsed.submitted.unwrap_or(0),
                        parsed.failed.unwrap_or(0),
                    ));
                }
                return Err(anyhow!(
                    "submit-batch : {}",
                    parsed.error.unwrap_or_else(|| "inconnu".into())
                ));
            }
            Ok(resp) if resp.status().as_u16() == 404 => {
                info!("submit-batch non disponible — repli submit unitaire");
            }
            Ok(resp) => {
                let status = resp.status();
                let text = resp.text().await.unwrap_or_default();
                warn!("submit-batch HTTP {} : {}", status, text);
            }
            Err(e) => {
                warn!("submit-batch erreur réseau : {} — repli unitaire", e);
            }
        }

        let mut ok = 0usize;
        let mut fail = 0usize;
        for item in batch.results {
            let r: SubmitResponse = self.post_json("/api/solver/work/submit", &item).await?;
            if r.success {
                ok += 1;
            } else {
                fail += 1;
                warn!("submit unitaire échoué : {:?}", r.error);
            }
        }
        Ok((ok, fail))
    }

    pub async fn release(&self, worker_id: &str, hash: &str) -> Result<()> {
        #[derive(Serialize)]
        struct ReleaseReq<'a> {
            worker_id: &'a str,
            hash: &'a str,
        }
        let _: Value = self
            .post_json(
                "/api/solver/work/release",
                &ReleaseReq { worker_id, hash },
            )
            .await?;
        Ok(())
    }
}

pub fn solve_claimed(pos: &ClaimedPosition, max_empty: usize) -> Option<SubmitPayload> {
    let board: Board = parse_board(&pos.board_json);
    let player = pos.player as i8;
    let last_move = parse_last_move(&pos.last_move);

    let mut solver = RetrogradeSolver::new(max_empty);
    let solved: SolvedPosition = solver.solve_position(&board, player, last_move)?;

    let best_move = solved.best_move.map(|(r, c)| SubmitMove {
        row: r as i32,
        col: c as i32,
    });

    Some(SubmitPayload {
        hash: pos.hash.clone(),
        result: solved.result,
        win_rate: solved.win_rate,
        best_move,
        depth_remaining: solved.depth_remaining,
        board_json: pos.board_json.clone(),
        player: pos.player,
        last_move: pos.last_move.clone(),
        worker_id: String::new(),
    })
}

// Réexport pour compatibilité des imports existants depuis api_client
