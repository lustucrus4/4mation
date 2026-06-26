import { emptyBoard, type BoardMatrix, type Move } from "../components/game/Board";

export function boardAt(
  history: Array<{ row: number; col: number; player: number }>,
  upTo: number
): { board: BoardMatrix; lastMove: Move | null } {
  const board = emptyBoard();
  let last: Move | null = null;
  for (let i = 0; i < upTo && i < history.length; i++) {
    const m = history[i];
    board[m.row][m.col] = m.player;
    last = { row: m.row, col: m.col };
  }
  return { board, lastMove: last };
}
