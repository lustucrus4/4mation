import {
  emptyRuleBoard,
  legalMoveHighlights,
  lineHighlights,
  withPieces,
  type CellValue,
  type HighlightKind,
} from "./ruleBoard";

/**
 * Schémas pédagogiques prêts à l'emploi.
 *
 * Toutes les pages « Apprendre » piochent ici plutôt que de redessiner un plateau : une
 * position n'existe qu'à un seul endroit, donc une correction (coordonnée fausse, règle
 * mal illustrée) se fait une fois pour toutes.
 *
 * Repères de lecture :
 *   - indices `row, col` de 0 à 6, comme le moteur (`row` = ligne, `col` = colonne) ;
 *   - `1` = rouge (premier joueur), `2` = bleu (second joueur) ;
 *   - le vert « valid » marque une case jouable, le ✕ « invalid » une case refusée.
 *
 * Les cases jouables ne sont jamais listées à la main : elles viennent de
 * `legalMoveHighlights`, qui applique la règle de la frontière (et sa règle de secours)
 * exactement comme le jeu. `scripts/check-diagrams.mjs` relit ensuite le catalogue.
 */

export interface LearnDiagram {
  board: CellValue[][];
  highlights?: Record<string, HighlightKind>;
  labels?: Record<string, string>;
  winLine?: [number, number][];
  caption?: string;
}

const SIZE = 7;
const EMPTY = emptyRuleBoard(SIZE);

const rowCells = (row: number): [number, number][] =>
  Array.from({ length: SIZE }, (_, col) => [row, col] as [number, number]);

const colCells = (col: number): [number, number][] =>
  Array.from({ length: SIZE }, (_, row) => [row, col] as [number, number]);

const mainDiagonal: [number, number][] = Array.from(
  { length: SIZE },
  (_, i) => [i, i] as [number, number]
);

const antiDiagonal: [number, number][] = Array.from(
  { length: SIZE },
  (_, i) => [i, SIZE - 1 - i] as [number, number]
);

/* ------------------------------------------------------------------ */
/* 1. Le plateau                                                       */
/* ------------------------------------------------------------------ */

export const emptyBoardDiagram: LearnDiagram = {
  board: EMPTY,
  caption: "Plateau vide — 7 lignes × 7 colonnes",
};

export const firstMoveDiagram: LearnDiagram = {
  board: EMPTY,
  highlights: legalMoveHighlights(EMPTY, 1, null),
  caption: "Coup nº 1 : le plateau est vide, les 49 cases sont jouables",
};

/* ------------------------------------------------------------------ */
/* 2. Les quatre directions d'alignement                               */
/* ------------------------------------------------------------------ */

const horizontalCells: [number, number][] = [
  [3, 1],
  [3, 2],
  [3, 3],
  [3, 4],
];
const verticalCells: [number, number][] = [
  [1, 3],
  [2, 3],
  [3, 3],
  [4, 3],
];
const diagonalCells: [number, number][] = [
  [1, 1],
  [2, 2],
  [3, 3],
  [4, 4],
];
const antiDiagonalCells: [number, number][] = [
  [1, 5],
  [2, 4],
  [3, 3],
  [4, 2],
];

export const winHorizontalDiagram: LearnDiagram = {
  board: withPieces(
    EMPTY,
    horizontalCells.map(([row, col]) => ({ row, col, player: 1 as const }))
  ),
  highlights: lineHighlights(horizontalCells, "win"),
  winLine: [horizontalCells[0], horizontalCells[3]],
  caption: "Horizontal — 4 pions sur la même ligne",
};

export const winVerticalDiagram: LearnDiagram = {
  board: withPieces(
    EMPTY,
    verticalCells.map(([row, col]) => ({ row, col, player: 2 as const }))
  ),
  highlights: lineHighlights(verticalCells, "win"),
  winLine: [verticalCells[0], verticalCells[3]],
  caption: "Vertical — 4 pions sur la même colonne",
};

export const winDiagonalDiagram: LearnDiagram = {
  board: withPieces(
    EMPTY,
    diagonalCells.map(([row, col]) => ({ row, col, player: 1 as const }))
  ),
  highlights: lineHighlights(diagonalCells, "win"),
  winLine: [diagonalCells[0], diagonalCells[3]],
  caption: "Diagonale ↘ — la ligne descend vers la droite",
};

export const winAntiDiagonalDiagram: LearnDiagram = {
  board: withPieces(
    EMPTY,
    antiDiagonalCells.map(([row, col]) => ({ row, col, player: 2 as const }))
  ),
  highlights: lineHighlights(antiDiagonalCells, "win"),
  winLine: [antiDiagonalCells[0], antiDiagonalCells[3]],
  caption: "Diagonale ↙ — la ligne descend vers la gauche",
};

export const winLastMoveDiagram: LearnDiagram = {
  board: withPieces(EMPTY, [
    { row: 1, col: 1, player: 1 },
    { row: 2, col: 2, player: 1 },
    { row: 3, col: 3, player: 1 },
    { row: 4, col: 4, player: 1 },
  ]),
  highlights: {
    ...lineHighlights(diagonalCells, "win"),
    "1,1": "last",
  },
  winLine: [diagonalCells[0], diagonalCells[3]],
  caption: "Le dernier coup rouge (1,1) referme la diagonale : victoire immédiate",
};

/* ------------------------------------------------------------------ */
/* 3. Le tour de jeu                                                   */
/* ------------------------------------------------------------------ */

export const turnOrderDiagram: LearnDiagram = {
  board: withPieces(EMPTY, [
    { row: 3, col: 3, player: 1 },
    { row: 3, col: 4, player: 2 },
    { row: 2, col: 3, player: 1 },
  ]),
  highlights: { "2,3": "last" },
  labels: { "3,3": "1", "3,4": "2", "2,3": "3" },
  caption: "① rouge au centre · ② bleu à droite · ③ rouge se connecte par le haut",
};

/* ------------------------------------------------------------------ */
/* 4. La frontière                                                     */
/* ------------------------------------------------------------------ */

const frontierBoard = withPieces(EMPTY, [{ row: 3, col: 3, player: 1 }]);

export const frontierDiagram: LearnDiagram = {
  board: frontierBoard,
  highlights: {
    ...legalMoveHighlights(frontierBoard, 2, { row: 3, col: 3 }),
    "3,3": "last",
    "1,1": "invalid",
    "5,5": "invalid",
  },
  caption: "Rouge joue (3,3) : bleu doit répondre sur une des 8 cases voisines (vert)",
};

const frontierMidGameBoard = withPieces(EMPTY, [
  { row: 3, col: 3, player: 1 },
  { row: 3, col: 4, player: 2 },
]);

export const frontierMidGameDiagram: LearnDiagram = {
  board: frontierMidGameBoard,
  highlights: {
    ...legalMoveHighlights(frontierMidGameBoard, 1, { row: 3, col: 4 }),
    "3,4": "last",
    "3,2": "invalid",
    "0,0": "invalid",
  },
  caption: "Seul le dernier coup compte : (3,2) touche un vieux pion rouge → refusée",
};

/**
 * Règle de secours : le dernier coup est entouré de pions, donc la frontière s'ouvre
 * aux cases vides touchant un pion adverse.
 */
const rescueRuleBoard = withPieces(EMPTY, [
  { row: 2, col: 2, player: 1 },
  { row: 2, col: 3, player: 2 },
  { row: 2, col: 4, player: 1 },
  { row: 3, col: 2, player: 2 },
  { row: 3, col: 3, player: 2 },
  { row: 3, col: 4, player: 1 },
  { row: 4, col: 2, player: 1 },
  { row: 4, col: 3, player: 2 },
  { row: 4, col: 4, player: 1 },
]);

export const rescueRuleDiagram: LearnDiagram = {
  board: rescueRuleBoard,
  highlights: {
    ...legalMoveHighlights(rescueRuleBoard, 1, { row: 3, col: 3 }),
    "3,3": "last",
    "0,0": "invalid",
    "6,6": "invalid",
  },
  caption:
    "Les 8 voisins du dernier coup bleu (3,3) sont occupés → règle de secours : rouge joue sur une case vide touchant un pion bleu",
};

/** Un coin : la frontière n'offre que 3 cases, la mobilité s'effondre. */
const cornerBoard = withPieces(EMPTY, [{ row: 0, col: 0, player: 1 }]);

export const cornerFrontierDiagram: LearnDiagram = {
  board: cornerBoard,
  highlights: {
    ...legalMoveHighlights(cornerBoard, 2, { row: 0, col: 0 }),
    "0,0": "last",
  },
  caption: "Après un coup en coin, la frontière ne laisse que 3 réponses au lieu de 8",
};

/* ------------------------------------------------------------------ */
/* 5. Menaces                                                          */
/* ------------------------------------------------------------------ */

const threatBoard = withPieces(EMPTY, [
  { row: 3, col: 1, player: 1 },
  { row: 3, col: 2, player: 1 },
  { row: 3, col: 3, player: 1 },
]);

export const threatOnFrontierDiagram: LearnDiagram = {
  board: threatBoard,
  highlights: {
    ...legalMoveHighlights(threatBoard, 2, { row: 3, col: 3 }),
    "3,3": "last",
    "3,4": "focus",
    "3,0": "invalid",
  },
  caption:
    "Rouge vient de jouer (3,3). (3,4) est sur la frontière et complète le 4 → bleu doit bloquer là. (3,0) compléterait aussi, mais hors frontière",
};

/** Menace fantôme : la ligne existe, mais sa case de complétion est hors frontière. */
const ghostThreatBoard = withPieces(EMPTY, [
  { row: 3, col: 1, player: 1 },
  { row: 3, col: 2, player: 1 },
  { row: 3, col: 3, player: 1 },
  { row: 1, col: 1, player: 2 },
]);

export const ghostThreatDiagram: LearnDiagram = {
  board: ghostThreatBoard,
  highlights: {
    ...legalMoveHighlights(ghostThreatBoard, 1, { row: 1, col: 1 }),
    "1,1": "last",
    "3,0": "invalid",
    "3,4": "invalid",
  },
  caption:
    "Trois rouges alignés, mais le dernier coup bleu (1,1) est loin : les deux cases de complétion sont hors frontière — menace fantôme",
};

/** Deux lignes de 3 qui se croisent : quatre cases de complétion possibles. */
const doubleThreatBoard = withPieces(EMPTY, [
  { row: 3, col: 1, player: 1 },
  { row: 3, col: 2, player: 1 },
  { row: 3, col: 3, player: 1 },
  { row: 1, col: 3, player: 1 },
  { row: 2, col: 3, player: 1 },
]);

export const doubleThreatDiagram: LearnDiagram = {
  board: doubleThreatBoard,
  highlights: lineHighlights(
    [
      [3, 0],
      [3, 4],
      [0, 3],
      [4, 3],
    ],
    "focus"
  ),
  caption:
    "Deux lignes de 3 qui se croisent : quatre cases de complétion. Si deux d'entre elles sont jouables au même tour, l'adversaire n'en bloque qu'une",
};

/** Gagner tout de suite : la case de complétion est légale, le gain est immédiat. */
const immediateWinBoard = withPieces(EMPTY, [
  { row: 5, col: 2, player: 1 },
  { row: 5, col: 3, player: 1 },
  { row: 5, col: 4, player: 1 },
  { row: 4, col: 5, player: 2 },
]);

export const immediateWinDiagram: LearnDiagram = {
  board: immediateWinBoard,
  highlights: {
    ...legalMoveHighlights(immediateWinBoard, 1, { row: 4, col: 5 }),
    "4,5": "last",
    "5,5": "best",
  },
  labels: { "5,5": "1" },
  caption:
    "Priorité nº 1 : gagner tout de suite. Le dernier coup bleu (4,5) rend (5,5) jouable — et (5,5) termine l'alignement rouge",
};

export const centerLinesDiagram: LearnDiagram = {
  board: withPieces(EMPTY, [{ row: 3, col: 3, player: 1 }]),
  highlights: {
    ...lineHighlights(rowCells(3), "focus"),
    ...lineHighlights(colCells(3), "focus"),
    ...lineHighlights(mainDiagonal, "focus"),
    ...lineHighlights(antiDiagonal, "focus"),
    "3,3": "win",
  },
  caption:
    "Le pion central (3,3) appartient à 4 lignes de 7 cases : c'est la case la plus connectée du plateau",
};

export const cornerLinesDiagram: LearnDiagram = {
  board: withPieces(EMPTY, [{ row: 0, col: 0, player: 1 }]),
  highlights: {
    ...lineHighlights(rowCells(0), "focus"),
    ...lineHighlights(colCells(0), "focus"),
    ...lineHighlights(mainDiagonal, "focus"),
    "0,0": "win",
  },
  caption: "Un coin n'appartient qu'à 3 lignes : deux directions sur quatre y sont perdues",
};

/**
 * Carte de chaleur du plateau : nombre d'alignements de 4 passant par chaque case.
 *
 * Chiffres produits par `scripts/check_learn_diagrams.py --windows` (16 au centre,
 * 3 dans un coin) — c'est le chiffre qui justifie « jouez au centre ».
 */
export const centerHeatmapDiagram: LearnDiagram = {
  board: EMPTY,
  labels: {
    "0,0": "3", "0,1": "4", "0,2": "5", "0,3": "7", "0,4": "5", "0,5": "4", "0,6": "3",
    "1,0": "4", "1,1": "6", "1,2": "8", "1,3": "10", "1,4": "8", "1,5": "6", "1,6": "4",
    "2,0": "5", "2,1": "8", "2,2": "11", "2,3": "13", "2,4": "11", "2,5": "8", "2,6": "5",
    "3,0": "7", "3,1": "10", "3,2": "13", "3,3": "16", "3,4": "13", "3,5": "10", "3,6": "7",
    "4,0": "5", "4,1": "8", "4,2": "11", "4,3": "13", "4,4": "11", "4,5": "8", "4,6": "5",
    "5,0": "4", "5,1": "6", "5,2": "8", "5,3": "10", "5,4": "8", "5,5": "6", "5,6": "4",
    "6,0": "3", "6,1": "4", "6,2": "5", "6,3": "7", "6,4": "5", "6,5": "4", "6,6": "3",
  },
  highlights: { "3,3": "focus" },
  caption:
    "Nombre d'alignements de 4 qui traversent chaque case : 16 au centre (3,3), 3 seulement dans un coin",
};

/* ------------------------------------------------------------------ */
/* 6. Fin de partie                                                    */
/* ------------------------------------------------------------------ */

/**
 * Plateau plein sans aucun alignement de 4 — un match nul.
 *
 * Grille cherchée par `scripts/check_learn_diagrams.py --draw-board`, qui garantit
 * l'absence de toute suite de 4 (mais aussi de toute suite de 3 ouverte).
 */
export const drawDiagram: LearnDiagram = {
  board: [
    [1, 2, 2, 1, 2, 1, 1],
    [2, 1, 1, 1, 2, 2, 1],
    [2, 2, 1, 1, 2, 2, 2],
    [1, 2, 2, 2, 1, 1, 1],
    [1, 2, 1, 1, 1, 2, 2],
    [1, 1, 2, 1, 2, 2, 1],
    [2, 1, 2, 2, 1, 1, 1],
  ],
  caption:
    "Plateau plein et aucun alignement de 4 : la partie est nulle (cas rare, mais possible)",
};

/* ------------------------------------------------------------------ */
/* 7. Ouvertures                                                       */
/* ------------------------------------------------------------------ */

/**
 * Les 10 premiers coups réellement distincts.
 *
 * Mêmes orbites que le solveur (`ORBITS` de `script/solver/build_lessons.py`) : les 39
 * autres cases du plateau vide sont des rotations ou des miroirs de celles-ci.
 */
export const distinctFirstMovesDiagram: LearnDiagram = {
  board: EMPTY,
  highlights: lineHighlights(
    [
      [0, 0],
      [0, 1],
      [0, 2],
      [0, 3],
      [1, 1],
      [1, 2],
      [1, 3],
      [2, 2],
      [2, 3],
      [3, 3],
    ],
    "focus"
  ),
  labels: {
    "0,0": "1", "0,1": "2", "0,2": "3", "0,3": "4",
    "1,1": "5", "1,2": "6", "1,3": "7",
    "2,2": "8", "2,3": "9",
    "3,3": "10",
  },
  caption:
    "Seulement 10 premiers coups vraiment différents : les 39 autres cases sont une rotation ou un miroir",
};

/** Deux cases voisines ne sont pas la même ouverture : le bord change la suite. */
export const shiftedOpeningDiagram: LearnDiagram = {
  board: EMPTY,
  highlights: {
    "3,3": "focus",
    "2,2": "focus",
  },
  labels: { "3,3": "A", "2,2": "B" },
  caption:
    "A (3,3) et B (2,2) sont deux ouvertures distinctes, pas une copie décalée : leurs continuations et leur valeur diffèrent",
};

/* ------------------------------------------------------------------ */
/* 8. Lecture de l'interface (entraîneur, puzzles)                     */
/* ------------------------------------------------------------------ */

/**
 * Légende du mode apprentissage, calquée sur le rendu réel du plateau
 * (`components/game/Board.tsx`) : liseré accent, contour jouable, ★ or, % par case.
 *
 * Les pourcentages sont des valeurs d'exemple — un schéma ne peut pas figer une
 * évaluation, qui dépend de la position.
 */
const trainerLegendBoard = withPieces(EMPTY, [
  { row: 3, col: 3, player: 1 },
  { row: 3, col: 4, player: 2 },
]);

export const trainerLegendDiagram: LearnDiagram = {
  board: trainerLegendBoard,
  highlights: {
    ...legalMoveHighlights(trainerLegendBoard, 1, { row: 3, col: 4 }),
    "3,4": "last",
    "2,4": "best",
  },
  labels: { "2,4": "62", "4,3": "41" },
  caption:
    "Lecture du plateau : liseré accent = dernier coup · contour vert = coup jouable · ★ or = meilleur coup · nombre = % de victoire (exemple)",
};

/**
 * Un puzzle en une image : un seul coup complète l'alignement.
 *
 * Rouge a (3,1), (3,2), (3,3). Le dernier coup bleu (2,4) ouvre la case (3,4), qui
 * referme la ligne. Les autres cases jouables ne complètent rien.
 */
const puzzleBoard = withPieces(EMPTY, [
  { row: 3, col: 1, player: 1 },
  { row: 3, col: 2, player: 1 },
  { row: 3, col: 3, player: 1 },
  { row: 2, col: 4, player: 2 },
]);

export const puzzleUniqueWinDiagram: LearnDiagram = {
  board: puzzleBoard,
  highlights: {
    ...legalMoveHighlights(puzzleBoard, 1, { row: 2, col: 4 }),
    "2,4": "last",
    "3,4": "best",
  },
  labels: { "3,4": "1" },
  caption:
    "Le dernier coup bleu (2,4) rend (3,4) jouable — et (3,4) referme l'alignement rouge : c'est le coup à trouver",
};
