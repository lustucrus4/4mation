/**
 * API entraînement RL Rust.
 */
import { apiFetch } from "./api";

export interface RlStatus {
  success?: boolean;
  running: boolean;
  pid?: number;
  step: number;
  total_games: number;
  policy_version?: number;
  cores?: number;
  self_play_batch?: number;
  last_self_play_win_rate?: number;
  last_eval_vs_level5?: number | null;
  games_per_sec?: number;
  eta_seconds?: number | null;
  started_at?: string;
  updated_at?: string;
  checkpoint?: string;
  message?: string;
  data_dir?: string;
}

export interface RlMetric {
  ts: string;
  step: number;
  event: string;
  games: number;
  self_play_win_rate_p1?: number;
  eval_vs_level5?: number;
  eval_games?: number;
  policy_version?: number;
  games_per_sec?: number;
  avg_moves?: number;
  message?: string;
}

export async function fetchRlStatus(): Promise<RlStatus> {
  return apiFetch<RlStatus>("/api/rl/status");
}

export async function fetchRlMetrics(limit = 500): Promise<RlMetric[]> {
  const res = await apiFetch<{ metrics: RlMetric[] }>(`/api/rl/metrics?limit=${limit}`);
  return res.metrics ?? [];
}
