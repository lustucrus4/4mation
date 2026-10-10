import { ApiError, apiFetch, friendlyApiMessage, getApiBase, getSessionId, setSessionId } from "./api";

export interface UserRating {
  mode: string;
  elo: number;
  games_played: number;
  wins: number;
  losses: number;
  draws: number;
}

export interface SavedGameSummary {
  id: string;
  game_mode: string;
  bot_id?: string;
  bot_level?: number;
  opponent_name?: string;
  opponent_elo?: number;
  result: "win" | "loss" | "draw";
  move_count: number;
  elo_before?: number;
  elo_after?: number;
  elo_delta?: number;
  started_at?: string;
  finished_at?: string;
}

export interface UserProfile {
  user: {
    id: number;
    lab211_id: string;
    username: string;
    display_name: string;
    email: string;
  };
  rating: UserRating;
  rating_online?: UserRating;
  recent_games: SavedGameSummary[];
}

export interface SavedGameDetail extends SavedGameSummary {
  human_color: number;
  winner: number | null;
  history: { index: number; player: number; row: number; col: number }[];
}

export function fetchProfile(): Promise<UserProfile> {
  return apiFetch<{ success: boolean } & UserProfile>("/api/me").then((d) => ({
    user: d.user,
    rating: d.rating,
    rating_online: d.rating_online,
    recent_games: d.recent_games,
  }));
}

export function fetchGames(limit = 20, offset = 0): Promise<SavedGameSummary[]> {
  return apiFetch<{ games: SavedGameSummary[] }>(
    `/api/me/games?limit=${limit}&offset=${offset}`
  ).then((d) => d.games);
}

export function fetchGame(id: string): Promise<SavedGameDetail> {
  return apiFetch<{ game: SavedGameDetail }>(`/api/me/games/${id}`).then((d) => d.game);
}

export type MoveClassification =
  | "best"
  | "excellent"
  | "good"
  | "inaccuracy"
  | "mistake"
  | "blunder"
  | "unknown";

export type ReviewPhase = "opening" | "middlegame" | "endgame";
export type ReviewNature = "proven" | "estimated" | "unknown";

export interface ReviewMove {
  index: number;
  player: number;
  row: number;
  col: number;
  classification: MoveClassification;
  win_rate_before: number;
  win_rate_played: number;
  win_rate_best: number;
  best_move: [number, number] | null;
  accuracy: number | null;
  source: string;
  exact: boolean;
  value_exact?: boolean;
  is_human: boolean;
  nature?: ReviewNature;
  nature_label?: string;
  verdict?: string;
  phase?: ReviewPhase;
  win_rate_loss?: number | null;
  position_status_before?: string;
  played_outcome?: string;
  missed_forced_win?: boolean;
  proven_error?: boolean;
  mate_in?: number | null;
  played_mate_in?: number | null;
}

export interface ReviewKeyMoment {
  index: number;
  player: number;
  is_human: boolean;
  row: number;
  col: number;
  phase: ReviewPhase;
  classification: MoveClassification;
  nature: ReviewNature;
  win_rate_loss: number;
  delta_p1: number;
  best_move: [number, number] | null;
  description: string;
}

export interface ReviewSummaryPlayer {
  accuracy: number | null;
  counts: Record<string, number>;
  strengths: number;
  errors: { total: number; proven: number; estimated: number };
  decisive_move: {
    index: number;
    classification: MoveClassification;
    nature: ReviewNature;
    verdict: string;
    win_rate_loss: number;
    phase: ReviewPhase;
  } | null;
  decisive_phase: ReviewPhase | null;
  text: string;
}

export interface ReviewAccuracyByPhase {
  human: Record<ReviewPhase, number | null>;
  bot: Record<ReviewPhase, number | null>;
  counts: {
    human: Record<ReviewPhase, number>;
    bot: Record<ReviewPhase, number>;
  };
}

export interface ReviewProvenStats {
  proven_moves: number;
  estimated_moves: number;
  unknown_moves: number;
  proven_errors: number;
  estimated_errors: number;
  missed_forced_wins: number;
  by_phase: Record<string, Record<string, number>>;
  mixed: boolean;
}

export interface GameReview {
  human_color: number;
  human_accuracy: number | null;
  bot_accuracy: number | null;
  moves: ReviewMove[];
  graph: { move_index: number; win_rate_p1: number; player?: number }[];
  move_count: number;
  accuracy_by_phase?: ReviewAccuracyByPhase;
  key_moments?: ReviewKeyMoment[];
  summary?: { human: ReviewSummaryPlayer; bot: ReviewSummaryPlayer };
  proven_stats?: ReviewProvenStats;
}

export function fetchGameReview(gameId: string): Promise<{
  game: SavedGameDetail;
  review: GameReview;
}> {
  return apiFetch<{ game: SavedGameDetail; review: GameReview }>(
    `/api/me/games/${gameId}/review`
  ).then((d) => ({ game: d.game, review: d.review }));
}

const API_BASE = getApiBase();

export async function fetchGameReviewStream(
  gameId: string,
  callbacks: {
    onProgress?: (current: number, total: number) => void;
    onGame?: (game: SavedGameDetail) => void;
  }
): Promise<{ game: SavedGameDetail; review: GameReview }> {
  const headers = new Headers();
  const sid = getSessionId();
  if (sid) headers.set("X-Session-Id", sid);

  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/me/games/${gameId}/review?stream=1`, {
      credentials: "include",
      headers,
    });
  } catch {
    throw new ApiError(friendlyApiMessage(0, ""), 0, "");
  }

  const newSid = res.headers.get("X-Session-Id");
  if (newSid) setSessionId(newSid);

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new ApiError(friendlyApiMessage(res.status, text), res.status, text);
  }

  const reader = res.body?.getReader();
  if (!reader) {
    throw new Error("Flux d'analyse indisponible");
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let game: SavedGameDetail | null = null;
  let review: GameReview | null = null;

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.trim()) continue;
      const event = JSON.parse(line) as {
        type: string;
        current?: number;
        total?: number;
        game?: SavedGameDetail;
        review?: GameReview;
      };

      if (event.type === "start" && event.game) {
        game = event.game;
        callbacks.onGame?.(event.game);
      } else if (event.type === "progress" && event.current != null && event.total != null) {
        callbacks.onProgress?.(event.current, event.total);
      } else if (event.type === "complete") {
        if (event.game) game = event.game;
        if (event.review) review = event.review;
      }
    }
  }

  if (buffer.trim()) {
    const event = JSON.parse(buffer) as {
      type: string;
      game?: SavedGameDetail;
      review?: GameReview;
    };
    if (event.type === "complete") {
      if (event.game) game = event.game;
      if (event.review) review = event.review;
    }
  }

  if (!game || !review) {
    throw new Error("Analyse incomplète");
  }

  return { game, review };
}
