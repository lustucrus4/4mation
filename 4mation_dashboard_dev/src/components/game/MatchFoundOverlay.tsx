export interface MatchIntro {
  youName: string;
  opponentName: string;
  opponentElo: number;
  yourColor: number;
}

interface MatchFoundOverlayProps {
  intro: MatchIntro;
}

export default function MatchFoundOverlay({ intro }: MatchFoundOverlayProps) {
  const youIsRed = intro.yourColor === 1;

  return (
    <div
      className="absolute inset-0 z-20 flex items-center justify-center p-4"
      role="status"
      aria-live="polite"
      aria-label={`Adversaire trouvé : ${intro.youName} contre ${intro.opponentName}`}
    >
      <div className="absolute inset-0 rounded-2xl bg-night/75 backdrop-blur-sm" />

      <div className="match-found-popup relative w-full max-w-md animate-[matchFoundIn_0.45s_ease-out] overflow-hidden rounded-2xl border border-accent/40 bg-gradient-to-b from-midnight to-deep px-6 py-8 text-center shadow-[0_0_48px_rgba(17,241,204,0.22)]">
        <div className="pointer-events-none absolute -top-16 left-1/2 h-32 w-32 -translate-x-1/2 rounded-full bg-accent/15 blur-3xl" />

        <p className="text-xs font-bold uppercase tracking-[0.2em] text-accent">
          Adversaire trouvé
        </p>

        <div className="mt-6 flex flex-wrap items-center justify-center gap-3 sm:gap-4">
          <div className="min-w-[7rem] flex-1 text-right">
            <p
              className={`truncate text-xl font-black sm:text-2xl ${youIsRed ? "text-p1" : "text-p2"}`}
            >
              {intro.youName}
            </p>
            <p className="mt-1 text-xs text-white/45">Vous</p>
          </div>

          <span className="rounded-lg bg-white/10 px-3 py-1.5 text-sm font-black tracking-widest text-accent">
            VS
          </span>

          <div className="min-w-[7rem] flex-1 text-left">
            <p
              className={`truncate text-xl font-black sm:text-2xl ${youIsRed ? "text-p2" : "text-p1"}`}
            >
              {intro.opponentName}
            </p>
            <p className="mt-1 text-xs text-white/45">{intro.opponentElo} Elo</p>
          </div>
        </div>

        <p className="mt-6 text-sm text-white/55">La partie commence dans un instant…</p>

        <div className="match-found-progress mt-4 h-1 overflow-hidden rounded-full bg-white/10">
          <div className="h-full rounded-full bg-accent" />
        </div>
      </div>
    </div>
  );
}
