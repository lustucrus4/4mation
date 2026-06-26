import { apiFetch } from "./api";

export interface OpeningExplore {
  board: number[][];
  current_player: number;
  move_count: number;
  is_terminal: boolean;
  last_move: { row: number; col: number } | null;
  book: {
    result: string;
    win_rate: number;
    best_move: [number, number] | null;
    exact: boolean;
    ply: number;
    source: string;
  } | null;
  analysis_label: string | null;
  best_move: [number, number] | null;
  continuations: {
    move: { row: number; col: number };
    in_book: boolean;
    win_rate?: number;
    result?: string;
    exact?: boolean;
    ply?: number;
  }[];
  history: { index: number; player: number; row: number; col: number }[];
}

export interface PuzzleMove {
  player: number;
  row: number;
  col: number;
}

export interface PackPuzzleSummary {
  id: string;
  difficulty: "easy" | "medium" | "hard";
  human_moves: number;
  title: string;
  theme: string;
}

export interface PackPuzzle extends PackPuzzleSummary {
  history: PuzzleMove[];
  player_to_move: number;
}

export interface Puzzle {
  id: string;
  history: { index: number; player: number; row: number; col: number }[];
  player_to_move: number;
  solution: { row: number; col: number };
  win_rate: number;
  gap: number;
  exact: boolean;
  label: string;
  theme: string;
}

export interface PackPuzzleCheckResult {
  correct: boolean;
  reason?: string;
  history?: PuzzleMove[];
  opponent_move?: PuzzleMove | null;
  solved?: boolean;
  step?: number;
  human_moves?: number;
  player_to_move?: number;
  expected_step?: number;
}

export interface Lesson {
  id: string;
  title: string;
  level: string;
  duration_min: number;
  sections: { heading: string; body: string }[];
}

export function exploreOpening(
  moves: { row: number; col: number }[]
): Promise<OpeningExplore> {
  return apiFetch<{ success: boolean } & OpeningExplore>("/api/learn/openings/explore", {
    method: "POST",
    body: JSON.stringify({ moves }),
  }).then((d) => d as OpeningExplore);
}

export function fetchPackPuzzles(): Promise<PackPuzzleSummary[]> {
  return apiFetch<{ puzzles: PackPuzzleSummary[] }>("/api/learn/puzzles").then((d) => d.puzzles);
}

export function fetchPackPuzzle(id: string): Promise<PackPuzzle> {
  return apiFetch<{ puzzle: PackPuzzle }>(`/api/learn/puzzles/${id}`).then((d) => d.puzzle);
}

export function fetchRandomPuzzle(): Promise<Puzzle> {
  return apiFetch<{ puzzle: Puzzle }>("/api/learn/puzzles/random").then((d) => d.puzzle);
}

export function checkPackPuzzle(
  puzzleId: string,
  history: PuzzleMove[],
  move: { row: number; col: number }
): Promise<PackPuzzleCheckResult> {
  return apiFetch<PackPuzzleCheckResult>("/api/learn/puzzles/check", {
    method: "POST",
    body: JSON.stringify({
      puzzle_id: puzzleId,
      history,
      move,
    }),
  });
}

export function checkPuzzle(
  puzzle: Puzzle,
  move: { row: number; col: number }
): Promise<{ correct: boolean; solution?: { row: number; col: number }; win_rate?: number; note?: string; reason?: string }> {
  return apiFetch("/api/learn/puzzles/check", {
    method: "POST",
    body: JSON.stringify({
      history: puzzle.history,
      player_to_move: puzzle.player_to_move,
      move,
    }),
  });
}

export function fetchLessons(): Promise<Lesson[]> {
  return apiFetch<{ lessons: Lesson[] }>("/api/learn/lessons").then((d) => d.lessons);
}

export function fetchLesson(id: string): Promise<Lesson> {
  return apiFetch<{ lesson: Lesson }>(`/api/learn/lessons/${id}`).then((d) => d.lesson);
}

export const DIFFICULTY_LABELS: Record<PackPuzzleSummary["difficulty"], string> = {
  easy: "Facile (3 coups)",
  medium: "Intermédiaire (5 coups)",
  hard: "Difficile (8 coups)",
};
