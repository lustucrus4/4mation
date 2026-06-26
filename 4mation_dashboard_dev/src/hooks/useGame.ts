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
  undoTo,
  type Bot,
  type GameMode,
  type GameState,
  type SavedGameInfo,
} from "../lib/gameApi";
import { gameStateToIntro } from "../lib/gameOverHelpers";
import { useGameOverOverlay } from "./useGameOverOverlay";

import {
  AFTER_PROVEN_LOSS_CAP,
  type PositionStatus,
} from "../lib/winRateDisplay";

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
  ratesProvenLoss: Record<string, boolean>;
  positionStatus: PositionStatus;
  /** Après un coup à défaite prouvée : estimations plafonnées. */
  afterProvenBlunder: boolean;
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

  const {
    intro: gameOverOverlay,
    show: showGameOverOverlay,
    dismiss: dismissGameOverOverlay,
  } = useGameOverOverlay();

  const analysisToken = useRef(0);
  const afterProvenBlunderRef = useRef(false);
  const initStarted = useRef(false);
  const wasTerminalRef = useRef(false);
  const botsRef = useRef(bots);
  const modeRef = useRef(mode);
  const botIdRef = useRef(selectedBotId);
  modeRef.current = mode;
  botIdRef.current = selectedBotId;
  botsRef.current = bots;

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
        ratesProvenLoss: {},
        positionStatus: w === 1 ? "proven_winning" : w === 2 ? "proven_losing" : "proven_draw",
        afterProvenBlunder: false,
      });
      return;
    }
    const token = ++analysisToken.current;
    try {
      const { analysis: a } = await analyze(MCTS_BUDGET_MS);
      if (token !== analysisToken.current) return;
      const exact = Boolean(a.exact);
      const positionStatus: PositionStatus = a.position_status ?? "estimated";
      const rates: Record<string, number> = {};
      const ratesProvenLoss: Record<string, boolean> = {};
      const capRates =
        afterProvenBlunderRef.current && !exact && positionStatus !== "proven_losing";

      for (const m of a.moves ?? []) {
        const key = `${m.row},${m.col}`;
        let wr = m.win_rate;
        if (capRates) {
          wr = Math.min(wr, AFTER_PROVEN_LOSS_CAP);
        }
        rates[key] = wr;
        if (m.proven_loss) {
          ratesProvenLoss[key] = true;
        }
      }

      if (positionStatus === "proven_losing") {
        afterProvenBlunderRef.current = true;
      } else if (exact && positionStatus !== "proven_losing") {
        afterProvenBlunderRef.current = false;
      }

      let winRateP1 = typeof a.win_rate_p1 === "number" ? a.win_rate_p1 : 0.5;
      if (capRates) {
        winRateP1 = Math.min(winRateP1, AFTER_PROVEN_LOSS_CAP);
      }
      if (positionStatus === "proven_losing") {
        winRateP1 = 0;
      }

      setAnalysis({
        winRateP1,
        label: a.label || (exact ? "Exact (tablebase)" : "Estimé (MCTS)"),
        exact,
        source: a.label || a.source || "",
        bestMove: Array.isArray(a.best_move)
          ? { row: a.best_move[0], col: a.best_move[1] }
          : null,
        rates,
        ratesProvenLoss,
        positionStatus,
        afterProvenBlunder: afterProvenBlunderRef.current,
      });
    } catch {
      if (token === analysisToken.current) {
        setAnalysis((prev) => (prev ? { ...prev, source: "analyse indisponible" } : prev));
      }
    }
  }, []);

  const opponentNameForMode = useCallback((m: GameMode) => {
    if (m === "learning") return "Coach";
    const bot = botsRef.current.find((b) => b.id === botIdRef.current);
    return bot?.name ?? "IA";
  }, []);

  const applyState = useCallback(
    (next: GameState, saved?: SavedGameInfo | null) => {
      setState(next);
      if (saved) setSavedGame(saved);
      setMessage(statusMessage(next, modeRef.current, saved));

      if (next.is_terminal && !wasTerminalRef.current) {
        showGameOverOverlay(
          gameStateToIntro(next, {
            mode: modeRef.current,
            opponentName: opponentNameForMode(modeRef.current),
            savedGame: saved !== undefined ? saved : savedGame,
          })
        );
      } else if (!next.is_terminal) {
        dismissGameOverOverlay();
      }
      wasTerminalRef.current = next.is_terminal;

      // L'analyse (barre W/L, meilleur coup, taux par case) n'est utile qu'en
      // mode apprentissage. En classique, on joue « à l'aveugle » : pas d'aide.
      if (modeRef.current === "learning") {
        void runAnalysis(next);
      } else {
        analysisToken.current += 1; // invalide une analyse en vol éventuelle
        setAnalysis(null);
      }
    },
    [dismissGameOverOverlay, opponentNameForMode, runAnalysis, savedGame, showGameOverOverlay]
  );

  const newGame = useCallback(
    async (nextMode?: GameMode) => {
      const m = nextMode ?? modeRef.current;
      dismissGameOverOverlay();
      wasTerminalRef.current = false;
      afterProvenBlunderRef.current = false;
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
    [applyState, botIdForMode, dismissGameOverOverlay]
  );

  const playHuman = useCallback(
    async (row: number, col: number) => {
      if (busy) return;
      const moveKey = `${row},${col}`;
      const cellRate = analysis?.rates[moveKey];
      if (
        analysis?.ratesProvenLoss[moveKey] ||
        (analysis?.exact && cellRate !== undefined && cellRate <= 0.005)
      ) {
        afterProvenBlunderRef.current = true;
      }
      setBusy(true);
      setMessage("Coup en cours…");
      setError(null);
      let finalState: GameState | null = null;
      let saved: SavedGameInfo | null | undefined = null;
      try {
        const res = await playMove(row, col);
        finalState = res.state;
        saved = res.saved_game;
        applyState(finalState, saved ?? undefined);

        if (modeRef.current === "standard" && !res.terminal && res.next_player === 2) {
          setMessage("Réflexion de l'IA…");
          try {
            const ai = await aiMove(botIdRef.current);
            finalState = ai.state;
            saved = ai.saved_game ?? saved;
          } catch {
            const ai = await aiMove(botIdRef.current);
            finalState = ai.state;
            saved = ai.saved_game ?? saved;
          }
        } else if (
          modeRef.current === "learning" &&
          !res.terminal &&
          res.state.current_player === 2 &&
          !res.coach_action
        ) {
          setError("Le coach n'a pas pu répondre. Utilisez Annuler ou Nouvelle partie.");
        }
      } catch (err) {
        if (isSessionLost(err)) {
          await newGame();
          return;
        }
        if (finalState?.current_player === 2 && modeRef.current === "standard") {
          try {
            setMessage("Réflexion de l'IA…");
            const ai = await aiMove(botIdRef.current);
            finalState = ai.state;
            saved = ai.saved_game ?? saved;
          } catch (aiErr) {
            setError(
              aiErr instanceof Error
                ? `L'IA n'a pas pu jouer : ${aiErr.message}`
                : "L'IA n'a pas pu jouer."
            );
          }
        } else {
          setError(err instanceof Error ? err.message : "Erreur inconnue");
        }
      } finally {
        setBusy(false);
        if (finalState) applyState(finalState, saved ?? undefined);
      }
    },
    [busy, applyState, newGame, analysis]
  );

  const playAi = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    setMessage("Réflexion de l'IA…");
    setError(null);
    try {
      const ai = await aiMove(botIdRef.current);
      applyState(ai.state, ai.saved_game ?? undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur inconnue");
    } finally {
      setBusy(false);
    }
  }, [busy, applyState]);

  const undo = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    setMessage("Annulation…");
    try {
      // Annule le coup coach + le coup humain en mode apprentissage.
      const count = modeRef.current === "learning" ? 2 : modeRef.current === "standard" ? 2 : 1;
      const { state: s } = await undoMove(count).catch(() => undoMove(1));
      afterProvenBlunderRef.current = false;
      applyState(s);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur inconnue");
    } finally {
      setBusy(false);
    }
  }, [busy, applyState]);

  const undoToMove = useCallback(
    async (moveIndex: number) => {
      if (busy) return;
      setBusy(true);
      setMessage("Navigation…");
      setError(null);
      try {
        const { state: s } = await undoTo(moveIndex);
        afterProvenBlunderRef.current = false;
        applyState(s);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Erreur inconnue");
      } finally {
        setBusy(false);
      }
    },
    [busy, applyState]
  );

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
    undoToMove,
    gameOverOverlay,
    dismissGameOverOverlay,
  };
}
