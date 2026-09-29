/**
 * Briques de construction des schémas de plateau de la section « Apprendre ».
 *
 * Ces fonctions sont pures (aucun rendu) et vivent hors de `RuleDiagram.tsx` pour
 * pouvoir être relues par un script de validation Node
 * (`4mation_dashboard_dev/scripts/check-diagrams.mjs`), qui vérifie que chaque schéma
 * du catalogue est jouable et sans coordonnée fautive.
 *
 * Conventions : matrice row-major, `0` vide, `1` rouge, `2` bleu ; clés de surbrillance
 * et de libellé sous la forme `"row,col"`.
 */

export type CellValue = 0 | 1 | 2;

/**
 * Styles de surbrillance.
 *
 * `best` reprend exactement le repère du plateau de jeu (liseré or pointillé + ★), pour
 * que les schémas « comment lire » décrivent ce que le joueur voit vraiment à l'écran.
 */
export type HighlightKind = "valid" | "invalid" | "win" | "focus" | "last" | "best";

export const BOARD_SIZE = 7;

/** Plateau `size` × `size` vide. */
export function emptyRuleBoard(size = BOARD_SIZE): CellValue[][] {
  return Array.from({ length: size }, () => Array.from({ length: size }, () => 0 as CellValue));
}

/** Pose des pions sur une copie du plateau. */
export function withPieces(
  base: CellValue[][],
  pieces: { row: number; col: number; player: 1 | 2 }[]
): CellValue[][] {
  const next = base.map((row) => [...row]) as CellValue[][];
  for (const p of pieces) {
    next[p.row][p.col] = p.player;
  }
  return next;
}

/** Toutes les cases vides du plateau. */
export function emptyCells(board: CellValue[][]): { row: number; col: number }[] {
  const out: { row: number; col: number }[] = [];
  for (let row = 0; row < board.length; row++) {
    for (let col = 0; col < board[row].length; col++) {
      if (board[row][col] === 0) out.push({ row, col });
    }
  }
  return out;
}

/**
 * Coups légaux d'une position, **même règle que le jeu** (`lib/validActions.ts`) :
 * premier coup libre, sinon les voisins vides du dernier coup, sinon — quand ces
 * voisins sont tous occupés — les cases vides touchant un pion adverse.
 *
 * Les schémas ne recopient donc jamais une liste de cases jouables à la main : la
 * frontière dessinée est celle que le moteur appliquerait. C'est ce qui évite le
 * schéma qui a l'air juste mais qui marque « jouable » une case refusée par le jeu.
 */
export function legalMoves(
  board: CellValue[][],
  player: 1 | 2,
  lastMove: { row: number; col: number } | null
): { row: number; col: number }[] {
  const height = board.length;
  const width = board[0]?.length ?? 0;
  const opponent = player === 1 ? 2 : 1;
  const inside = (row: number, col: number) =>
    row >= 0 && row < height && col >= 0 && col < width;

  if (!lastMove) return emptyCells(board);

  const adjacent: { row: number; col: number }[] = [];
  for (let dr = -1; dr <= 1; dr++) {
    for (let dc = -1; dc <= 1; dc++) {
      if (dr === 0 && dc === 0) continue;
      const row = lastMove.row + dr;
      const col = lastMove.col + dc;
      if (inside(row, col) && board[row][col] === 0) adjacent.push({ row, col });
    }
  }
  if (adjacent.length > 0) return adjacent;

  const nearOpponent = (row: number, col: number) => {
    for (let dr = -1; dr <= 1; dr++) {
      for (let dc = -1; dc <= 1; dc++) {
        if (dr === 0 && dc === 0) continue;
        const r = row + dr;
        const c = col + dc;
        if (inside(r, c) && board[r][c] === opponent) return true;
      }
    }
    return false;
  };
  return emptyCells(board).filter(({ row, col }) => nearOpponent(row, col));
}

/** Surbrillance des coups légaux d'une position (« valid » par défaut). */
export function legalMoveHighlights(
  board: CellValue[][],
  player: 1 | 2,
  lastMove: { row: number; col: number } | null,
  kind: HighlightKind = "valid"
): Record<string, HighlightKind> {
  const h: Record<string, HighlightKind> = {};
  for (const { row, col } of legalMoves(board, player, lastMove)) {
    h[`${row},${col}`] = kind;
  }
  return h;
}

/**
 * Surbrillance d'une suite de cases, dans un style donné.
 *
 * C'est le raccourci des alignements : `lineHighlights([[3,1],[3,2],[3,3],[3,4]], "win")`
 * remplace quatre entrées écrites à la main, et évite les fautes de frappe sur les
 * coordonnées quand on dessine une ligne de 4.
 */
export function lineHighlights(
  cells: [number, number][],
  kind: HighlightKind = "valid"
): Record<string, HighlightKind> {
  const h: Record<string, HighlightKind> = {};
  for (const [row, col] of cells) {
    h[`${row},${col}`] = kind;
  }
  return h;
}

/** Centre d'une case, en pourcentage du plateau (tracé de la ligne gagnante). */
export function cellCenterPercent(
  row: number,
  col: number,
  rows: number,
  cols: number
): { x: number; y: number } {
  const pad = 8;
  const gap = 4;
  const innerW = 100 - pad * 2;
  const innerH = 100 - pad * 2;
  const cellW = (innerW - gap * (cols - 1)) / cols;
  const cellH = (innerH - gap * (rows - 1)) / rows;
  return {
    x: pad + col * (cellW + gap) + cellW / 2,
    y: pad + row * (cellH + gap) + cellH / 2,
  };
}
