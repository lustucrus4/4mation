import type { MoveClassification } from "./accountApi";

export interface AnalysisSnapshot {
  winRateP1: number;
  bestMove: { row: number; col: number } | null;
  rates: Record<string, number>;
}

const THRESHOLDS: [MoveClassification, number][] = [
  ["best", 0.01],
  ["excellent", 0.03],
  ["good", 0.08],
  ["inaccuracy", 0.15],
  ["mistake", 0.30],
];

export function classifyMoveLoss(winRateLoss: number, isBest: boolean): MoveClassification {
  if (isBest) return "best";
  for (const [label, maxLoss] of THRESHOLDS) {
    if (winRateLoss <= maxLoss) return label;
  }
  return "blunder";
}

export function moveAccuracy(winRateLoss: number, isBest: boolean): number {
  if (isBest) return 100;
  return Math.max(0, Math.min(100, 100 - winRateLoss * 200));
}

export function winRateP1(winRate: number, player: number): number {
  return player === 1 ? winRate : 1 - winRate;
}

/** Classifie un coup humain à partir de l'analyse affichée avant le coup. */
export function classifyFromAnalysis(
  analysis: AnalysisSnapshot,
  row: number,
  col: number
): {
  classification: MoveClassification;
  accuracy: number | null;
  winRatePlayed: number;
  winRateBest: number;
} {
  const key = `${row},${col}`;
  const moves = Object.entries(analysis.rates).map(([k, wr]) => {
    const [r, c] = k.split(",").map(Number);
    return { row: r, col: c, win_rate: wr };
  });
  moves.sort((a, b) => b.win_rate - a.win_rate);

  const bestWr = moves[0]?.win_rate ?? analysis.winRateP1;
  const playedWr = analysis.rates[key] ?? bestWr;
  const bestMove = analysis.bestMove;
  const isBest =
    (bestMove?.row === row && bestMove?.col === col) || playedWr >= bestWr - 0.001;
  const loss = Math.max(0, bestWr - playedWr);
  const classification = classifyMoveLoss(loss, isBest);

  return {
    classification,
    accuracy: moveAccuracy(loss, isBest),
    winRatePlayed: playedWr,
    winRateBest: bestWr,
  };
}
