import Button from "../ui/Button";

export interface GameOverIntro {
  result: "win" | "loss" | "draw";
  subtitle: string;
  opponentName: string;
  eloAfter?: number;
  eloDelta?: number;
  isGuest?: boolean;
  savedGameId?: string;
}

export interface GameOverPrimaryAction {
  label: string;
  onClick: () => void;
}

interface GameOverOverlayProps {
  intro: GameOverIntro;
  onDismiss?: () => void;
  primaryAction?: GameOverPrimaryAction;
  secondaryAction?: GameOverPrimaryAction;
}

const RESULT_META = {
  win: {
    label: "Victoire",
    title: "Victoire !",
    border: "border-gold/50",
    glow: "shadow-[0_0_48px_rgba(255,215,0,0.25)]",
    badge: "bg-gold/15 text-gold",
    bar: "bg-gold",
    flare: "bg-gold/20",
  },
  loss: {
    label: "Défaite",
    title: "Défaite",
    border: "border-p1/45",
    glow: "shadow-[0_0_48px_rgba(255,71,87,0.22)]",
    badge: "bg-p1/15 text-p1",
    bar: "bg-p1",
    flare: "bg-p1/15",
  },
  draw: {
    label: "Match nul",
    title: "Match nul",
    border: "border-white/25",
    glow: "shadow-[0_0_48px_rgba(255,255,255,0.12)]",
    badge: "bg-white/10 text-white/80",
    bar: "bg-white/60",
    flare: "bg-white/10",
  },
} as const;

export default function GameOverOverlay({ intro, onDismiss, primaryAction, secondaryAction }: GameOverOverlayProps) {
  const meta = RESULT_META[intro.result];
  const delta = intro.eloDelta;
  const hasElo = !intro.isGuest && delta != null && intro.eloAfter != null;
  const deltaSign = delta != null && delta > 0 ? "+" : "";

  return (
    <div
      className="absolute inset-0 z-20 flex items-center justify-center p-4"
      role="status"
      aria-live="polite"
      aria-label={`${meta.title} contre ${intro.opponentName}`}
    >
      <div className="absolute inset-0 rounded-2xl bg-night/80 backdrop-blur-sm" />

      <div
        className={`game-overlay-popup relative w-full max-w-md animate-[matchFoundIn_0.45s_ease-out] overflow-hidden rounded-2xl border bg-gradient-to-b from-midnight to-deep px-6 py-8 text-center ${meta.border} ${meta.glow}`}
      >
        {onDismiss ? (
          <button
            type="button"
            onClick={onDismiss}
            className="absolute right-3 top-3 flex h-8 w-8 items-center justify-center rounded-lg text-white/50 transition hover:bg-white/10 hover:text-white"
            aria-label="Fermer"
          >
            <span className="text-xl leading-none" aria-hidden="true">
              ×
            </span>
          </button>
        ) : null}
        <div
          className={`pointer-events-none absolute -top-16 left-1/2 h-32 w-32 -translate-x-1/2 rounded-full blur-3xl ${meta.flare}`}
        />

        <p className={`text-xs font-bold uppercase tracking-[0.2em] ${meta.badge} inline-block rounded-full px-3 py-1`}>
          {meta.label}
        </p>

        <h2 className="mt-4 text-3xl font-black text-white sm:text-4xl">{meta.title}</h2>

        {intro.subtitle ? (
          <p className="mt-2 text-sm text-white/60">{intro.subtitle}</p>
        ) : null}

        <p className="mt-4 text-sm text-white/45">
          vs <span className="font-semibold text-white/75">{intro.opponentName}</span>
        </p>

        {hasElo ? (
          <div className="mt-6 rounded-xl border border-white/10 bg-black/20 px-4 py-5">
            <p
              className={`text-4xl font-black tabular-nums ${delta! >= 0 ? "text-gold" : "text-p1"}`}
            >
              {deltaSign}
              {delta}
            </p>
            <p className="mt-1 text-xs font-bold uppercase tracking-wider text-white/40">Elo</p>
            <p className="mt-3 text-lg font-semibold text-accent tabular-nums">
              {intro.eloAfter} Elo
            </p>
          </div>
        ) : intro.isGuest ? (
          <p className="mt-6 text-sm text-white/50">Elo non enregistré (mode invité)</p>
        ) : null}

        {primaryAction || secondaryAction ? (
          <div className="mt-6 flex flex-col gap-2">
            {primaryAction ? (
              <Button
                type="button"
                className="w-full"
                onClick={() => {
                  primaryAction.onClick();
                }}
              >
                {primaryAction.label}
              </Button>
            ) : null}
            {secondaryAction ? (
              <Button
                type="button"
                variant="secondary"
                className="w-full"
                onClick={() => {
                  secondaryAction.onClick();
                }}
              >
                {secondaryAction.label}
              </Button>
            ) : null}
          </div>
        ) : null}

        <div className="game-over-progress mt-6 h-1 overflow-hidden rounded-full bg-white/10">
          <div className={`h-full rounded-full ${meta.bar}`} />
        </div>
      </div>
    </div>
  );
}
