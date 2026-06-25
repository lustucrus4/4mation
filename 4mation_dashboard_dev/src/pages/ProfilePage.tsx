import { Link } from "react-router-dom";
import Card from "../components/ui/Card";
import GameHistoryList from "../components/account/GameHistoryList";
import { useAccount } from "../hooks/useAccount";
import { useEffect } from "react";

export default function ProfilePage() {
  const { authenticated, authLoading, profile, loading, error, refresh } = useAccount();

  useEffect(() => {
    const handler = () => refresh();
    window.addEventListener("4mation:game-saved", handler);
    return () => window.removeEventListener("4mation:game-saved", handler);
  }, [refresh]);

  if (authLoading || loading) {
    return <p className="text-white/60">Chargement du profil…</p>;
  }

  if (!authenticated) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-black text-accent">Profil</h1>
        <Card>
          <p className="text-white/70">
            Connectez-vous via le bouton en haut à droite pour enregistrer vos parties, suivre
            votre Elo et consulter votre historique.
          </p>
          <p className="mt-2 text-sm text-white/50">
            En mode invité, vous pouvez toujours jouer contre les bots sans sauvegarde.
          </p>
        </Card>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-black text-accent">Profil</h1>
        <Card>
          <p className="text-p1">Impossible de charger le profil (base de données ou session).</p>
        </Card>
      </div>
    );
  }

  const rating = profile?.rating;
  const ratingOnline = profile?.rating_online;
  const user = profile?.user;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-black text-accent">Profil</h1>

      <div className="grid gap-5 lg:grid-cols-[1fr_1fr]">
        <Card>
          <p className="text-lg font-bold">{user?.display_name || user?.username}</p>
          {user?.email && <p className="text-sm text-white/60">{user.email}</p>}
          {rating && (
            <div className="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-4">
              <Stat label="Elo (bots)" value={String(rating.elo)} accent />
              <Stat label="Parties" value={String(rating.games_played)} />
              <Stat label="Victoires" value={String(rating.wins)} />
              <Stat label="Défaites" value={String(rating.losses)} />
            </div>
          )}
          {ratingOnline && (
            <div className="mt-4 border-t border-white/10 pt-4">
              <p className="text-xs font-bold uppercase tracking-wide text-white/40">En ligne</p>
              <div className="mt-2 grid grid-cols-2 gap-4 sm:grid-cols-4">
                <Stat label="Elo online" value={String(ratingOnline.elo)} accent />
                <Stat label="Parties" value={String(ratingOnline.games_played)} />
                <Stat label="Victoires" value={String(ratingOnline.wins)} />
                <Stat label="Défaites" value={String(ratingOnline.losses)} />
              </div>
            </div>
          )}
        </Card>

        <Card>
          <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-white/50">
            Ratio victoires
          </h2>
          {rating && rating.games_played > 0 ? (
            <p className="text-3xl font-black text-accent">
              {Math.round((rating.wins / rating.games_played) * 100)}%
            </p>
          ) : (
            <p className="text-white/60">Jouez une partie classique vs bot pour démarrer.</p>
          )}
        </Card>
      </div>

      <Card>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-bold uppercase tracking-wide text-white/50">
            Dernières parties
          </h2>
          <Link to="/analyze" className="text-sm text-accent hover:underline">
            Tout voir →
          </Link>
        </div>
        <GameHistoryList
          games={profile?.recent_games ?? []}
          emptyMessage="Aucune partie enregistrée pour l'instant."
        />
      </Card>
    </div>
  );
}

function Stat({
  label,
  value,
  accent = false,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-white/45">{label}</p>
      <p className={`mt-1 text-xl font-bold ${accent ? "text-accent" : "text-white"}`}>{value}</p>
    </div>
  );
}
