import type { CSSProperties } from "react";

export type CellValue = 0 | 1 | 2;

export type HighlightKind = "valid" | "invalid" | "win" | "focus" | "last";

export interface RuleDiagramProps {
  /** Matrice row-major : 0 vide, 1 rouge, 2 bleu. */
  board: CellValue[][];
  /** Surbrillance par case "row,col". */
  highlights?: Record<string, HighlightKind>;
  /** Ligne gagnante à tracer (indices de cases). */
  winLine?: [number, number][];
  caption?: string;
  /** Taille compacte pour plusieurs schémas côte à côte. */
  compact?: boolean;
}

const highlightStyles: Record<HighlightKind, CSSProperties> = {
  valid: {
    outline: "2px dashed var(--color-exact)",
    outlineOffset: "-1px",
    boxShadow: "0 0 10px rgba(123, 237, 159, 0.55)",
  },
  invalid: {
    outline: "2px dashed var(--color-p1)",
    outlineOffset: "-1px",
    opacity: 0.45,
  },
  win: {
    outline: "2px solid var(--color-gold)",
    outlineOffset: "-1px",
    boxShadow: "0 0 12px rgba(255, 215, 0, 0.65)",
  },
  focus: {
    outline: "2px solid var(--color-accent)",
    outlineOffset: "-1px",
  },
  last: {
    outline: "2px solid var(--color-accent)",
    outlineOffset: "-1px",
  },
};

function cellCenterPercent(row: number, col: number, rows: number, cols: number): { x: number; y: number } {
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

export default function RuleDiagram({
  board,
  highlights = {},
  winLine,
  caption,
  compact = false,
}: RuleDiagramProps) {
  const rows = board.length;
  const cols = board[0]?.length ?? 7;

  const linePoints =
    winLine && winLine.length >= 2
      ? winLine.map(([r, c]) => {
          const p = cellCenterPercent(r, c, rows, cols);
          return `${p.x},${p.y}`;
        }).join(" ")
      : null;

  return (
    <figure className={compact ? "w-full max-w-[200px]" : "mx-auto w-full max-w-[280px]"}>
      <div
        className={[
          "relative rounded-xl border border-white/15 bg-white/5",
          compact ? "p-2" : "p-3",
        ].join(" ")}
      >
        <div
          className="grid gap-1"
          style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
          role="img"
          aria-label={caption ?? "Schéma de plateau"}
        >
          {board.map((rowArr, r) =>
            rowArr.map((value, c) => {
              const key = `${r},${c}`;
              const hl = highlights[key];
              const style: CSSProperties = {
                aspectRatio: "1",
                borderRadius: "18%",
                background: "var(--cell)",
                border: "2px solid var(--cell-border)",
                position: "relative",
                ...(hl ? highlightStyles[hl] : {}),
              };

              if (value === 1) {
                style.background = "linear-gradient(135deg, #ff4757, #c44569)";
                style.borderColor = "var(--color-p1)";
              } else if (value === 2) {
                style.background = "linear-gradient(135deg, #3742fa, #2f3542)";
                style.borderColor = "var(--color-p2)";
              }

              return (
                <div key={key} style={style} aria-hidden>
                  {hl === "invalid" && (
                    <span className="absolute inset-0 grid place-items-center text-lg font-bold text-p1">
                      ✕
                    </span>
                  )}
                </div>
              );
            })
          )}
        </div>

        {linePoints && (
          <svg
            className="pointer-events-none absolute inset-0 h-full w-full"
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            aria-hidden
          >
            <polyline
              points={linePoints}
              fill="none"
              stroke="var(--color-gold)"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
            />
          </svg>
        )}
      </div>
      {caption && (
        <figcaption className="mt-2 text-center text-xs leading-snug text-white/60">
          {caption}
        </figcaption>
      )}
    </figure>
  );
}

/** Plateau 7×7 vide. */
export function emptyRuleBoard(size = 7): CellValue[][] {
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

/** Toutes les cases valides au premier coup. */
export function firstMoveHighlights(size = 7): Record<string, HighlightKind> {
  const h: Record<string, HighlightKind> = {};
  for (let r = 0; r < size; r++) {
    for (let c = 0; c < size; c++) h[`${r},${c}`] = "valid";
  }
  return h;
}

/** Voisins 8-directions d'une case (pour schéma connexité). */
export function neighborHighlights(row: number, col: number, size = 7): Record<string, HighlightKind> {
  const h: Record<string, HighlightKind> = {};
  for (let dr = -1; dr <= 1; dr++) {
    for (let dc = -1; dc <= 1; dc++) {
      if (dr === 0 && dc === 0) continue;
      const nr = row + dr;
      const nc = col + dc;
      if (nr >= 0 && nr < size && nc >= 0 && nc < size) {
        h[`${nr},${nc}`] = "valid";
      }
    }
  }
  return h;
}
