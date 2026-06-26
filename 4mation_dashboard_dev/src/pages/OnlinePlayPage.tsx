import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Board, { emptyBoard } from "../components/game/Board";
import MatchFoundOverlay from "../components/game/MatchFoundOverlay";
import GameOverOverlay from "../components/game/GameOverOverlay";
import Card from "../components/ui/Card";
import Button from "../components/ui/Button";
import { useOnlineGame } from "../hooks/useOnlineGame";
import { boardInteractionProps } from "../lib/boardInteraction";
import { useAccount } from "../hooks/useAccount";
import { getGuestName, rollGuestName, setGuestName } from "../lib/socket";
import { isGenericGuestName } from "../lib/guestNames";
import AuthButton from "../components/auth/AuthButton";

function PrivateCodeBadge({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);

  const copyCode = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      /* presse-papier indisponible (HTTP, permissions…) */
    }
  };

  return (
    <button
      type="button"
      onClick={() => void copyCode()}
      title="Cliquer pour copier le code"
      className="cursor-pointer rounded-lg bg-accent/15 px-3 py-2 font-mono text-lg font-bold text-accent transition hover:bg-accent/25"
    >
      {copied ? "Copié !" : code}
    </button>
  );
}

export default function OnlinePlayPage() {
  const navigate = useNavigate();
  const { authenticated, profile } = useAccount();
  const [nickname, setNickname] = useState(getGuestName);
  const [joinCode, setJoinCode] = useState("");
  const online = useOnlineGame();

  const board =
    online.phase === "playing" && online.state?.board
      ? online.state.board
      : online.phase === "match_found" || online.rematchWaiting
        ? emptyBoard()
        : online.state?.board ?? emptyBoard();
  const yourColor = online.yourColor;
  const isYourTurn =
    online.phase === "playing" &&
    !!online.state &&
    yourColor != null &&
    !online.state.is_terminal &&
    online.state.current_player === yourColor;
  const boardUi = boardInteractionProps(online.state ?? undefined, {
    humanColor: yourColor ?? 1,
    active: online.phase === "playing" && yourColor != null,
  });

  const applyNickname = () => {
    const trimmed = nickname.trim();
    if (!trimmed || isGenericGuestName(trimmed)) return;
    const next = trimmed.slice(0, 24);
    setGuestName(next);
    setNickname(next);
    if (online.canSearch || online.phase === "connecting") {
      online.reconnectWithGuest(next);
    }
  };

  const randomizeNickname = () => {
    const next = rollGuestName();
    setNickname(next);
    if (online.canSearch || online.phase === "connecting") {
      online.reconnectWithGuest(next);
    }
  };

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_340px]">
      <div className="relative">
        <Board
          key={online.boardRoomId ?? online.phase}
          board={board}
          playable={isYourTurn ? online.playable : []}
          dimInvalid={boardUi.dimInvalid}
          muteEmpty={boardUi.muteEmpty}
          lastMove={
            online.phase === "playing" ? (online.state?.last_move ?? null) : null
          }
          thinking={online.busy || online.phase === "match_found"}
          onCellClick={({ row, col }) => online.playMove(row, col)}
        />
        {online.matchIntro ? <MatchFoundOverlay intro={online.matchIntro} /> : null}
        {online.gameOverOverlay ? (
          <GameOverOverlay
            intro={online.gameOverOverlay}
            onDismiss={online.dismissGameOverOverlay}
            primaryAction={
              online.inPrivateSession
                ? {
                    label: online.rematchWaiting ? "En attente…" : "Rejouer",
                    onClick: online.requestPrivateRematch,
                  }
                : {
                    label: "Nouvelle partie",
                    onClick: online.joinQueue,
                  }
            }
            secondaryAction={
              online.gameOverOverlay.savedGameId
                ? {
                    label: "Analyser la partie",
                    onClick: () => {
                      navigate(`/analyze/${online.gameOverOverlay!.savedGameId}`);
                    },
                  }
                : undefined
            }
          />
        ) : null}

        {!online.gameOverOverlay ? (
          <p className="mt-4 text-center text-lg font-semibold text-accent">{online.message}</p>
        ) : null}
        {online.error && (
          <p className="mt-2 text-center text-sm text-p1">{online.error}</p>
        )}
        {!online.socketConnected && online.phase !== "connecting" && (
          <p className="mt-2 text-center text-sm text-amber-300">
            Déconnecté du serveur en ligne — vérifiez que l&apos;API realtime tourne.
          </p>
        )}
        {online.state && yourColor != null && (
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
              Un pseudo aléatoire vous est attribué. L&apos;Elo et l&apos;historique ne sont pas
              enregistrés.
            </p>
            <label className="mt-3 block text-sm font-semibold text-accent" htmlFor="nick">
              Pseudo
            </label>
            <div className="mt-1 flex gap-2">
              <input
                id="nick"
                value={nickname}
                onChange={(e) => setNickname(e.target.value)}
                onBlur={applyNickname}
                maxLength={24}
                disabled={online.phase === "playing" || online.phase === "private_wait"}
                className="min-w-0 flex-1 rounded-lg border border-white/20 bg-black/25 px-3 py-2 text-sm text-white disabled:opacity-50"
                placeholder="Paul (invité)"
              />
              <Button
                type="button"
                variant="ghost"
                onClick={randomizeNickname}
                disabled={online.phase === "playing" || online.phase === "private_wait"}
                title="Autre pseudo aléatoire"
              >
                Aléa
              </Button>
            </div>
            <div className="mt-3 text-xs text-white/50">
              Connectez-vous pour enregistrer votre Elo : <AuthButton />
            </div>
          </Card>
        )}

        {(!(online.isGuest && !authenticated) ||
          online.displayName ||
          online.state?.opponent) && (
          <Card>
            {!(online.isGuest && !authenticated) && (
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm text-white/60">Votre Elo en ligne</span>
                <span className="text-xl font-black text-accent">
                  {online.elo ?? profile?.rating_online?.elo ?? "—"}
                </span>
              </div>
            )}
            {online.displayName && (
              <p
                className={`text-xs text-white/50 ${!(online.isGuest && !authenticated) ? "mt-2" : ""}`}
              >
                Connecté : {online.displayName}
                {online.socketConnected ? "" : " (hors ligne)"}
              </p>
            )}
            {online.state?.opponent && (
              <div className="mt-3 border-t border-white/10 pt-3 text-sm text-white/70">
                Adversaire :{" "}
                <strong>{online.state.opponent.display_name}</strong> (
                {online.state.opponent.elo} Elo)
              </div>
            )}
            {!online.state?.opponent && online.sessionOpponent && (
              <div className="mt-3 border-t border-white/10 pt-3 text-sm text-white/70">
                Adversaire :{" "}
                <strong>{online.sessionOpponent.display_name}</strong> (
                {online.sessionOpponent.elo} Elo)
              </div>
            )}
          </Card>
        )}

        <Card>
          <h2 className="text-sm font-bold uppercase tracking-wide text-white/50">
            Partie privée
          </h2>
          <p className="mt-2 text-xs text-white/60">
            Créez une salle et partagez le code avec un ami (autre navigateur ou appareil).
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {online.canSearch ? (
              <Button variant="secondary" onClick={online.createPrivate}>
                Créer une salle
              </Button>
            ) : null}
            {online.phase === "private_wait" ? (
              <>
                <PrivateCodeBadge code={online.privateCode!} />
                <Button variant="ghost" onClick={online.leaveQueue}>
                  Annuler
                </Button>
              </>
            ) : null}
            {online.inPrivateSession && online.privateCode ? (
              <>
                <PrivateCodeBadge code={online.privateCode} />
                <span className="self-center text-xs text-white/50">Salle active</span>
              </>
            ) : null}
          </div>
          {(online.phase === "private_session" || online.inPrivateSession) && (
            <div className="mt-3 flex flex-wrap gap-2">
              <Button
                onClick={online.requestPrivateRematch}
                disabled={online.rematchWaiting || online.phase === "playing"}
              >
                {online.rematchWaiting ? "En attente de l'adversaire…" : "Rejouer"}
              </Button>
              <Button variant="ghost" onClick={online.leavePrivate}>
                Quitter la salle
              </Button>
            </div>
          )}
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
            <>
              <Button variant="ghost" onClick={online.resign}>
                Abandonner
              </Button>
              {online.inPrivateSession ? (
                <Button variant="ghost" onClick={online.leavePrivate}>
                  Quitter la salle
                </Button>
              ) : null}
            </>
          ) : null}
          {online.phase === "finished" && !online.inPrivateSession ? (
            <Button onClick={online.joinQueue}>Rejouer</Button>
          ) : null}
        </div>

        {online.phase === "queued" && (
          <p className="animate-pulse text-sm text-white/50">
            Appariement par proximité d&apos;Elo…
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
