import { apiFetch, getSessionId, setSessionId } from "./api";

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
  is_human: boolean;
}

export interface GameReview {
  human_color: number;
  human_accuracy: number | null;
  bot_accuracy: number | null;
  moves: ReviewMove[];
  graph: { move_index: number; win_rate_p1: number; player?: number }[];
  move_count: number;
}

export function fetchGameReview(gameId: string): Promise<{
  game: SavedGameDetail;
  review: GameReview;
}> {
  return apiFetch(`/api/me/games/${gameId}/review`).then((d: {
    game: SavedGameDetail;
    review: GameReview;
  }) => ({ game: d.game, review: d.review }));
}

const API_BASE = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

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

  const res = await fetch(`${API_BASE}/api/me/games/${gameId}/review?stream=1`, {
    credentials: "include",
    headers,
  });

  const newSid = res.headers.get("X-Session-Id");
  if (newSid) setSessionId(newSid);

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `Erreur ${res.status}`);
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
