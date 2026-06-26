import { useQuery } from "@tanstack/react-query";
import Card from "../components/ui/Card";
import Button from "../components/ui/Button";
import GameHistoryList from "../components/account/GameHistoryList";
import { useAccount } from "../hooks/useAccount";
import { fetchGames } from "../lib/accountApi";
import { parseApiErrorMessage } from "../lib/apiErrors";
import { useEffect } from "react";

export default function AnalyzePage() {
  const { authenticated, authLoading, refresh } = useAccount();

  const gamesQuery = useQuery({
    queryKey: ["games", "all"],
    queryFn: () => fetchGames(50, 0),
    enabled: authenticated,
    staleTime: 30_000,
    retry: 2,
  });

  useEffect(() => {
    const handler = () => {
      refresh();
      gamesQuery.refetch();
    };
    window.addEventListener("4mation:game-saved", handler);
    return () => window.removeEventListener("4mation:game-saved", handler);
  }, [refresh, gamesQuery]);

  const historyError = gamesQuery.isError
    ? parseApiErrorMessage(gamesQuery.error, "Impossible de charger l'historique.")
    : null;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-black text-accent">Analyser</h1>
        <p className="mt-1 text-sm text-white/60">
          Historique de vos parties enregistrées (IA et en ligne) — cliquez sur une partie pour la revue
          détaillée (précision, classification des coups, relecture).
        </p>
        <p className="mt-2 text-sm">
          <a href="/analyze/rl" className="font-semibold text-accent hover:underline">
            Entraînement RL Rust →
          </a>
        </p>
      </header>

      {!authLoading && !authenticated && (
        <Card>
          <p className="text-white/70">
            Connectez-vous pour retrouver l&apos;historique de vos parties contre les bots et en ligne.
          </p>
        </Card>
      )}

      {authenticated && (
        <Card>
          <h2 className="mb-4 text-sm font-bold uppercase tracking-wide text-white/50">
            Parties enregistrées
          </h2>
          {gamesQuery.isLoading ? (
            <p className="text-white/60">Chargement…</p>
          ) : gamesQuery.isError ? (
            <div className="space-y-3">
              <p className="text-p1">{historyError}</p>
              <Button variant="secondary" onClick={() => void gamesQuery.refetch()}>
                Réessayer
              </Button>
            </div>
          ) : (
            <GameHistoryList games={gamesQuery.data ?? []} linkToReview />
          )}
        </Card>
      )}
    </div>
  );
}
