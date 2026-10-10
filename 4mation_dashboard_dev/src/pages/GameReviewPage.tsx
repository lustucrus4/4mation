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
import {
  classificationColor,
  classificationLabel,
  natureColor,
  natureLabel,
  phaseLabel,
} from "../lib/reviewLabels";

function resultLabel(result: string): string {
  if (result === "win") return "Victoire";
  if (result === "loss") return "Défaite";
  return "Nul";
}

function fmtPct(value: number | null | undefined): string {
  return value == null ? "—" : `${value}%`;
}

const REVIEW_PHASES = ["opening", "middlegame", "endgame"] as const;

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
        <Link to="/analyze" className="text-sm text-white/60 hover:text-accent">
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
          <p className="mt-3 text-xs text-white/60">
            Chaque coup est évalué par la tablebase (valeur prouvée) ou par le moteur
            d'analyse (estimation). Les parties longues peuvent prendre une minute.
          </p>
        </Card>
      </div>
    );
  }

  if (error || !review || !game) {
    return (
      <div className="space-y-4">
        <p className="text-p1">Impossible de charger la revue de partie.</p>
        {error ? <p className="text-sm text-white/60">{error}</p> : null}
        <Link to="/analyze" className="text-accent hover:underline">
          ← Retour à l'historique
        </Link>
      </div>
    );
  }

  const maxMove = moves.length;
  const abp = review.accuracy_by_phase;
  const summary = review.summary;
  const keyMoments = review.key_moments ?? [];
  const provenStats = review.proven_stats;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link to="/analyze" className="inline-block py-2 text-sm text-white/60 hover:text-accent">
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
        <div className="flex gap-3">
          {review.human_accuracy != null && (
            <div className="rounded-xl border border-accent/30 bg-accent/10 px-4 py-2 text-center">
              <p className="text-xs uppercase tracking-wide text-white/60">Précision (Vous)</p>
              <p className="text-2xl font-black text-accent">{review.human_accuracy}%</p>
            </div>
          )}
          {review.bot_accuracy != null && (
            <div className="rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-center">
              <p className="text-xs uppercase tracking-wide text-white/60">Précision (Coach)</p>
              <p className="text-2xl font-black text-white/80">{review.bot_accuracy}%</p>
            </div>
          )}
        </div>
      </header>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-[minmax(0,1fr)_280px] lg:grid-cols-[minmax(0,1fr)_340px]">
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
              <p className="flex flex-wrap items-center gap-2 text-sm">
                <span>
                  Coup #{currentMove.index} —{" "}
                  <span style={{ color: classificationColor(currentMove.classification) }}>
                    {classificationLabel(currentMove.classification)}
                  </span>
                </span>
                {currentMove.nature && (
                  <span
                    className="rounded border px-1.5 py-0.5 text-[11px] uppercase tracking-wide"
                    style={{
                      color: natureColor(currentMove.nature),
                      borderColor: `${natureColor(currentMove.nature)}66`,
                    }}
                  >
                    {currentMove.nature_label ?? natureLabel(currentMove.nature)}
                  </span>
                )}
                {currentMove.is_human && currentMove.accuracy != null && (
                  <span className="text-white/60">· {currentMove.accuracy}% précision</span>
                )}
              </p>
              {currentMove.verdict && (
                <p className="mt-1 text-sm" style={{ color: natureColor(currentMove.nature ?? "unknown") }}>
                  {currentMove.verdict}
                </p>
              )}
              <p className="mt-1 text-xs text-white/60">
                {currentMove.phase ? `${phaseLabel(currentMove.phase)} · ` : ""}
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

        <Card className="max-h-72 overflow-y-auto md:max-h-[70vh]">
          <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-white/60">
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

      {(abp || summary) && (
        <section className="grid gap-4 md:grid-cols-2">
          {abp && (
            <Card>
              <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-white/60">
                Précision par phase
              </h2>
              <div className="space-y-1 text-sm">
                <div className="grid grid-cols-[1fr_4rem_4rem] gap-3 text-xs text-white/60">
                  <span>Phase</span>
                  <span className="text-right">Vous</span>
                  <span className="text-right">Coach</span>
                </div>
                {REVIEW_PHASES.map((p) => (
                  <div key={p} className="grid grid-cols-[1fr_4rem_4rem] gap-3">
                    <span className="text-white/60">{phaseLabel(p)}</span>
                    <span className="text-right text-accent">{fmtPct(abp.human[p])}</span>
                    <span className="text-right text-white/70">{fmtPct(abp.bot[p])}</span>
                  </div>
                ))}
              </div>
              {provenStats && (
                <p className="mt-3 border-t border-white/10 pt-3 text-xs text-white/60">
                  {provenStats.proven_moves} coup(s) prouvé(s) ·{" "}
                  {provenStats.estimated_moves} estimé(s)
                  {provenStats.proven_errors > 0
                    ? ` · ${provenStats.proven_errors} faute(s) prouvée(s)`
                    : ""}
                  {provenStats.missed_forced_wins > 0
                    ? ` · ${provenStats.missed_forced_wins} mat(s) forcé(s) manqué(s)`
                    : ""}
                </p>
              )}
            </Card>
          )}
          {summary && (
            <Card>
              <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-white/60">
                Résumé
              </h2>
              <p className="text-sm leading-relaxed text-accent">{summary.human.text}</p>
              <p className="mt-2 text-sm leading-relaxed text-white/65">{summary.bot.text}</p>
            </Card>
          )}
        </section>
      )}

      {keyMoments.length > 0 && (
        <Card>
          <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-white/60">
            Moments clés
          </h2>
          <ol className="space-y-2">
            {keyMoments.map((km) => (
              <li key={km.index}>
                <button
                  type="button"
                  onClick={() => setMoveIndex(km.index)}
                  className={[
                    "flex w-full items-start gap-2 rounded-lg border border-white/10 px-3 py-2 text-left transition-colors",
                    moveIndex === km.index ? "bg-accent/15" : "hover:bg-white/5",
                  ].join(" ")}
                >
                  <span
                    className="mt-1.5 h-2 w-2 shrink-0 rounded-full"
                    style={{ background: classificationColor(km.classification) }}
                  />
                  <span className="text-sm text-white/75">
                    <span
                      className="mr-2 text-[11px] uppercase tracking-wide"
                      style={{ color: natureColor(km.nature) }}
                    >
                      {natureLabel(km.nature)}
                    </span>
                    {km.description}
                  </span>
                </button>
              </li>
            ))}
          </ol>
        </Card>
      )}
    </div>
  );
}
