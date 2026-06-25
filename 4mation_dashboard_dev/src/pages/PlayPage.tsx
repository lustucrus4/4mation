import Board, { emptyBoard } from "../components/game/Board";
import WinBar from "../components/game/WinBar";
import Card from "../components/ui/Card";
import Button from "../components/ui/Button";
import { useGame } from "../hooks/useGame";
import { useAccount } from "../hooks/useAccount";
import type { GameMode } from "../lib/gameApi";

export default function PlayPage() {
  const game = useGame();
  const { authenticated, profile } = useAccount();
  const { state, analysis, mode, busy } = game;

  const isLearning = mode === "learning";
  const board = state?.board ?? emptyBoard();
  const playable =
    state && !state.is_terminal && state.current_player === 1 ? state.valid_actions : [];
  const showRates = isLearning ? analysis?.rates : undefined;
  const showBest = isLearning && state && !state.is_terminal ? analysis?.bestMove ?? null : null;

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_340px]">
      <div>
        <Board
          board={board}
          playable={playable}
          lastMove={state?.last_move ?? null}
          bestMove={showBest}
          rates={showRates}
          ratesExact={analysis?.exact}
          thinking={busy}
          onCellClick={({ row, col }) => game.playHuman(row, col)}
        />

        {isLearning && (
          <WinBar
            winRateP1={analysis?.winRateP1 ?? 0.5}
            label="Probabilité de victoire"
            source={analysis?.label ?? ""}
            exact={analysis?.exact ?? false}
          />
        )}

        <p className="mt-4 text-center text-lg font-semibold text-accent">{game.message}</p>
        {game.error && (
          <p className="mt-2 text-center text-sm text-p1">{game.error}</p>
        )}
        {state && (
          <p className="mt-1 text-center text-xs text-white/50">
            Coup #{state.move_count} — Joueur actif : {state.current_player}
          </p>
        )}
      </div>

      <aside className="space-y-4">
        <div className="flex items-baseline justify-between gap-2">
          <h1 className="text-2xl font-black text-accent">Jouer</h1>
          {authenticated && profile?.rating && (
            <span className="rounded-full bg-accent/15 px-2.5 py-1 text-xs font-bold text-accent">
              {profile.rating.elo} Elo
            </span>
          )}
        </div>

        <Card>
          <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-white/50">Mode</h2>
          <div className="grid grid-cols-2 gap-2">
            {(
              [
                { id: "standard", label: "Classique" },
                { id: "learning", label: "Apprentissage" },
              ] as { id: GameMode; label: string }[]
            ).map((m) => (
              <button
                key={m.id}
                type="button"
                disabled={busy}
                onClick={() => mode !== m.id && game.setMode(m.id)}
                className={[
                  "rounded-lg px-3 py-2 text-sm font-semibold transition-colors disabled:opacity-50",
                  mode === m.id
                    ? "bg-accent text-deep"
                    : "border border-white/15 bg-white/5 text-white/80 hover:bg-white/10",
                ].join(" ")}
              >
                {m.label}
              </button>
            ))}
          </div>

          {mode === "standard" && (
            <div className="mt-4">
              <label className="mb-1.5 block text-sm font-semibold text-accent" htmlFor="bot">
                Adversaire IA
              </label>
              <select
                id="bot"
                value={game.selectedBotId}
                disabled={busy}
                onChange={(e) => game.setSelectedBotId(e.target.value)}
                className="w-full rounded-lg border-2 border-accent bg-black/25 px-3 py-2.5 text-sm text-white"
              >
                {game.bots.map((b) => (
                  <option key={b.id} value={b.id} title={b.description}>
                    {b.name}
                  </option>
                ))}
              </select>
            </div>
          )}
        </Card>

        <div className="flex flex-wrap gap-2">
          <Button onClick={() => game.newGame()} disabled={busy}>
            Nouvelle partie
          </Button>
          <Button variant="ghost" onClick={() => game.undo()} disabled={!game.canUndo}>
            Annuler
          </Button>
          {mode === "standard" && state?.current_player === 2 && !state.is_terminal && (
            <Button variant="secondary" onClick={() => game.playAi()} disabled={busy}>
              Coup de l'IA
            </Button>
          )}
        </div>

        <Timeline history={state?.history ?? []} mode={mode} />
      </aside>
    </div>
  );
}

function Timeline({
  history,
  mode,
}: {
  history: { index: number; player: number; row: number; col: number }[];
  mode: GameMode;
}) {
  if (!history.length) return null;
  return (
    <Card className="max-h-48 overflow-y-auto !p-3">
      <h2 className="mb-2 text-sm font-bold uppercase tracking-wide text-white/50">Historique</h2>
      <ol className="space-y-1 text-sm text-white/70">
        {history.map((e) => {
          const who = e.player === 1 ? "Vous" : mode === "learning" ? "Coach" : "IA";
          return (
            <li key={e.index}>
              <span className="text-white/40">#{e.index}</span> {who} : ({e.row + 1}, {e.col + 1})
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
