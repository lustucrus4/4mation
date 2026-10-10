import { useEffect, useMemo, useRef } from "react";
import { Link } from "react-router-dom";
import Board, { emptyBoard } from "../components/game/Board";
import WinBar from "../components/game/WinBar";
import GameOverOverlay from "../components/game/GameOverOverlay";
import RuleDiagram from "../components/learn/RuleDiagram";
import { trainerLegendDiagram } from "../components/learn/diagrams";
import EvalGraph from "../components/review/EvalGraph";
import MoveHistoryList from "../components/review/MoveHistoryList";
import MoveNavigator from "../components/review/MoveNavigator";
import Card from "../components/ui/Card";
import Button from "../components/ui/Button";
import { useGame } from "../hooks/useGame";
import { useLearningReview } from "../hooks/useLearningReview";
import { boardAt } from "../lib/boardReplay";
import { boardInteractionProps } from "../lib/boardInteraction";
import { classificationColor, classificationLabel } from "../lib/reviewLabels";
import { positionStatusHint } from "../lib/winRateDisplay";

/** Partie guidée en mode apprentissage (taux par case + barre W/L + relecture). */
export default function TrainerPage() {
  const game = useGame();
  const initRef = useRef(false);
  const { state, analysis, busy, mode } = game;

  const review = useLearningReview(state, analysis, busy);

  useEffect(() => {
    if (initRef.current) return;
    initRef.current = true;
    if (mode !== "learning") {
      void game.setMode("learning");
    }
  }, [mode, game]);

  const history = state?.history ?? [];
  const liveCount = review.liveCount;

  const { board, lastMove } = useMemo(() => {
    if (!state) return { board: emptyBoard(), lastMove: null };
    if (review.isAtLive) {
      return { board: state.board, lastMove: state.last_move };
    }
    return boardAt(history, review.viewMoveIndex);
  }, [state, review.isAtLive, review.viewMoveIndex, history]);

  const displayAnalysis = review.viewedAnalysis ?? analysis;

  const boardUi = boardInteractionProps(state ?? undefined, { active: review.isAtLive });

  const statusHint = positionStatusHint(displayAnalysis?.positionStatus);
  const coachNote =
    displayAnalysis?.afterProvenBlunder &&
    displayAnalysis.positionStatus !== "proven_losing"
      ? "Après un coup perdant prouvé, les estimations suivantes sont plafonnées (<5 %)."
      : null;

  const handleCellClick = async ({ row, col }: { row: number; col: number }) => {
    if (!review.isAtLive) {
      await game.undoToMove(review.viewMoveIndex);
    }
    await game.playHuman(row, col);
  };

  const handleNewGame = () => {
    review.reset();
    void game.newGame("learning");
  };

  const viewingPast = !review.isAtLive;

  const actionButtons = (
    <div className="flex flex-wrap justify-center gap-2 md:justify-start">
      <Button onClick={handleNewGame} disabled={busy}>
        Nouvelle partie
      </Button>
      <Button variant="ghost" onClick={() => void game.undo()} disabled={!game.canUndo}>
        Annuler
      </Button>
    </div>
  );

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3 md:hidden">
        <div>
          <Link to="/learn" className="inline-block py-2 text-sm text-white/60 hover:text-accent">
            ← Apprendre
          </Link>
          <h1 className="mt-1 text-2xl font-black text-accent">Entraîneur</h1>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-[minmax(0,1fr)_280px] lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="relative space-y-4">
          <Board
            board={board}
            playable={boardUi.playable}
            dimInvalid={boardUi.dimInvalid}
            muteEmpty={boardUi.muteEmpty}
            lastMove={lastMove}
            bestMove={
              displayAnalysis && (!state?.is_terminal || viewingPast)
                ? displayAnalysis.bestMove
                : null
            }
            rates={displayAnalysis?.rates}
            ratesExact={displayAnalysis?.exact}
            ratesProvenLoss={displayAnalysis?.ratesProvenLoss}
            thinking={busy && review.isAtLive}
            onCellClick={({ row, col }) => void handleCellClick({ row, col })}
          />

          {game.gameOverOverlay ? (
            <GameOverOverlay
              intro={game.gameOverOverlay}
              onDismiss={game.dismissGameOverOverlay}
              primaryAction={{
                label: "Nouvelle partie",
                onClick: () => {
                  game.dismissGameOverOverlay();
                  handleNewGame();
                },
              }}
            />
          ) : null}

          <p className="text-center text-lg font-semibold text-accent" aria-live="polite">
            {game.gameOverOverlay
              ? null
              : viewingPast
                ? "Relecture de la partie"
                : game.message}
          </p>
          {game.error && (
            <p className="text-center text-sm text-p1">{game.error}</p>
          )}

          <MoveNavigator
            moveIndex={review.viewMoveIndex}
            maxMove={liveCount}
            onChange={review.goToMove}
            disabled={busy || liveCount === 0}
            hideStart
          />

          <div className="md:hidden">{actionButtons}</div>

          {viewingPast && (
            <p className="text-center text-sm text-white/60">
              Relecture — ▶ ou ⏭ pour reprendre la partie sans la modifier. Jouez sur le plateau
              pour changer la ligne à partir de ce coup.
            </p>
          )}

          {review.currentStored && (
            <Card className="!py-3">
              <p className="text-sm">
                Coup #{review.currentStored.index} —{" "}
                <span
                  style={{
                    color: classificationColor(review.currentStored.classification),
                  }}
                >
                  {classificationLabel(review.currentStored.classification)}
                </span>
                {review.currentStored.isHuman &&
                  review.currentStored.displayPercent != null && (
                    <span className="text-white/60">
                      {" "}
                      · {review.currentStored.displayPercent}% précision
                    </span>
                  )}
              </p>
              <p className="mt-1 text-xs text-white/60">
                Joué : {Math.round(review.currentStored.winRatePlayed * 100)} % · Meilleur :{" "}
                {Math.round(review.currentStored.winRateBest * 100)} %
              </p>
            </Card>
          )}

          <WinBar
            winRateP1={displayAnalysis?.winRateP1 ?? 0.5}
            label="Probabilité de victoire"
            source={displayAnalysis?.label ?? ""}
            exact={displayAnalysis?.exact ?? false}
            positionStatus={displayAnalysis?.positionStatus}
          />

          {review.graph.length >= 2 && (
            <EvalGraph
              graph={review.graph}
              currentMove={review.viewMoveIndex}
              onSelectMove={review.goToMove}
            />
          )}

          {statusHint && !game.gameOverOverlay && review.isAtLive && (
            <p className="mx-auto max-w-[560px] rounded-lg border border-exact/40 bg-exact/10 px-3 py-2 text-center text-sm text-exact">
              {statusHint}
            </p>
          )}
          {coachNote && !statusHint && !game.gameOverOverlay && review.isAtLive && (
            <p className="mx-auto max-w-[560px] rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-center text-sm text-white/70">
              {coachNote}
            </p>
          )}

        </div>

        <aside className="space-y-4">
          <Link to="/learn" className="hidden py-2 text-sm text-white/60 hover:text-accent md:inline-block">
            ← Apprendre
          </Link>
          <h1 className="hidden text-2xl font-black text-accent md:block">Entraîneur</h1>

          <Card>
            <p className="text-sm text-white/70">
              Jouez contre le <strong className="text-white">coach</strong>. ◀ ▶ ⏭ pour parcourir
              les coups sans modifier la partie ; jouez sur le plateau pour corriger une ligne.
            </p>
            <ul className="mt-2 space-y-1 text-xs text-white/60">
              <li>
                <span className="text-exact">Vert</span> — analyse exacte
              </li>
              <li>
                <span className="text-accent">Turquoise</span> — estimation du moteur
              </li>
              <li>★ — meilleur coup suggéré</li>
            </ul>
            <div className="mt-3 flex justify-center">
              <RuleDiagram {...trainerLegendDiagram} compact />
            </div>
          </Card>

          <Card className="max-h-[40vh] overflow-y-auto md:max-h-[50vh]">
            <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-white/60">
              Coups
            </h2>
            {review.historyMoves.length === 0 ? (
              <p className="text-sm text-white/60">Aucun coup joué.</p>
            ) : (
              <MoveHistoryList
                moves={review.historyMoves}
                moveIndex={review.viewMoveIndex}
                humanColor={1}
                onSelectMove={review.goToMove}
              />
            )}
          </Card>

          <div className="hidden md:block">{actionButtons}</div>
        </aside>
      </div>
    </div>
  );
}
