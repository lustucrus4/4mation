import {
  formatBarWinRate,
  type PositionStatus,
} from "../../lib/winRateDisplay";

interface WinBarProps {
  /** Probabilité de victoire du joueur 1 (0..1). */
  winRateP1: number;
  label?: string;
  source?: string;
  exact?: boolean;
  positionStatus?: PositionStatus;
}

export default function WinBar({
  winRateP1,
  label,
  source,
  exact = false,
  positionStatus,
}: WinBarProps) {
  const p1 = Math.max(0, Math.min(1, Number.isFinite(winRateP1) ? winRateP1 : 0.5));
  const displayPct = formatBarWinRate(p1, exact, positionStatus);
  const barPct =
    positionStatus === "proven_losing"
      ? 0
      : positionStatus === "proven_winning"
        ? 100
        : Math.round(p1 * 100);

  return (
    <section className="mx-auto mt-4 w-full max-w-[560px]" aria-label="Probabilité de victoire">
      <div className="mb-1.5 flex items-baseline justify-between text-sm">
        <span className="font-bold">{label ?? "Probabilité de victoire"}</span>
        <span className="text-xs text-white/60">{source ?? ""}</span>
      </div>
      <div
        className="relative h-6 overflow-hidden rounded-full border"
        style={{
          background: "linear-gradient(135deg, #3742fa, #2f3542)",
          borderColor: exact ? "var(--color-exact)" : "rgba(255,255,255,0.2)",
          boxShadow: exact ? "0 0 14px rgba(123, 237, 159, 0.55)" : "none",
        }}
      >
        <div
          className="h-full transition-[width] duration-500 ease-out"
          style={{
            width: `${barPct}%`,
            background: "linear-gradient(135deg, #ff4757, #c44569)",
          }}
        />
        <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-xs font-bold drop-shadow-[0_0_4px_rgba(0,0,0,0.85)]">
          {displayPct}
        </span>
        <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-xs font-bold drop-shadow-[0_0_4px_rgba(0,0,0,0.85)]">
          {positionStatus === "proven_losing"
            ? "100%"
            : positionStatus === "proven_winning"
              ? "0%"
              : `${100 - barPct}%`}
        </span>
      </div>
      <div className="mt-1 flex justify-between text-[0.72rem] text-white/60">
        <span className="text-p1">Vous</span>
        <span className="text-p2">Coach</span>
      </div>
    </section>
  );
}
