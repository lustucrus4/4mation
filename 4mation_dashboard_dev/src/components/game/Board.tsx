import type { CSSProperties } from "react";
import { formatCellWinRate } from "../../lib/winRateDisplay";

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
  /** Dernier coup refusé (puzzles) : mis en évidence en rouge. */
  invalidMove?: Move | null;
  thinking?: boolean;
  /** Assombrir les cases vides hors coup légal (règle de connexité). */
  dimInvalid?: boolean;
  /** Assombrir toutes les cases vides (ex. tour de l'adversaire). */
  muteEmpty?: boolean;
  /** Taux de victoire par case "row,col" → 0..1 (mode apprentissage). */
  rates?: Record<string, number>;
  ratesExact?: boolean;
  /** Coup à défaite prouvée (exact) par case. */
  ratesProvenLoss?: Record<string, boolean>;
  onCellClick?: (move: Move) => void;
}

function isSame(a: Move | null | undefined, r: number, c: number): boolean {
  return !!a && a.row === r && a.col === c;
}

// `border` est volontairement éclaté en propriétés détaillées : les cases surchargent
// ensuite `borderColor` de façon conditionnelle. Avec le raccourci, la clé `borderColor`
// disparaît du style quand une case cesse d'être jouable, ce que React signale comme un
// mélange raccourci/propriété détaillée.
const cellBase: CSSProperties = {
  aspectRatio: "1",
  borderRadius: "22%",
  background: "var(--cell)",
  borderWidth: "3px",
  borderStyle: "solid",
  borderColor: "var(--cell-border)",
  position: "relative",
};

/**
 * Taille max du plateau : 560 px, mais aussi bornée par la hauteur de l'écran
 * (portable 1366×768, téléphone en paysage) pour garder le plateau et le message
 * de tour visibles sans défiler. Plancher à 17rem pour rester jouable au doigt.
 * Les navigateurs sans `dvh` ignorent ce style et retombent sur la classe max-w-[560px].
 */
const boardMaxWidth = "min(560px, max(17rem, calc(100dvh - 14rem)))";

function cellLabel(r: number, c: number, value: number, canPlay: boolean): string {
  const where = `Case ligne ${r + 1}, colonne ${c + 1}`;
  if (value === 1) return `${where} : pion rouge`;
  if (value === 2) return `${where} : pion bleu`;
  return canPlay ? `${where} : vide, jouable` : `${where} : vide`;
}

export function emptyBoard(size = 7): BoardMatrix {
  return Array.from({ length: size }, () => Array.from({ length: size }, () => 0));
}

export default function Board({
  board,
  playable = [],
  lastMove,
  bestMove,
  invalidMove,
  thinking = false,
  dimInvalid = false,
  muteEmpty = false,
  rates,
  ratesExact = false,
  ratesProvenLoss,
  onCellClick,
}: BoardProps) {
  const playableSet = new Set(playable.map((m) => `${m.row},${m.col}`));
  const showInvalid = dimInvalid && playable.length > 0;

  return (
    <div
      className="mx-auto grid aspect-square w-full max-w-[560px] grid-cols-7 gap-1.5 rounded-2xl border border-white/15 bg-white/5 p-2 sm:gap-2 sm:p-3.5"
      style={{
        maxWidth: boardMaxWidth,
        opacity: thinking ? 0.75 : 1,
        pointerEvents: thinking ? "none" : "auto",
      }}
      role="group"
      aria-label="Plateau 7 par 7"
    >
      {board.map((rowArr, r) =>
        rowArr.map((value, c) => {
          const canPlay = playableSet.has(`${r},${c}`) && value === 0;
          const style: CSSProperties = {
            ...cellBase,
            cursor: canPlay ? "pointer" : "default",
            transition: canPlay
              ? "transform 0.15s ease, border-color 0.15s ease"
              : "transform 0.15s ease",
          };

          if (canPlay) {
            style.borderColor = "rgba(255, 255, 255, 1)";
          } else if (value === 0 && (showInvalid || muteEmpty)) {
            style.opacity = 0.38;
            style.borderColor = "rgba(255, 255, 255, 0.12)";
          }

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
          if (isSame(invalidMove, r, c)) {
            style.outline = "3px solid var(--color-p1)";
            style.outlineOffset = "-2px";
            style.boxShadow = "0 0 16px rgba(255, 71, 87, 0.75)";
          }

          const key = `${r},${c}`;
          const rate = canPlay ? rates?.[key] : undefined;
          const provenLoss = canPlay ? ratesProvenLoss?.[key] : undefined;

          return (
            <button
              key={`${r}-${c}`}
              type="button"
              style={style}
              disabled={!canPlay}
              onClick={canPlay ? () => onCellClick?.({ row: r, col: c }) : undefined}
              className={canPlay ? "grid place-items-center hover:scale-[1.06]" : ""}
              aria-label={cellLabel(r, c, value, canPlay)}
            >
              {isSame(bestMove, r, c) && (
                <span className="absolute right-0.5 top-0 text-xs text-gold sm:right-1 sm:top-0.5 drop-shadow-[0_0_4px_rgba(0,0,0,0.9)]">
                  ★
                </span>
              )}
              {rate !== undefined && (
                <span
                  className="text-[0.7rem] font-bold leading-none sm:text-xs drop-shadow-[0_0_4px_rgba(0,0,0,0.85)]"
                  style={{
                    color: ratesExact
                      ? provenLoss
                        ? "var(--color-p1)"
                        : "var(--color-exact)"
                      : "var(--color-accent)",
                  }}
                >
                  {formatCellWinRate(rate, ratesExact, provenLoss)}
                </span>
              )}
            </button>
          );
        })
      )}
    </div>
  );
}
