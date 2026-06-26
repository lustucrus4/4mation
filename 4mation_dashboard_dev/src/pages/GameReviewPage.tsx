import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import Board, { type Move } from "../components/game/Board";
import Card from "../components/ui/Card";
import EvalGraph from "../components/review/EvalGraph";
import MoveNavigator from "../components/review/MoveNavigator";
import MoveHistoryList from "../components/review/MoveHistoryList";
import { fetchGameReview, type ReviewMove } from "../lib/accountApi";
import { boardAt } from "../lib/boardReplay";
import { classificationColor, classificationLabel } from "../lib/reviewLabels";
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
            {game.game_mode === "online"
              ? `vs ${game.opponent_name ?? "joueur"}${game.opponent_elo != null ? ` (${game.opponent_elo} Elo)` : ""} · ${
                  game.result === "win" ? "Victoire" : game.result === "loss" ? "Défaite" : "Nul"
                }`
              : `Niveau ${game.bot_level ?? "?"} · ${
                  game.result === "win" ? "Victoire" : game.result === "loss" ? "Défaite" : "Nul"
                }`}
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

          <MoveNavigator
            moveIndex={moveIndex}
            maxMove={maxMove}
            onChange={setMoveIndex}
          />
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
          <MoveHistoryList
            moves={moves.map((m) => ({
              index: m.index,
              player: m.player,
              row: m.row,
              col: m.col,
              classification: m.classification,
              isHuman: m.is_human,
              displayPercent: m.is_human && m.accuracy != null ? m.accuracy : null,
            }))}
            moveIndex={moveIndex}
            humanColor={review.human_color}
            onSelectMove={(idx) => setMoveIndex(idx)}
          />
        </Card>      </div>
    </div>
  );
}
