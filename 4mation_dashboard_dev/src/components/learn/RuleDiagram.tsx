import type { CSSProperties } from "react";
import {
  cellCenterPercent,
  type CellValue,
  type HighlightKind,
} from "./ruleBoard";

export * from "./ruleBoard";

export interface RuleDiagramProps {
  /** Matrice row-major : 0 vide, 1 rouge, 2 bleu. */
  board: CellValue[][];
  /** Surbrillance par case "row,col". */
  highlights?: Record<string, HighlightKind>;
  /**
   * Texte court affiché au centre d'une case, par case "row,col".
   *
   * Sert à montrer un **ordre de coups** (① ② ③) ou un repère de lecture (A, B…).
   * Un libellé prend la place du ✕ : sur une case étiquetée, la surbrillance
   * `invalid` se contente de griser la case.
   */
  labels?: Record<string, string>;
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
  best: {
    outline: "2px dashed var(--color-gold)",
    outlineOffset: "-1px",
    boxShadow: "0 0 10px rgba(255, 215, 0, 0.6)",
  },
};

export default function RuleDiagram({
  board,
  highlights = {},
  labels = {},
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
              const label = labels[key];
              const style: CSSProperties = {
                aspectRatio: "1",
                borderRadius: "18%",
                background: "var(--cell)",
                borderWidth: "2px",
                borderStyle: "solid",
                borderColor: "var(--cell-border)",
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
                  {hl === "best" && (
                    <span
                      className={[
                        "absolute right-0.5 top-0 leading-none text-gold",
                        compact ? "text-[9px]" : "text-xs",
                      ].join(" ")}
                      style={{ textShadow: "0 0 4px rgba(0,0,0,0.9)" }}
                    >
                      ★
                    </span>
                  )}
                  {label ? (
                    <span
                      className={[
                        "absolute inset-0 grid place-items-center font-bold text-white",
                        compact ? "text-[10px] leading-none" : "text-sm",
                      ].join(" ")}
                      style={{ textShadow: "0 1px 2px rgba(0,0,0,0.85)" }}
                    >
                      {label}
                    </span>
                  ) : (
                    hl === "invalid" && (
                      <span className="absolute inset-0 grid place-items-center text-lg font-bold text-p1">
                        ✕
                      </span>
                    )
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
