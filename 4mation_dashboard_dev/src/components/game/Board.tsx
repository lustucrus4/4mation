import type { CSSProperties } from "react";

export type BoardMatrix = number[][];

export interface Move {
  row: number;
  col: number;
}

interface BoardProps {
  board: BoardMatrix;
  playable?: Move[];
  lastMove?: Move | null;
  bestMove?: Move | null;
  thinking?: boolean;
  /** Taux de victoire par case "row,col" → 0..1 (mode apprentissage). */
  rates?: Record<string, number>;
  ratesExact?: boolean;
  onCellClick?: (move: Move) => void;
}

function isSame(a: Move | null | undefined, r: number, c: number): boolean {
  return !!a && a.row === r && a.col === c;
}

const cellBase: CSSProperties = {
  aspectRatio: "1",
  borderRadius: "22%",
  background: "var(--cell)",
  border: "3px solid var(--cell-border)",
  position: "relative",
  transition: "transform 0.15s ease, border-color 0.15s ease",
};

export function emptyBoard(size = 7): BoardMatrix {
  return Array.from({ length: size }, () => Array.from({ length: size }, () => 0));
}

export default function Board({
  board,
  playable = [],
  lastMove,
  bestMove,
  thinking = false,
  rates,
  ratesExact = false,
  onCellClick,
}: BoardProps) {
  const playableSet = new Set(playable.map((m) => `${m.row},${m.col}`));

  return (
    <div
      className="mx-auto grid aspect-square w-full max-w-[560px] grid-cols-7 gap-2 rounded-2xl border border-white/15 bg-white/5 p-3.5"
      style={{ opacity: thinking ? 0.75 : 1, pointerEvents: thinking ? "none" : "auto" }}
      aria-label="Plateau 7 par 7"
    >
      {board.map((rowArr, r) =>
        rowArr.map((value, c) => {
          const canPlay = playableSet.has(`${r},${c}`) && value === 0;
          const style: CSSProperties = { ...cellBase, cursor: canPlay ? "pointer" : "default" };

          if (value === 1) {
            style.background = "linear-gradient(135deg, #ff4757, #c44569)";
            style.borderColor = "var(--color-p1)";
            style.boxShadow = "0 0 14px rgba(255, 71, 87, 0.5)";
          } else if (value === 2) {
            style.background = "linear-gradient(135deg, #3742fa, #2f3542)";
            style.borderColor = "var(--color-p2)";
            style.boxShadow = "0 0 14px rgba(55, 66, 250, 0.5)";
          }
          if (isSame(lastMove, r, c)) {
            style.outline = "3px solid var(--color-accent)";
            style.outlineOffset = "-2px";
          }
          if (isSame(bestMove, r, c)) {
            style.outline = "3px dashed var(--color-gold)";
            style.outlineOffset = "-2px";
            style.boxShadow = "0 0 16px rgba(255, 215, 0, 0.7)";
          }

          const rate = canPlay ? rates?.[`${r},${c}`] : undefined;

          return (
            <button
              key={`${r}-${c}`}
              type="button"
              style={style}
              disabled={!canPlay}
              onClick={canPlay ? () => onCellClick?.({ row: r, col: c }) : undefined}
              className={
                canPlay ? "grid place-items-center hover:scale-[1.06] hover:!border-accent" : ""
              }
              aria-label={`Case ${r + 1},${c + 1}`}
            >
              {isSame(bestMove, r, c) && (
                <span className="absolute right-1 top-0.5 text-xs text-gold drop-shadow-[0_0_4px_rgba(0,0,0,0.9)]">
                  ★
                </span>
              )}
              {rate !== undefined && (
                <span
                  className="text-[0.6rem] font-bold leading-none drop-shadow-[0_0_4px_rgba(0,0,0,0.85)]"
                  style={{ color: ratesExact ? "var(--color-exact)" : "var(--color-accent)" }}
                >
                  {Math.round(rate * 100)}%
                </span>
              )}
            </button>
          );
        })
      )}
    </div>
  );
}
