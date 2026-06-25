import { Link } from "react-router-dom";
import type { SavedGameSummary } from "../../lib/accountApi";

function resultLabel(result: string): string {
  if (result === "win") return "Victoire";
  if (result === "loss") return "Défaite";
  return "Nul";
}

function resultClass(result: string): string {
  if (result === "win") return "text-exact";
  if (result === "loss") return "text-p1";
  return "text-white/60";
}

export default function GameHistoryList({
  games,
  emptyMessage,
  linkToReview = false,
}: {
  games: SavedGameSummary[];
  emptyMessage?: string;
  linkToReview?: boolean;
}) {
  if (!games.length) {
    return <p className="text-sm text-white/60">{emptyMessage ?? "Aucune partie enregistrée."}</p>;
  }
  return (
    <ul className="divide-y divide-white/10">
      {games.map((g) => (
        <li key={g.id} className="flex items-center justify-between gap-3 py-3 first:pt-0">
          <div className="min-w-0 flex-1">
            {linkToReview ? (
              <Link
                to={`/analyze/${g.id}`}
                className={`block font-semibold hover:underline ${resultClass(g.result)}`}
              >
                {resultLabel(g.result)}
              </Link>
            ) : (
              <p className={`font-semibold ${resultClass(g.result)}`}>{resultLabel(g.result)}</p>
            )}
            <p className="text-xs text-white/50">
              {g.game_mode === "online"
                ? `vs ${g.opponent_name ?? "joueur"} · ${g.move_count} coups`
                : `Niveau ${g.bot_level ?? "?"} · ${g.move_count} coups`}
              {g.finished_at && ` · ${new Date(g.finished_at).toLocaleDateString("fr-FR")}`}
            </p>
          </div>
          <div className="text-right text-sm">
            {typeof g.elo_delta === "number" && (
              <span className={g.elo_delta >= 0 ? "text-exact" : "text-p1"}>
                {g.elo_delta >= 0 ? "+" : ""}
                {g.elo_delta} Elo
              </span>
            )}
            {g.elo_after != null && (
              <p className="text-xs text-white/40">{g.elo_after} Elo</p>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
