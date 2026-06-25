import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import Board, { emptyBoard, type BoardMatrix, type Move } from "../components/game/Board";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import EvalGraph from "../components/review/EvalGraph";
import { fetchGameReview, type ReviewMove } from "../lib/accountApi";
import { classificationColor, classificationLabel } from "../lib/reviewLabels";

function boardAt(history: ReviewMove[], upTo: number): {
  board: BoardMatrix;
  lastMove: Move | null;
} {
  const board = emptyBoard();
  let last: Move | null = null;
  for (let i = 0; i < upTo && i < history.length; i++) {
    const m = history[i];
    board[m.row][m.col] = m.player;
    last = { row: m.row, col: m.col };
  }
  return { board, lastMove: last };
}

export default function GameReviewPage() {
  const { gameId } = useParams<{ gameId: string }>();
  const [moveIndex, setMoveIndex] = useState(0);

  const query = useQuery({
    queryKey: ["game-review", gameId],
    queryFn: () => fetchGameReview(gameId!),
    enabled: Boolean(gameId),
    staleTime: 60_000,
  });

  const review = query.data?.review;
  const game = query.data?.game;
  const moves = review?.moves ?? [];

  const { board, lastMove } = useMemo(
    () => boardAt(moves, moveIndex),
    [moves, moveIndex]
  );

  const currentMove = moveIndex > 0 ? moves[moveIndex - 1] : null;
  const bestHighlight =
    currentMove?.best_move && moveIndex > 0
      ? { row: currentMove.best_move[0], col: currentMove.best_move[1] }
      : null;

  if (query.isLoading) {
    return <p className="text-white/60">Analyse de la partie en cours…</p>;
  }

  if (query.isError || !review || !game) {
    return (
      <div className="space-y-4">
        <p className="text-p1">Impossible de charger la revue de partie.</p>
        <Link to="/analyze" className="text-accent hover:underline">
          ← Retour à l'historique
        </Link>
      </div>
    );
  }

  const maxMove = moves.length;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link to="/analyze" className="text-sm text-white/50 hover:text-accent">
            ← Historique
          </Link>
          <h1 className="mt-1 text-2xl font-black text-accent">Revue de partie</h1>
          <p className="text-sm text-white/60">
            Niveau {game.bot_level ?? "?"} · {game.result === "win" ? "Victoire" : game.result === "loss" ? "Défaite" : "Nul"}
            {game.finished_at &&
              ` · ${new Date(game.finished_at).toLocaleDateString("fr-FR")}`}
          </p>
        </div>
        {review.human_accuracy != null && (
          <div className="rounded-xl border border-accent/30 bg-accent/10 px-4 py-2 text-center">
            <p className="text-xs uppercase tracking-wide text-white/50">Précision</p>
            <p className="text-2xl font-black text-accent">{review.human_accuracy}%</p>
          </div>
        )}
      </header>

      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="space-y-4">
          <Board
            board={board}
            lastMove={lastMove}
            bestMove={bestHighlight}
            playable={[]}
          />

          <div className="flex flex-wrap items-center justify-center gap-2">
            <Button variant="ghost" onClick={() => setMoveIndex(0)} disabled={moveIndex === 0}>
              ⏮
            </Button>
            <Button
              variant="ghost"
              onClick={() => setMoveIndex((i) => Math.max(0, i - 1))}
              disabled={moveIndex === 0}
            >
              ◀
            </Button>
            <span className="min-w-[5rem] text-center text-sm text-white/70">
              {moveIndex} / {maxMove}
            </span>
            <Button
              variant="ghost"
              onClick={() => setMoveIndex((i) => Math.min(maxMove, i + 1))}
              disabled={moveIndex >= maxMove}
            >
              ▶
            </Button>
            <Button
              variant="ghost"
              onClick={() => setMoveIndex(maxMove)}
              disabled={moveIndex >= maxMove}
            >
              ⏭
            </Button>
          </div>

          {currentMove && (
            <Card className="!py-3">
              <p className="text-sm">
                Coup #{currentMove.index} —{" "}
                <span style={{ color: classificationColor(currentMove.classification) }}>
                  {classificationLabel(currentMove.classification)}
                </span>
                {currentMove.is_human && currentMove.accuracy != null && (
                  <span className="text-white/50"> · {currentMove.accuracy}% précision</span>
                )}
              </p>
              <p className="mt-1 text-xs text-white/45">
                Joué : {Math.round(currentMove.win_rate_played * 100)} % · Meilleur :{" "}
                {Math.round(currentMove.win_rate_best * 100)} %
                {currentMove.exact ? " · exact" : ""}
              </p>
            </Card>
          )}

          <EvalGraph
            graph={review.graph}
            currentMove={moveIndex}
            onSelectMove={setMoveIndex}
          />
        </div>

        <Card className="max-h-[70vh] overflow-y-auto">
          <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-white/50">
            Coups
          </h2>
          <ol className="space-y-1 text-sm">
            {moves.map((m, i) => (
              <li key={m.index}>
                <button
                  type="button"
                  onClick={() => setMoveIndex(i + 1)}
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
                    {m.player === review.human_color ? "Vous" : "IA"}
                  </span>
                  <span className="text-white/70">
                    ({m.row + 1},{m.col + 1})
                  </span>
                  {m.is_human && m.accuracy != null && (
                    <span className="ml-auto text-xs text-white/40">{m.accuracy}%</span>
                  )}
                </button>
              </li>
            ))}
          </ol>
        </Card>
      </div>
    </div>
  );
}
