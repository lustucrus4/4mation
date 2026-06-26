/** Coups légaux (règle de connexité) — aligné sur script/game/game_state.py */

export interface BoardMove {
  row: number;
  col: number;
}

export function computeValidActions(
  board: number[][],
  currentPlayer: number,
  lastMove: BoardMove | null
): BoardMove[] {
  const height = board.length;
  const width = board[0]?.length ?? 0;
  const opponent = currentPlayer === 1 ? 2 : 1;

  if (!lastMove) {
    const actions: BoardMove[] = [];
    for (let row = 0; row < height; row++) {
      for (let col = 0; col < width; col++) {
        if (board[row]?.[col] === 0) actions.push({ row, col });
      }
    }
    return actions;
  }

  const adjacentToLast: BoardMove[] = [];
  for (let dr = -1; dr <= 1; dr++) {
    for (let dc = -1; dc <= 1; dc++) {
      if (dr === 0 && dc === 0) continue;
      const row = lastMove.row + dr;
      const col = lastMove.col + dc;
      if (row >= 0 && row < height && col >= 0 && col < width && board[row]?.[col] === 0) {
        adjacentToLast.push({ row, col });
      }
    }
  }
  if (adjacentToLast.length > 0) return adjacentToLast;

  const actions: BoardMove[] = [];
  for (let row = 0; row < height; row++) {
    for (let col = 0; col < width; col++) {
      if (board[row]?.[col] !== 0) continue;
      let nearOpponent = false;
      for (let dr = -1; dr <= 1 && !nearOpponent; dr++) {
        for (let dc = -1; dc <= 1; dc++) {
          if (dr === 0 && dc === 0) continue;
          const r = row + dr;
          const c = col + dc;
          if (r >= 0 && r < height && c >= 0 && c < width && board[r]?.[c] === opponent) {
            nearOpponent = true;
            break;
          }
        }
      }
      if (nearOpponent) actions.push({ row, col });
    }
  }
  return actions;
}
