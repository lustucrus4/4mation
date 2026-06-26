/**
 * Couche API typée du jeu 4mation (au-dessus de apiFetch).
 */
import { apiFetch, getSessionId } from "./api";

export type GameMode = "standard" | "learning";

export interface ValidAction {
  row: number;
  col: number;
}

export interface MoveHistoryEntry {
  index: number;
  player: number;
  row: number;
  col: number;
}

export interface GameState {
  board: number[][];
  current_player: number;
  is_terminal: boolean;
  winner: number | null;
  move_count: number;
  mode: GameMode;
  valid_actions: ValidAction[];
  last_move: { row: number; col: number } | null;
  history: MoveHistoryEntry[];
}

export interface Bot {
  id: string;
  name: string;
  description: string;
}

export interface AnalysisMove {
  row: number;
  col: number;
  win_rate: number;
  result?: string;
  proven_loss?: boolean;
  proven_win?: boolean;
}

export type PositionStatus =
  | "proven_losing"
  | "proven_winning"
  | "proven_draw"
  | "estimated";

export interface Analysis {
  moves?: AnalysisMove[];
  best_move?: [number, number] | null;
  win_rate_p1?: number;
  position_win_rate?: number;
  exact?: boolean;
  label?: string;
  source?: string;
  position_status?: PositionStatus;
  coverage_percent?: number;
}

interface SessionResponse {
  success: boolean;
  session_id: string;
  mode: GameMode;
  state: GameState;
}

export interface SavedGameInfo {
  game_id: string;
  elo_before?: number;
  elo_after?: number;
  elo_delta?: number;
  result?: string;
}

export interface MoveResponse {
  success: boolean;
  terminal: boolean;
  winner: number | null;
  next_player: number;
  coach_action: { row: number; col: number } | null;
  state: GameState;
  saved_game?: SavedGameInfo | null;
}

export interface AiMoveResponse {
  success: boolean;
  bot_id: string;
  action: { row: number; col: number };
  terminal: boolean;
  winner: number | null;
  state: GameState;
  saved_game?: SavedGameInfo | null;
}

export function createSession(mode: GameMode, botId?: string): Promise<SessionResponse> {
  const body: Record<string, string> = { mode };
  if (botId) body.bot_id = botId;
  return apiFetch<SessionResponse>("/api/session", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Garantit une session active ; en crée une si absente. */
export async function ensureSession(mode: GameMode, botId?: string): Promise<void> {
  if (!getSessionId()) {
    await createSession(mode, botId);
  }
}

export function getState(): Promise<GameState> {
  return apiFetch<GameState>("/api/state");
}

export function resetGame(mode: GameMode, botId?: string): Promise<{ state: GameState; mode: GameMode }> {
  const body: Record<string, string> = { mode };
  if (botId) body.bot_id = botId;
  return apiFetch("/api/reset", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function playMove(row: number, col: number): Promise<MoveResponse> {
  return apiFetch<MoveResponse>("/api/move", {
    method: "POST",
    body: JSON.stringify({ action: { row, col } }),
  });
}

export function aiMove(botId: string): Promise<AiMoveResponse> {
  return apiFetch<AiMoveResponse>("/api/ai_move", {
    method: "POST",
    body: JSON.stringify({ bot_id: botId }),
  });
}

export function analyze(timeBudgetMs = 600): Promise<{ analysis: Analysis; state: GameState }> {
  return apiFetch("/api/analyze", {
    method: "POST",
    body: JSON.stringify({ time_budget_ms: timeBudgetMs }),
  });
}

export function undoMove(count = 1): Promise<{ state: GameState }> {
  return apiFetch("/api/undo", {
    method: "POST",
    body: JSON.stringify({ count }),
  });
}

/** Revient à l'état après `moveIndex` coups (0 = début de partie). */
export function undoTo(moveIndex: number): Promise<{ state: GameState }> {
  return apiFetch("/api/undo_to", {
    method: "POST",
    body: JSON.stringify({ move_index: moveIndex }),
  });
}

export function listBots(): Promise<{ bots: Bot[] }> {
  return apiFetch("/api/bots");
}

/** Détecte une erreur « session perdue » côté serveur. */
export function isSessionLost(err: unknown): boolean {
  return err instanceof Error && /Session introuvable|Session requise/.test(err.message);
}
