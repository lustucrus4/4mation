import { useCallback, useEffect, useRef, useState } from "react";
import { connectOnlineSocket, disconnectSocket, getGuestName, getSocket } from "../lib/socket";
import type { MoveHistoryEntry } from "../lib/gameApi";
import type { MatchIntro } from "../components/game/MatchFoundOverlay";
import type { GameOverIntro } from "../components/game/GameOverOverlay";
import { useGameOverOverlay } from "./useGameOverOverlay";
import { computeValidActions } from "../lib/validActions";

export type OnlinePhase =
  | "connecting"
  | "idle"
  | "queued"
  | "private_wait"
  | "private_session"
  | "match_found"
  | "playing"
  | "finished";

const MATCH_INTRO_MS = 3000;

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
  end_reason?: "resign" | "disconnect" | null;
  elo_delta?: number;
  elo_after?: number;
  is_guest?: boolean;
  is_private?: boolean;
  private_code?: string;
  opponent: { display_name: string; elo: number };
}

function gameOverMessage(payload: GameOverPayload): string {
  const eloSuffix =
    payload.elo_after != null && payload.elo_delta != null
      ? (() => {
          const sign = payload.elo_delta! >= 0 ? "+" : "";
          return ` Elo ${payload.elo_after} (${sign}${payload.elo_delta})`;
        })()
      : "";

  if (payload.resign_by === payload.your_color) {
    return payload.end_reason === "disconnect"
      ? "Connexion perdue — défaite par abandon."
      : "Abandon.";
  }

  if (
    payload.winner === payload.your_color &&
    payload.end_reason === "disconnect"
  ) {
    return `L'adversaire a quitté la partie — victoire !${eloSuffix}`;
  }

  if (payload.winner === payload.your_color) {
    return `Victoire !${eloSuffix}`;
  }
  if (payload.winner === null) return "Match nul.";
  return `Défaite.${eloSuffix}`;
}

function gameOverSubtitle(payload: GameOverPayload): string {
  if (payload.winner === null) return "Égalité parfaite.";
  if (payload.resign_by === payload.your_color) {
    return payload.end_reason === "disconnect"
      ? "Connexion perdue."
      : "Vous avez abandonné.";
  }
  if (payload.end_reason === "disconnect") return "L'adversaire a quitté la partie.";
  if (payload.resign_by != null && payload.resign_by !== payload.your_color) {
    return "L'adversaire a abandonné.";
  }
  return payload.winner === payload.your_color
    ? "Belle partie !"
    : "Dommage, retentez votre chance.";
}

function toGameOverIntro(payload: GameOverPayload): GameOverIntro {
  const result: GameOverIntro["result"] =
    payload.winner === null
      ? "draw"
      : payload.winner === payload.your_color
        ? "win"
        : "loss";

  return {
    result,
    subtitle: gameOverSubtitle(payload),
    opponentName: payload.opponent.display_name,
    eloAfter: payload.elo_after,
    eloDelta: payload.elo_delta,
    isGuest: payload.is_guest,
  };
}

function turnMessage(payload: OnlineGameState): string {
  if (payload.is_terminal) {
    return payload.winner === payload.your_color
      ? "Victoire !"
      : payload.winner === null
        ? "Match nul."
        : "Défaite.";
  }
  return payload.current_player === payload.your_color
    ? "À vous de jouer."
    : "Tour de l'adversaire…";
}

function filterPlayableActions(
  state: OnlineGameState | null,
  yourColor: number | null,
  phase: OnlinePhase,
  busy: boolean
): { row: number; col: number }[] {
  if (
    !state ||
    state.is_terminal ||
    busy ||
    phase !== "playing" ||
    yourColor === null ||
    state.current_player !== yourColor
  ) {
    return [];
  }
  return computeValidActions(state.board, state.current_player, state.last_move);
}

export function useOnlineGame() {
  const [phase, setPhase] = useState<OnlinePhase>("connecting");
  const [socketConnected, setSocketConnected] = useState(false);
  const [elo, setElo] = useState<number | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [isGuest, setIsGuest] = useState(true);
  const [state, setState] = useState<OnlineGameState | null>(null);
  const [message, setMessage] = useState("Connexion…");
  const [error, setError] = useState<string | null>(null);
  const [gameOver, setGameOver] = useState<GameOverPayload | null>(null);
  const [busy, setBusy] = useState(false);
  const [privateCode, setPrivateCode] = useState<string | null>(null);
  const [inPrivateSession, setInPrivateSession] = useState(false);
  const [rematchWaiting, setRematchWaiting] = useState(false);
  const [sessionOpponent, setSessionOpponent] = useState<{
    display_name: string;
    elo: number;
  } | null>(null);
  const [matchIntro, setMatchIntro] = useState<MatchIntro | null>(null);
  const {
    intro: gameOverOverlay,
    show: showGameOverIntro,
    dismiss: dismissGameOverOverlay,
  } = useGameOverOverlay();

  const mounted = useRef(true);
  const stateRef = useRef(state);
  stateRef.current = state;
  const displayNameRef = useRef(displayName);
  displayNameRef.current = displayName;
  const introActiveRef = useRef(false);
  const pendingStateRef = useRef<OnlineGameState | null>(null);
  const matchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeRoomIdRef = useRef<string | null>(null);
  const closedRoomIdsRef = useRef<Set<string>>(new Set());
  const phaseRef = useRef(phase);
  phaseRef.current = phase;
  const privateCodeRef = useRef(privateCode);
  privateCodeRef.current = privateCode;
  const inPrivateSessionRef = useRef(inPrivateSession);
  inPrivateSessionRef.current = inPrivateSession;
  const unbindRef = useRef<(() => void) | null>(null);
  const cleanupConnectionRef = useRef<(() => void) | null>(null);

  const clearMatchTimer = useCallback(() => {
    if (matchTimerRef.current) {
      clearTimeout(matchTimerRef.current);
      matchTimerRef.current = null;
    }
  }, []);

  const showGameOverOverlay = useCallback(
    (payload: GameOverPayload) => {
      showGameOverIntro(toGameOverIntro(payload));
    },
    [showGameOverIntro]
  );

  const resetPrivateSession = useCallback(() => {
    setPrivateCode(null);
    setInPrivateSession(false);
    setRematchWaiting(false);
    setSessionOpponent(null);
  }, []);

  const clearMatchIntroState = useCallback(() => {
    introActiveRef.current = false;
    clearMatchTimer();
    setMatchIntro(null);
    pendingStateRef.current = null;
  }, [clearMatchTimer]);

  const forfeitActiveRoom = useCallback((socket: ReturnType<typeof getSocket>) => {
    if (phaseRef.current !== "playing" && phaseRef.current !== "match_found") {
      return;
    }
    const roomId =
      stateRef.current?.room_id ??
      pendingStateRef.current?.room_id ??
      activeRoomIdRef.current;
    if (roomId && socket.connected) {
      socket.emit("online:resign", { room_id: roomId });
    }
  }, []);

  const finishMatchIntro = useCallback(() => {
    if (!mounted.current) return;
    introActiveRef.current = false;
    clearMatchTimer();
    setMatchIntro(null);
    setPhase("playing");
    const pending = pendingStateRef.current;
    pendingStateRef.current = null;
    if (pending && pending.room_id === activeRoomIdRef.current) {
      setState(pending);
      setBusy(false);
      setMessage(turnMessage(pending));
    } else {
      setState(null);
      setBusy(false);
    }
  }, [clearMatchTimer]);

  const beginMatchIntro = useCallback(
    (data: {
      room_id: string;
      your_color: number;
      private_code?: string;
      opponent: { display_name: string; elo: number };
    }) => {
      activeRoomIdRef.current = data.room_id;
      clearMatchTimer();
      introActiveRef.current = true;
      pendingStateRef.current = null;
      setState(null);
      setBusy(false);
      setGameOver(null);
      setRematchWaiting(false);
      if (data.private_code) {
        setPrivateCode(data.private_code);
        setInPrivateSession(true);
        setSessionOpponent(data.opponent);
      }
      setMatchIntro({
        youName: displayNameRef.current || getGuestName(),
        opponentName: data.opponent.display_name,
        opponentElo: data.opponent.elo,
        yourColor: data.your_color,
      });
      setPhase("match_found");
      setMessage("Adversaire trouvé !");
      matchTimerRef.current = setTimeout(finishMatchIntro, MATCH_INTRO_MS);
    },
    [clearMatchTimer, finishMatchIntro]
  );

  const setupConnection = useCallback(
    (guestName?: string) => {
      cleanupConnectionRef.current?.();
      cleanupConnectionRef.current = null;

      const socket = connectOnlineSocket(guestName ?? getGuestName());
      setPhase("connecting");
      setSocketConnected(false);
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
        resetPrivateSession();
        activeRoomIdRef.current = null;
        setPhase("idle");
        setMessage("Recherche annulée.");
      };

      const onPrivateCreated = (data: { code: string }) => {
        if (!mounted.current) return;
        setPrivateCode(data.code);
        setInPrivateSession(false);
        setSessionOpponent(null);
        setPhase("private_wait");
        setMessage(`Partagez le code : ${data.code}`);
      };

      const onPrivateCancelled = () => {
        if (!mounted.current) return;
        resetPrivateSession();
        setPhase("idle");
        setMessage("Salle privée annulée.");
      };

      const onPrivateLeft = () => {
        if (!mounted.current) return;
        resetPrivateSession();
        activeRoomIdRef.current = null;
        setState(null);
        setGameOver(null);
        setPhase("idle");
        setMessage("Vous avez quitté la salle privée.");
      };

      const onPrivateOpponentLeft = (data: { reason?: string }) => {
        if (!mounted.current) return;
        resetPrivateSession();
        activeRoomIdRef.current = null;
        setState(null);
        setGameOver(null);
        dismissGameOverOverlay();
        setPhase("idle");
        setMessage(
          data.reason === "disconnect"
            ? "L'adversaire s'est déconnecté — salle fermée."
            : "L'adversaire a quitté la salle."
        );
      };

      const onPrivateRematchWaiting = () => {
        if (!mounted.current) return;
        setState(null);
        setRematchWaiting(true);
        setPhase("private_session");
        setMessage("En attente que l'adversaire accepte de rejouer…");
      };

      const onPrivateRematchOpponentReady = (data: { opponent_name?: string }) => {
        if (!mounted.current) return;
        const name = data.opponent_name ?? "L'adversaire";
        setMessage(`${name} souhaite rejouer — cliquez sur Rejouer pour lancer la partie.`);
      };

      const onPrivateSessionRestored = (data: {
        code: string;
        opponent: { display_name: string; elo: number };
        rematch_ready?: boolean;
        opponent_rematch_ready?: boolean;
      }) => {
        if (!mounted.current) return;
        setPrivateCode(data.code);
        setInPrivateSession(true);
        setSessionOpponent(data.opponent);
        setRematchWaiting(Boolean(data.rematch_ready && !data.opponent_rematch_ready));
        setPhase("private_session");
        setMessage(
          data.opponent_rematch_ready
            ? `${data.opponent.display_name} souhaite rejouer — cliquez sur Rejouer.`
            : `Salle ${data.code} — en attente d'une nouvelle partie.`
        );
      };

      const onMatchFound = (data: {
        room_id: string;
        your_color: number;
        private_code?: string;
        opponent: { display_name: string; elo: number };
      }) => {
        if (!mounted.current) return;
        beginMatchIntro(data);
      };

      const onState = (payload: OnlineGameState) => {
        if (!mounted.current) return;
        if (closedRoomIdsRef.current.has(payload.room_id)) return;

        if (introActiveRef.current) {
          if (payload.room_id === activeRoomIdRef.current) {
            pendingStateRef.current = payload;
          }
          return;
        }

        if (activeRoomIdRef.current && payload.room_id !== activeRoomIdRef.current) {
          return;
        }

        activeRoomIdRef.current = payload.room_id;
        setState(payload);
        setBusy(false);
        setMessage(turnMessage(payload));
        setPhase(payload.is_terminal ? "finished" : "playing");
      };

      const onGameOver = (payload: GameOverPayload) => {
        if (!mounted.current) return;
        clearMatchIntroState();
        closedRoomIdsRef.current.add(payload.room_id);
        activeRoomIdRef.current = null;
        setGameOver(payload);
        setRematchWaiting(false);
        if (payload.is_private && payload.private_code) {
          setPrivateCode(payload.private_code);
          setInPrivateSession(true);
          setSessionOpponent(payload.opponent);
          setPhase("private_session");
        } else {
          setPhase("finished");
        }
        setMessage(gameOverMessage(payload));
        showGameOverOverlay(payload);
        setState((prev) =>
          prev && prev.room_id === payload.room_id
            ? { ...prev, is_terminal: true, valid_actions: [], winner: payload.winner }
            : null
        );
        if (!payload.is_guest && payload.elo_after != null) {
          setElo(payload.elo_after);
          window.dispatchEvent(new CustomEvent("4mation:game-saved"));
        }
      };

      const onError = (data: { message?: string }) => {
        if (!mounted.current) return;
        setError(data.message ?? "Erreur");
        setBusy(false);
        if (phaseRef.current === "private_wait") {
          setPhase("idle");
          setPrivateCode(null);
        }
      };

      const onConnectError = (err?: Error) => {
        if (!mounted.current) return;
        setSocketConnected(false);
        setPhase("idle");
        const detail = err?.message?.trim();
        setError(
          detail
            ? `Impossible de joindre le serveur en ligne (${detail}).`
            : "Impossible de joindre le serveur en ligne."
        );
        setMessage("");
      };

      const onSocketConnect = () => {
        if (!mounted.current) return;
        setSocketConnected(true);
        setError(null);
      };

      const onSocketDisconnect = () => {
        if (!mounted.current) return;
        setSocketConnected(false);
      };

      socket.on("connect", onSocketConnect);
      socket.on("disconnect", onSocketDisconnect);
      socket.on("online:connected", onConnected);
      socket.on("online:queued", onQueued);
      socket.on("online:queue_left", onQueueLeft);
      socket.on("online:private_created", onPrivateCreated);
      socket.on("online:private_cancelled", onPrivateCancelled);
      socket.on("online:private_left", onPrivateLeft);
      socket.on("online:private_opponent_left", onPrivateOpponentLeft);
      socket.on("online:private_rematch_waiting", onPrivateRematchWaiting);
      socket.on("online:private_rematch_opponent_ready", onPrivateRematchOpponentReady);
      socket.on("online:private_session_restored", onPrivateSessionRestored);
      socket.on("online:match_found", onMatchFound);
      socket.on("online:state", onState);
      socket.on("online:game_over", onGameOver);
      socket.on("online:error", onError);
      socket.on("connect_error", onConnectError);

      unbindRef.current = () => {
        socket.off("connect", onSocketConnect);
        socket.off("disconnect", onSocketDisconnect);
        socket.off("online:connected", onConnected);
        socket.off("online:queued", onQueued);
        socket.off("online:queue_left", onQueueLeft);
        socket.off("online:private_created", onPrivateCreated);
        socket.off("online:private_cancelled", onPrivateCancelled);
        socket.off("online:private_left", onPrivateLeft);
        socket.off("online:private_opponent_left", onPrivateOpponentLeft);
        socket.off("online:private_rematch_waiting", onPrivateRematchWaiting);
        socket.off("online:private_rematch_opponent_ready", onPrivateRematchOpponentReady);
        socket.off("online:private_session_restored", onPrivateSessionRestored);
        socket.off("online:match_found", onMatchFound);
        socket.off("online:state", onState);
        socket.off("online:game_over", onGameOver);
        socket.off("online:error", onError);
        socket.off("connect_error", onConnectError);
      };

      const onPageHide = () => forfeitActiveRoom(socket);
      window.addEventListener("pagehide", onPageHide);
      socket.connect();

      const cleanup = () => {
        window.removeEventListener("pagehide", onPageHide);
        forfeitActiveRoom(socket);
        if (unbindRef.current) {
          unbindRef.current();
          unbindRef.current = null;
        }
        socket.emit("online:queue_leave");
        disconnectSocket();
      };
      cleanupConnectionRef.current = cleanup;
    },
    [beginMatchIntro, clearMatchIntroState, dismissGameOverOverlay, forfeitActiveRoom, resetPrivateSession, showGameOverOverlay]
  );

  useEffect(() => {
    mounted.current = true;
    setupConnection();
    return () => {
      mounted.current = false;
      cleanupConnectionRef.current?.();
      cleanupConnectionRef.current = null;
      clearMatchIntroState();
      dismissGameOverOverlay();
      activeRoomIdRef.current = null;
    };
  }, [setupConnection, clearMatchIntroState, dismissGameOverOverlay]);

  const reconnectWithGuest = useCallback(
    (guestName: string) => {
      const p = phaseRef.current;
      if (p === "playing" || p === "match_found") return;
      setupConnection(guestName);
    },
    [setupConnection]
  );

  const joinQueue = useCallback(() => {
    dismissGameOverOverlay();
    const s = getSocket();
    if (!s.connected) {
      setError("Serveur hors ligne — vérifiez la connexion ou réessayez.");
      return;
    }
    setError(null);
    setGameOver(null);
    setState(null);
    s.emit("online:queue_join");
  }, [dismissGameOverOverlay]);

  const leavePrivate = useCallback(() => {
    dismissGameOverOverlay();
    const s = getSocket();
    const code = privateCodeRef.current;
    s.emit("online:private_leave", code ? { code } : {});
  }, [dismissGameOverOverlay]);

  const requestPrivateRematch = useCallback(() => {
    dismissGameOverOverlay();
    setGameOver(null);
    setState(null);
    setError(null);
    getSocket().emit("online:private_rematch");
  }, [dismissGameOverOverlay]);

  const leaveQueue = useCallback(() => {
    const s = getSocket();
    const code = privateCodeRef.current;
    if (code && !inPrivateSessionRef.current) {
      s.emit("online:private_cancel", { code });
    } else if (inPrivateSessionRef.current) {
      leavePrivate();
      return;
    }
    s.emit("online:queue_leave");
    resetPrivateSession();
  }, [leavePrivate, resetPrivateSession]);

  const createPrivate = useCallback(() => {
    const s = getSocket();
    if (!s.connected) {
      setError("Serveur hors ligne — impossible de créer une salle.");
      return;
    }
    setError(null);
    setMessage("Création de la salle…");
    s.emit("online:private_create");
  }, []);

  const joinPrivate = useCallback((code: string) => {
    const s = getSocket();
    if (!s.connected) {
      setError("Serveur hors ligne — impossible de rejoindre.");
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
  const playable = filterPlayableActions(state, yourColor, phase, busy);
  const boardRoomId = state?.room_id ?? null;

  const canSearch =
    socketConnected &&
    (phase === "idle" || phase === "finished") &&
    !inPrivateSession;

  return {
    phase,
    socketConnected,
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
    boardRoomId,
    canSearch,
    privateCode,
    inPrivateSession,
    rematchWaiting,
    sessionOpponent,
    matchIntro,
    gameOverOverlay,
    dismissGameOverOverlay,
    reconnectWithGuest,
    joinQueue,
    leaveQueue,
    leavePrivate,
    requestPrivateRematch,
    createPrivate,
    joinPrivate,
    playMove,
    resign,
  };
}
