import type { GameReview } from "../../lib/accountApi";

interface EvalGraphProps {
  graph: GameReview["graph"];
  currentMove: number;
  onSelectMove: (index: number) => void;
}

export default function EvalGraph({ graph, currentMove, onSelectMove }: EvalGraphProps) {
  if (graph.length < 2) return null;

  const w = 100;
  const h = 48;
  const pad = 2;
  const maxIdx = Math.max(1, graph.length - 1);

  const points = graph.map((pt) => {
    const x = pad + ((pt.move_index / maxIdx) * (w - 2 * pad));
    const y = pad + (1 - pt.win_rate_p1) * (h - 2 * pad);
    return `${x},${y}`;
  });

  const cur = graph.find((g) => g.move_index === currentMove) ?? graph[graph.length - 1];
  const cx = pad + ((cur.move_index / maxIdx) * (w - 2 * pad));
  const cy = pad + (1 - cur.win_rate_p1) * (h - 2 * pad);

  return (
    <div className="rounded-xl border border-white/10 bg-black/20 p-3">
      <div className="mb-2 flex justify-between text-xs text-white/50">
        <span className="text-p1">Vous gagnez</span>
        <span>Probabilité de victoire</span>
        <span className="text-p2">IA gagne</span>
      </div>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        className="h-24 w-full cursor-pointer"
        role="img"
        aria-label="Courbe de probabilité de victoire"
        onClick={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const ratio = (e.clientX - rect.left) / rect.width;
          const idx = Math.round(ratio * maxIdx);
          onSelectMove(Math.max(0, Math.min(maxIdx, idx)));
        }}
      >
        <line x1={pad} y1={h / 2} x2={w - pad} y2={h / 2} stroke="rgba(255,255,255,0.15)" />
        <polyline
          fill="none"
          stroke="#11f1cc"
          strokeWidth="1.5"
          points={points.join(" ")}
        />
        <circle cx={cx} cy={cy} r="2.5" fill="#ffd700" stroke="#1a1a2e" strokeWidth="0.8" />
      </svg>
      <p className="mt-1 text-center text-xs text-white/45">
        Coup {currentMove} / {maxIdx} · {Math.round(cur.win_rate_p1 * 100)} % pour vous
      </p>
    </div>
  );
}
