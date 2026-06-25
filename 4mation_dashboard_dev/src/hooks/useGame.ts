import { useCallback, useEffect, useRef, useState } from "react";
import {
  aiMove,
  analyze,
  ensureSession,
  getState,
  isSessionLost,
  listBots,
  playMove,
  resetGame,
  undoMove,
  type Bot,
  type GameMode,
  type GameState,
  type SavedGameInfo,
} from "../lib/gameApi";

const MCTS_BUDGET_MS = 600;
const BOT_KEY = "4mation_bot_id";
const MODE_KEY = "4mation_mode";

export interface AnalysisView {
  winRateP1: number;
  label: string;
  exact: boolean;
  source: string;
  bestMove: { row: number; col: number } | null;
  /** Clé "row,col" → taux de victoire (0..1), pour le mode apprentissage. */
  rates: Record<string, number>;
}

function loadMode(): GameMode {
  const m = localStorage.getItem(MODE_KEY);
  return m === "learning" ? "learning" : "standard";
}

function statusMessage(state: GameState, mode: GameMode, saved?: SavedGameInfo | null): string {
  let base: string;
  if (state.is_terminal) {
    if (state.winner === 1) base = "Vous avez gagné ! 🎉";
    else if (state.winner === 2) base = mode === "learning" ? "Le coach a gagné." : "L'IA a gagné.";
    else base = "Match nul.";
  } else if (state.current_player === 1) {
    const count = state.valid_actions.length;
    base =
      count >= 49
        ? "Premier coup — cliquez où vous voulez."
        : `À vous de jouer (${count} case${count > 1 ? "s" : ""} valide${count > 1 ? "s" : ""}).`;
  } else {
    base = mode === "learning" ? "Le coach réfléchit…" : "Tour de l'IA…";
  }
  if (state.is_terminal && saved && typeof saved.elo_delta === "number") {
    const sign = saved.elo_delta >= 0 ? "+" : "";
    base += ` · Elo ${saved.elo_after} (${sign}${saved.elo_delta})`;
    window.dispatchEvent(new CustomEvent("4mation:game-saved"));
  }
  return base;
}

export function useGame() {
  const [state, setState] = useState<GameState | null>(null);
  const [bots, setBots] = useState<Bot[]>([]);
  const [selectedBotId, setSelectedBotIdState] = useState(
    () => localStorage.getItem(BOT_KEY) || "level_3"
  );
  const [mode, setModeState] = useState<GameMode>(loadMode);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("Chargement…");
  const [analysis, setAnalysis] = useState<AnalysisView | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [savedGame, setSavedGame] = useState<SavedGameInfo | null>(null);

  const analysisToken = useRef(0);
  const initStarted = useRef(false);
  const modeRef = useRef(mode);
  const botIdRef = useRef(selectedBotId);
  modeRef.current = mode;
  botIdRef.current = selectedBotId;

  const botIdForMode = useCallback(
    (m: GameMode) => (m === "standard" ? botIdRef.current : undefined),
    []
  );

  const runAnalysis = useCallback(async (current: GameState) => {
    if (current.is_terminal) {
      const w = current.winner;
      setAnalysis({
        winRateP1: w === 1 ? 1 : w === 2 ? 0 : 0.5,
        label: "Partie terminée",
        exact: true,
        source: "",
        bestMove: null,
        rates: {},
      });
      return;
    }
    const token = ++analysisToken.current;
    try {
      const { analysis: a } = await analyze(MCTS_BUDGET_MS);
      if (token !== analysisToken.current) return;
      const exact = Boolean(a.exact);
      const rates: Record<string, number> = {};
      for (const m of a.moves ?? []) rates[`${m.row},${m.col}`] = m.win_rate;
      setAnalysis({
        winRateP1: typeof a.win_rate_p1 === "number" ? a.win_rate_p1 : 0.5,
        label: a.label || (exact ? "Exact (tablebase)" : "Estimé (MCTS)"),
        exact,
        source: a.source || "",
        bestMove: Array.isArray(a.best_move)
          ? { row: a.best_move[0], col: a.best_move[1] }
          : null,
        rates,
      });
    } catch {
      if (token === analysisToken.current) {
        setAnalysis((prev) => (prev ? { ...prev, source: "analyse indisponible" } : prev));
      }
    }
  }, []);

  const applyState = useCallback(
    (next: GameState, saved?: SavedGameInfo | null) => {
      setState(next);
      if (saved) setSavedGame(saved);
      setMessage(statusMessage(next, modeRef.current, saved));
      // L'analyse (barre W/L, meilleur coup, taux par case) n'est utile qu'en
      // mode apprentissage. En classique, on joue « à l'aveugle » : pas d'aide.
      if (modeRef.current === "learning") {
        void runAnalysis(next);
      } else {
        analysisToken.current += 1; // invalide une analyse en vol éventuelle
        setAnalysis(null);
      }
    },
    [runAnalysis]
  );

  const newGame = useCallback(
    async (nextMode?: GameMode) => {
      const m = nextMode ?? modeRef.current;
      setBusy(true);
      setMessage("Nouvelle partie…");
      setError(null);
      try {
        await ensureSession(m, botIdForMode(m));
        const { state: s } = await resetGame(m, botIdForMode(m));
        setSavedGame(null);
        applyState(s);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Erreur inconnue");
      } finally {
        setBusy(false);
      }
    },
    [applyState, botIdForMode]
  );

  const playHuman = useCallback(
    async (row: number, col: number) => {
      if (busy) return;
      setBusy(true);
      setMessage("Coup en cours…");
      setError(null);
      let finalState: GameState | null = null;
      let saved: SavedGameInfo | null | undefined = null;
      try {
        const res = await playMove(row, col);
        finalState = res.state;
        saved = res.saved_game;
        if (modeRef.current === "standard" && !res.terminal && res.next_player === 2) {
          setMessage("Réflexion de l'IA…");
          const ai = await aiMove(selectedBotId);
          finalState = ai.state;
          saved = ai.saved_game ?? saved;
        }
      } catch (err) {
        if (isSessionLost(err)) {
          await newGame();
          return;
        }
        setError(err instanceof Error ? err.message : "Erreur inconnue");
      } finally {
        setBusy(false);
        if (finalState) applyState(finalState, saved ?? undefined);
      }
    },
    [busy, selectedBotId, applyState, newGame]
  );

  const playAi = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    setMessage("Réflexion de l'IA…");
    try {
      const ai = await aiMove(selectedBotId);
      applyState(ai.state, ai.saved_game ?? undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur inconnue");
    } finally {
      setBusy(false);
    }
  }, [busy, selectedBotId, applyState]);

  const undo = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    setMessage("Annulation…");
    try {
      // Annule le coup IA + le coup humain en mode standard (revenir à votre tour).
      const count = modeRef.current === "standard" ? 2 : 1;
      const { state: s } = await undoMove(count).catch(() => undoMove(1));
      applyState(s);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur inconnue");
    } finally {
      setBusy(false);
    }
  }, [busy, applyState]);

  const setMode = useCallback(
    async (next: GameMode) => {
      setModeState(next);
      localStorage.setItem(MODE_KEY, next);
      await newGame(next);
    },
    [newGame]
  );

  const setSelectedBotId = useCallback((id: string) => {
    setSelectedBotIdState(id);
    localStorage.setItem(BOT_KEY, id);
  }, []);

  useEffect(() => {
    if (initStarted.current) return;
    initStarted.current = true;
    (async () => {
      try {
        const { bots: list } = await listBots();
        setBots(list);
        // Si l'id de bot mémorisé n'existe plus (ancien schéma), on retombe sur
        // le niveau par défaut (intermédiaire) ou le premier disponible.
        const ids = new Set(list.map((b) => b.id));
        setSelectedBotIdState((prev) => {
          if (ids.has(prev)) return prev;
          const fallback = list.find((b) => b.id === "level_3")?.id ?? list[0]?.id ?? prev;
          localStorage.setItem(BOT_KEY, fallback);
          return fallback;
        });
      } catch {
        /* liste des bots indisponible */
      }
      try {
        await ensureSession(modeRef.current, botIdForMode(modeRef.current));
        const s = await getState();
        setModeState(s.mode);
        applyState(s);
      } catch (err) {
        setError(err instanceof Error ? err.message : "API injoignable");
        setMessage("Impossible de joindre l'API.");
      }
    })();
  }, [applyState]);

  const canUndo = !!state && state.move_count > 0 && !state.is_terminal && !busy;

  return {
    state,
    bots,
    selectedBotId,
    setSelectedBotId,
    mode,
    setMode,
    busy,
    message,
    analysis,
    savedGame,
    error,
    canUndo,
    newGame,
    playHuman,
    playAi,
    undo,
  };
}
