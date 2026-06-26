import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import Board from "../components/game/Board";
import Card from "../components/ui/Card";
import ProgressBar from "../components/ui/ProgressBar";
import EvalGraph from "../components/review/EvalGraph";
import MoveNavigator from "../components/review/MoveNavigator";
import MoveHistoryList from "../components/review/MoveHistoryList";
import {
  fetchGameReviewStream,
  type GameReview,
  type ReviewMove,
  type SavedGameDetail,
} from "../lib/accountApi";
import { boardAt } from "../lib/boardReplay";
import { classificationColor, classificationLabel } from "../lib/reviewLabels";

function resultLabel(result: string): string {
  if (result === "win") return "Victoire";
  if (result === "loss") return "Défaite";
  return "Nul";
}

export default function GameReviewPage() {
  const { gameId } = useParams<{ gameId: string }>();
  const [moveIndex, setMoveIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [game, setGame] = useState<SavedGameDetail | null>(null);
  const [review, setReview] = useState<GameReview | null>(null);
  const [progress, setProgress] = useState({ current: 0, total: 0 });

  useEffect(() => {
    if (!gameId) return;

    let cancelled = false;
    setLoading(true);
    setError(null);
    setGame(null);
    setReview(null);
    setProgress({ current: 0, total: 0 });
    setMoveIndex(0);

    fetchGameReviewStream(gameId, {
      onGame: (g) => {
        if (!cancelled) setGame(g);
      },
      onProgress: (current, total) => {
        if (!cancelled) setProgress({ current, total });
      },
    })
      .then((data) => {
        if (cancelled) return;
        setGame(data.game);
        setReview(data.review);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Erreur inconnue");
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [gameId]);

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

  if (loading) {
    const hasProgress = progress.total > 0;
    const progressLabel = hasProgress
      ? `Analyse du coup ${progress.current} / ${progress.total}…`
      : "Préparation de l'analyse…";

    return (
      <div className="mx-auto max-w-lg space-y-6 py-8">
        <Link to="/analyze" className="text-sm text-white/50 hover:text-accent">
          ← Historique
        </Link>
        <h1 className="text-2xl font-black text-accent">Revue de partie</h1>
        {game ? (
          <p className="text-sm text-white/60">
            {game.game_mode === "online"
              ? `vs ${game.opponent_name ?? "joueur"} · ${resultLabel(game.result)}`
              : `Niveau ${game.bot_level ?? "?"} · ${resultLabel(game.result)}`}
          </p>
        ) : null}
        <Card>
          <ProgressBar
            value={hasProgress ? progress.current : 0}
            max={hasProgress ? progress.total : 100}
            label={progressLabel}
            indeterminate={!hasProgress}
          />
          <p className="mt-3 text-xs text-white/45">
            Chaque coup est évalué (tablebase ou MCTS). Les parties longues peuvent prendre
            une minute.
          </p>
        </Card>
      </div>
    );
  }

  if (error || !review || !game) {
    return (
      <div className="space-y-4">
        <p className="text-p1">Impossible de charger la revue de partie.</p>
        {error ? <p className="text-sm text-white/50">{error}</p> : null}
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
              ? `vs ${game.opponent_name ?? "joueur"}${game.opponent_elo != null ? ` (${game.opponent_elo} Elo)` : ""} · ${resultLabel(game.result)}`
              : `Niveau ${game.bot_level ?? "?"} · ${resultLabel(game.result)}`}
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
            muteEmpty
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
            moves={moves.map((m: ReviewMove) => ({
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
        </Card>
      </div>
    </div>
  );
}
