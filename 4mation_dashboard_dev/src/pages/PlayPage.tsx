import { useEffect, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import Board, { emptyBoard } from "../components/game/Board";
import GameOverOverlay from "../components/game/GameOverOverlay";
import Card from "../components/ui/Card";
import Button from "../components/ui/Button";
import Select from "../components/ui/Select";
import { useGame } from "../hooks/useGame";
import { useAccount } from "../hooks/useAccount";
import { boardInteractionProps } from "../lib/boardInteraction";

export default function PlayPage() {
  const game = useGame();
  const navigate = useNavigate();
  const { authenticated, profile } = useAccount();
  const { state, busy, mode } = game;
  const initRef = useRef(false);

  useEffect(() => {
    if (initRef.current) return;
    initRef.current = true;
    if (mode !== "standard") {
      void game.setMode("standard");
    }
  }, [mode, game]);

  const board = state?.board ?? emptyBoard();
  const boardUi = boardInteractionProps(state ?? undefined);

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_340px]">
      <div className="relative">
        <Board
          board={board}
          playable={boardUi.playable}
          dimInvalid={boardUi.dimInvalid}
          muteEmpty={boardUi.muteEmpty}
          lastMove={state?.last_move ?? null}
          thinking={busy}
          onCellClick={({ row, col }) => game.playHuman(row, col)}
        />

        {game.gameOverOverlay ? (
          <GameOverOverlay
            intro={game.gameOverOverlay}
            onDismiss={game.dismissGameOverOverlay}
            primaryAction={{
              label: "Nouvelle partie",
              onClick: () => {
                game.dismissGameOverOverlay();
                void game.newGame("standard");
              },
            }}
            secondaryAction={
              game.gameOverOverlay.savedGameId
                ? {
                    label: "Analyser la partie",
                    onClick: () => {
                      navigate(`/analyze/${game.gameOverOverlay!.savedGameId}`);
                    },
                  }
                : undefined
            }
          />
        ) : null}

        <p className="mt-4 text-center text-lg font-semibold text-accent">
          {game.gameOverOverlay ? null : game.message}
        </p>
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
          <label className="mb-1.5 block text-sm font-bold uppercase tracking-wide text-white/50" htmlFor="bot">
            Adversaire IA
          </label>
          <Select
            id="bot"
            value={game.selectedBotId}
            disabled={busy}
            onChange={game.setSelectedBotId}
            aria-label="Adversaire IA"
            options={game.bots.map((b) => ({
              value: b.id,
              label: b.name,
              title: b.description,
            }))}
          />
          <p className="mt-3 text-xs text-white/45">
            Mode classique sans aide. Pour vous entraîner avec les % et le coach, utilisez{" "}
            <Link to="/learn/trainer" className="text-accent hover:underline">
              l&apos;entraîneur
            </Link>
            .
          </p>
        </Card>

        <div className="flex flex-wrap gap-2">
          <Button onClick={() => game.newGame("standard")} disabled={busy}>
            Nouvelle partie
          </Button>
          <Button variant="ghost" onClick={() => game.undo()} disabled={!game.canUndo}>
            Annuler
          </Button>
          {state?.current_player === 2 && !state.is_terminal && (
            <Button variant="secondary" onClick={() => game.playAi()} disabled={busy}>
              Coup de l&apos;IA
            </Button>
          )}
        </div>

        <Timeline history={state?.history ?? []} />
      </aside>
    </div>
  );
}

function Timeline({
  history,
}: {
  history: { index: number; player: number; row: number; col: number }[];
}) {
  if (!history.length) return null;
  return (
    <Card className="max-h-48 overflow-y-auto !p-3">
      <h2 className="mb-2 text-sm font-bold uppercase tracking-wide text-white/50">Historique</h2>
      <ol className="space-y-1 text-sm text-white/70">
        {history.map((e) => {
          const who = e.player === 1 ? "Vous" : "IA";
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
