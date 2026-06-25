import { useState } from "react";
import { Link } from "react-router-dom";
import Board, { emptyBoard } from "../components/game/Board";
import Card from "../components/ui/Card";
import Button from "../components/ui/Button";
import { useOnlineGame } from "../hooks/useOnlineGame";
import { useAccount } from "../hooks/useAccount";
import { getGuestName, setGuestName } from "../lib/socket";
import AuthButton from "../components/auth/AuthButton";

export default function OnlinePlayPage() {
  const { authenticated, profile } = useAccount();
  const [nickname, setNickname] = useState(getGuestName);
  const [nicknameDraft, setNicknameDraft] = useState(nickname);
  const [joinCode, setJoinCode] = useState("");
  const online = useOnlineGame(authenticated ? undefined : nickname);

  const board = online.state?.board ?? emptyBoard();
  const yourColor = online.yourColor ?? 1;

  const applyNickname = () => {
    const next = nicknameDraft.trim().slice(0, 24) || "Invité";
    setGuestName(next);
    setNickname(next);
  };

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_340px]">
      <div>
        <Board
          board={board}
          playable={online.playable}
          lastMove={online.state?.last_move ?? null}
          thinking={online.busy}
          onCellClick={({ row, col }) => online.playMove(row, col)}
        />

        <p className="mt-4 text-center text-lg font-semibold text-accent">{online.message}</p>
        {online.error && (
          <p className="mt-2 text-center text-sm text-p1">{online.error}</p>
        )}
        {online.state && (
          <p className="mt-1 text-center text-xs text-white/50">
            Coup #{online.state.move_count}
            {yourColor === 1 ? " · Vous êtes rouge" : " · Vous êtes bleu"}
          </p>
        )}
      </div>

      <aside className="space-y-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h1 className="text-2xl font-black text-accent">En ligne</h1>
          <Link to="/play" className="text-sm text-white/50 hover:text-accent">
            ← vs IA
          </Link>
        </div>

        {online.isGuest && !authenticated && (
          <Card>
            <h2 className="text-sm font-bold uppercase tracking-wide text-white/50">
              Mode invité
            </h2>
            <p className="mt-2 text-sm text-white/70">
              Jouez sans compte. L'Elo et l'historique ne sont pas enregistrés.
            </p>
            <label className="mt-3 block text-sm font-semibold text-accent" htmlFor="nick">
              Pseudo
            </label>
            <div className="mt-1 flex gap-2">
              <input
                id="nick"
                value={nicknameDraft}
                onChange={(e) => setNicknameDraft(e.target.value)}
                maxLength={24}
                className="min-w-0 flex-1 rounded-lg border border-white/20 bg-black/25 px-3 py-2 text-sm text-white"
                placeholder="Invité"
              />
              <Button variant="ghost" onClick={applyNickname} disabled={online.phase === "playing"}>
                OK
              </Button>
            </div>
            <div className="mt-3 text-xs text-white/50">
              Connectez-vous pour enregistrer votre Elo : <AuthButton />
            </div>
          </Card>
        )}

        <Card>
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm text-white/60">
              {online.isGuest && !authenticated ? "Elo indicatif" : "Votre Elo en ligne"}
            </span>
            <span className="text-xl font-black text-accent">
              {online.elo ?? profile?.rating_online?.elo ?? "—"}
            </span>
          </div>
          {online.displayName && (
            <p className="mt-2 text-xs text-white/50">Connecté : {online.displayName}</p>
          )}
          {online.state?.opponent && (
            <div className="mt-3 border-t border-white/10 pt-3 text-sm text-white/70">
              Adversaire :{" "}
              <strong>{online.state.opponent.display_name}</strong> (
              {online.state.opponent.elo} Elo)
            </div>
          )}
        </Card>

        <Card>
          <h2 className="text-sm font-bold uppercase tracking-wide text-white/50">
            Partie privée
          </h2>
          <p className="mt-2 text-xs text-white/60">
            Créez une salle et partagez le code avec un ami sur l'autre navigateur.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {online.canSearch ? (
              <Button variant="secondary" onClick={online.createPrivate}>
                Créer une salle
              </Button>
            ) : null}
            {online.phase === "private_wait" ? (
              <>
                <span className="rounded-lg bg-accent/15 px-3 py-2 font-mono text-lg font-bold text-accent">
                  {online.privateCode}
                </span>
                <Button variant="ghost" onClick={online.leaveQueue}>
                  Annuler
                </Button>
              </>
            ) : null}
          </div>
          {online.canSearch && (
            <div className="mt-3 flex gap-2">
              <input
                value={joinCode}
                onChange={(e) => setJoinCode(e.target.value.toUpperCase().slice(0, 6))}
                placeholder="CODE"
                maxLength={6}
                className="min-w-0 flex-1 rounded-lg border border-white/20 bg-black/25 px-3 py-2 font-mono text-sm tracking-widest text-white"
              />
              <Button
                variant="ghost"
                onClick={() => joinCode.length === 6 && online.joinPrivate(joinCode)}
                disabled={joinCode.length !== 6}
              >
                Rejoindre
              </Button>
            </div>
          )}
        </Card>

        <div className="flex flex-wrap gap-2">
          <span className="w-full text-xs font-bold uppercase text-white/40">Matchmaking</span>
          {online.canSearch ? (
            <Button onClick={online.joinQueue}>Rechercher une partie</Button>
          ) : null}
          {online.phase === "queued" ? (
            <Button variant="ghost" onClick={online.leaveQueue}>
              Annuler la recherche
            </Button>
          ) : null}
          {online.phase === "playing" && online.state && !online.state.is_terminal ? (
            <Button variant="ghost" onClick={online.resign}>
              Abandonner
            </Button>
          ) : null}
          {online.phase === "finished" ? (
            <Button onClick={online.joinQueue}>Rejouer</Button>
          ) : null}
        </div>

        {online.phase === "queued" && (
          <p className="animate-pulse text-sm text-white/50">
            Appariement par proximité d'Elo…
          </p>
        )}

        <Timeline history={online.state?.history ?? []} yourColor={yourColor} />
      </aside>
    </div>
  );
}

function Timeline({
  history,
  yourColor,
}: {
  history: { index: number; player: number; row: number; col: number }[];
  yourColor: number;
}) {
  if (!history.length) return null;
  return (
    <Card className="max-h-48 overflow-y-auto !p-3">
      <h2 className="mb-2 text-sm font-bold uppercase tracking-wide text-white/50">Historique</h2>
      <ol className="space-y-1 text-sm text-white/70">
        {history.map((e) => {
          const who = e.player === yourColor ? "Vous" : "Adversaire";
          return (
            <li key={e.index}>
              <span className="text-white/40">#{e.index}</span> {who} : ({e.row + 1},{" "}
              {e.col + 1})
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
