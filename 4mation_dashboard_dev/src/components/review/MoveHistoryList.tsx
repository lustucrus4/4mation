import type { MoveClassification } from "../../lib/accountApi";
import { classificationColor } from "../../lib/reviewLabels";

export interface HistoryMoveItem {
  index: number;
  player: number;
  row: number;
  col: number;
  classification: MoveClassification;
  isHuman: boolean;
  /** Précision affichée (coups humains) ou taux joué en % (coach). */
  displayPercent: number | null;
}

interface MoveHistoryListProps {
  moves: HistoryMoveItem[];
  moveIndex: number;
  humanColor?: number;
  onSelectMove: (index: number) => void;
}

export default function MoveHistoryList({
  moves,
  moveIndex,
  humanColor = 1,
  onSelectMove,
}: MoveHistoryListProps) {
  return (
    <ol className="space-y-1 text-sm">
      {moves.map((m, i) => (
        <li key={m.index}>
          <button
            type="button"
            onClick={() => onSelectMove(i + 1)}
            className={[
              "flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left transition-colors",
              moveIndex === i + 1 ? "bg-accent/15" : "hover:bg-white/5",
            ].join(" ")}
          >
            <span
              className="h-2 w-2 shrink-0 rounded-full"
              style={{ background: classificationColor(m.classification) }}
            />
            <span className="text-white/40">#{m.index}</span>
            <span className={m.player === 1 ? "text-p1" : "text-p2"}>
              {m.player === humanColor ? "Vous" : "Coach"}
            </span>
            <span className="text-white/70">
              ({m.row + 1},{m.col + 1})
            </span>
            {m.displayPercent != null && (
              <span className="ml-auto text-xs text-white/40">{m.displayPercent}%</span>
            )}
          </button>
        </li>
      ))}
    </ol>
  );
}
