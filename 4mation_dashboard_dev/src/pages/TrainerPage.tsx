import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import Board, { emptyBoard } from "../components/game/Board";
import WinBar from "../components/game/WinBar";
import Card from "../components/ui/Card";
import Button from "../components/ui/Button";
import { useGame } from "../hooks/useGame";

/** Partie guidée en mode apprentissage (taux par case + barre W/L). */
export default function TrainerPage() {
  const game = useGame();
  const initRef = useRef(false);
  const { state, analysis, busy, mode } = game;

  useEffect(() => {
    if (initRef.current) return;
    initRef.current = true;
    if (mode !== "learning") {
      void game.setMode("learning");
    }
  }, [mode, game]);

  const board = state?.board ?? emptyBoard();
  const playable =
    state && !state.is_terminal && state.current_player === 1 ? state.valid_actions : [];
  const showBest = state && !state.is_terminal ? analysis?.bestMove ?? null : null;

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_340px]">
      <div>
        <Board
          board={board}
          playable={playable}
          lastMove={state?.last_move ?? null}
          bestMove={showBest}
          rates={analysis?.rates}
          ratesExact={analysis?.exact}
          thinking={busy}
          onCellClick={({ row, col }) => game.playHuman(row, col)}
        />

        <WinBar
          winRateP1={analysis?.winRateP1 ?? 0.5}
          label="Probabilité de victoire"
          source={analysis?.label ?? ""}
          exact={analysis?.exact ?? false}
        />

        <p className="mt-4 text-center text-lg font-semibold text-accent">{game.message}</p>
        {game.error && (
          <p className="mt-2 text-center text-sm text-p1">{game.error}</p>
        )}
      </div>

      <aside className="space-y-4">
        <Link to="/learn" className="text-sm text-white/50 hover:text-accent">
          ← Apprendre
        </Link>
        <h1 className="text-2xl font-black text-accent">Entraîneur</h1>

        <Card>
          <p className="text-sm text-white/70">
            Jouez contre le coach avec les pourcentages affichés sur chaque case
            valide et le meilleur coup suggéré en pointillés dorés.
          </p>
        </Card>

        <div className="flex flex-wrap gap-2">
          <Button onClick={() => game.newGame("learning")} disabled={busy}>
            Nouvelle partie
          </Button>
          <Button variant="ghost" onClick={() => game.undo()} disabled={!game.canUndo}>
            Annuler
          </Button>
        </div>
      </aside>
    </div>
  );
}
