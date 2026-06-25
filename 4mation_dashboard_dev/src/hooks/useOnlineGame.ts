import { useCallback, useEffect, useRef, useState } from "react";
import { connectOnlineSocket, disconnectSocket, getGuestName, getSocket } from "../lib/socket";
import type { MoveHistoryEntry } from "../lib/gameApi";

export type OnlinePhase =
  | "connecting"
  | "idle"
  | "queued"
  | "private_wait"
  | "playing"
  | "finished";

export interface OnlinePlayerInfo {
  display_name: string;
  elo: number;
  color: number;
}

export interface OnlineGameState {
  board: number[][];
  current_player: number;
  is_terminal: boolean;
  winner: number | null;
  move_count: number;
  mode: string;
  valid_actions: { row: number; col: number }[];
  last_move: { row: number; col: number } | null;
  history: MoveHistoryEntry[];
  your_color: number;
  room_id: string;
  you: OnlinePlayerInfo;
  opponent: OnlinePlayerInfo;
}

export interface GameOverPayload {
  room_id: string;
  winner: number | null;
  your_color: number;
  resign_by: number | null;
  elo_delta?: number;
  elo_after?: number;
  is_guest?: boolean;
  opponent: { display_name: string; elo: number };
}

function gameOverMessage(payload: GameOverPayload): string {
  if (payload.winner === payload.your_color) {
    if (payload.elo_after != null && payload.elo_delta != null) {
      const sign = payload.elo_delta >= 0 ? "+" : "";
      return `Victoire ! Elo ${payload.elo_after} (${sign}${payload.elo_delta})`;
    }
    return "Victoire !";
  }
  if (payload.resign_by === payload.your_color) return "Abandon.";
  if (payload.winner === null) return "Match nul.";
  if (payload.elo_after != null && payload.elo_delta != null) {
    const sign = payload.elo_delta >= 0 ? "+" : "";
    return `Défaite. Elo ${payload.elo_after} (${sign}${payload.elo_delta})`;
  }
  return "Défaite.";
}

export function useOnlineGame(guestName?: string) {
  const [phase, setPhase] = useState<OnlinePhase>("connecting");
  const [elo, setElo] = useState<number | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [isGuest, setIsGuest] = useState(true);
  const [state, setState] = useState<OnlineGameState | null>(null);
  const [message, setMessage] = useState("Connexion…");
  const [error, setError] = useState<string | null>(null);
  const [gameOver, setGameOver] = useState<GameOverPayload | null>(null);
  const [busy, setBusy] = useState(false);
  const [privateCode, setPrivateCode] = useState<string | null>(null);

  const mounted = useRef(true);
  const stateRef = useRef(state);
  stateRef.current = state;

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    const name = guestName ?? getGuestName();
    const socket = connectOnlineSocket(name);
    setPhase("connecting");
    setMessage("Connexion au serveur…");
    setError(null);

    const onConnected = (data: {
      display_name: string;
      elo: number;
      is_guest?: boolean;
    }) => {
      if (!mounted.current) return;
      setDisplayName(data.display_name);
      setElo(data.elo);
      setIsGuest(Boolean(data.is_guest));
      setPhase("idle");
      setMessage(
        data.is_guest
          ? "Prêt — mode invité (Elo non enregistré)."
          : "Prêt — lancez une recherche de partie."
      );
    };

    const onQueued = () => {
      if (!mounted.current) return;
      setPhase("queued");
      setMessage("Recherche d'un adversaire…");
    };

    const onQueueLeft = () => {
      if (!mounted.current) return;
      setPrivateCode(null);
      setPhase("idle");
      setMessage("Recherche annulée.");
    };

    const onPrivateCreated = (data: { code: string }) => {
      if (!mounted.current) return;
      setPrivateCode(data.code);
      setPhase("private_wait");
      setMessage(`Partagez le code : ${data.code}`);
    };

    const onPrivateCancelled = () => {
      if (!mounted.current) return;
      setPrivateCode(null);
      setPhase("idle");
      setMessage("Salle privée annulée.");
    };

    const onMatchFound = (data: {
      opponent: { display_name: string; elo: number };
    }) => {
      if (!mounted.current) return;
      setPhase("playing");
      setGameOver(null);
      setMessage(`Partie vs ${data.opponent.display_name} (${data.opponent.elo} Elo)`);
    };

    const onState = (payload: OnlineGameState) => {
      if (!mounted.current) return;
      setState(payload);
      setBusy(false);
      if (payload.is_terminal) {
        setMessage(
          payload.winner === payload.your_color
            ? "Victoire !"
            : payload.winner === null
              ? "Match nul."
              : "Défaite."
        );
      } else if (payload.current_player === payload.your_color) {
        setMessage("À vous de jouer.");
      } else {
        setMessage("Tour de l'adversaire…");
      }
    };

    const onGameOver = (payload: GameOverPayload) => {
      if (!mounted.current) return;
      setGameOver(payload);
      setPhase("finished");
      setMessage(gameOverMessage(payload));
      if (!payload.is_guest && payload.elo_after != null) {
        setElo(payload.elo_after);
        window.dispatchEvent(new CustomEvent("4mation:game-saved"));
      }
    };

    const onError = (data: { message?: string }) => {
      if (!mounted.current) return;
      setError(data.message ?? "Erreur");
      setBusy(false);
    };

    const onConnectError = (err?: Error) => {
      if (!mounted.current) return;
      setPhase("idle");
      const detail = err?.message?.trim();
      setError(
        detail
          ? `Impossible de joindre le serveur en ligne (${detail}).`
          : "Impossible de joindre le serveur en ligne."
      );
      setMessage("");
    };

    socket.on("connect", () => {
      if (!mounted.current) return;
      setError(null);
    });

    socket.on("online:connected", onConnected);
    socket.on("online:queued", onQueued);
    socket.on("online:queue_left", onQueueLeft);
    socket.on("online:private_created", onPrivateCreated);
    socket.on("online:private_cancelled", onPrivateCancelled);
    socket.on("online:match_found", onMatchFound);
    socket.on("online:state", onState);
    socket.on("online:game_over", onGameOver);
    socket.on("online:error", onError);
    socket.on("connect_error", onConnectError);

    socket.connect();

    return () => {
      socket.emit("online:queue_leave");
      disconnectSocket();
    };
  }, [guestName]);

  const joinQueue = useCallback(() => {
    const s = getSocket();
    if (!s.connected) {
      setError("Connexion au serveur en cours… Réessayez dans un instant.");
      return;
    }
    setError(null);
    s.emit("online:queue_join");
  }, []);

  const leaveQueue = useCallback(() => {
    const s = getSocket();
    if (privateCode) s.emit("online:private_cancel", { code: privateCode });
    s.emit("online:queue_leave");
  }, [privateCode]);

  const createPrivate = useCallback(() => {
    const s = getSocket();
    if (!s.connected) {
      setError("Connexion au serveur en cours…");
      return;
    }
    setError(null);
    s.emit("online:private_create");
  }, []);

  const joinPrivate = useCallback((code: string) => {
    const s = getSocket();
    if (!s.connected) {
      setError("Connexion au serveur en cours…");
      return;
    }
    setError(null);
    s.emit("online:private_join", { code: code.toUpperCase().trim() });
  }, []);

  const playMove = useCallback((row: number, col: number) => {
    const s = stateRef.current;
    if (!s || s.is_terminal) return;
    setBusy(true);
    getSocket().emit("online:play_move", { room_id: s.room_id, row, col });
  }, []);

  const resign = useCallback(() => {
    const s = stateRef.current;
    if (!s) return;
    getSocket().emit("online:resign", { room_id: s.room_id });
  }, []);

  const yourColor = state?.your_color ?? null;
  const playable =
    state &&
    !state.is_terminal &&
    state.current_player === yourColor &&
    phase === "playing"
      ? state.valid_actions
      : [];

  return {
    phase,
    elo,
    displayName,
    isGuest,
    state,
    message,
    error,
    gameOver,
    busy,
    yourColor,
    playable,
    canSearch: phase === "idle" || phase === "finished",
    privateCode,
    joinQueue,
    leaveQueue,
    createPrivate,
    joinPrivate,
    playMove,
    resign,
  };
}
