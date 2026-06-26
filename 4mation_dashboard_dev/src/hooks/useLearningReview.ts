import { useCallback, useEffect, useRef, useState } from "react";
import type { GameState } from "../lib/gameApi";
import type { MoveClassification } from "../lib/accountApi";
import type { AnalysisView } from "./useGame";
import {
  classifyFromAnalysis,
  winRateP1,
  type AnalysisSnapshot,
} from "../lib/moveReview";
import type { HistoryMoveItem } from "../components/review/MoveHistoryList";

export interface EvalGraphPoint {
  move_index: number;
  win_rate_p1: number;
  player?: number;
}

interface StoredMoveMeta {
  index: number;
  player: number;
  row: number;
  col: number;
  classification: MoveClassification;
  isHuman: boolean;
  displayPercent: number | null;
  winRatePlayed: number;
  winRateBest: number;
}

function toSnapshot(analysis: AnalysisView): AnalysisSnapshot {
  return {
    winRateP1: analysis.winRateP1,
    bestMove: analysis.bestMove,
    rates: analysis.rates,
  };
}

export function useLearningReview(
  state: GameState | null,
  analysis: AnalysisView | null,
  _busy: boolean
) {
  const [viewMoveIndex, setViewMoveIndex] = useState(0);
  const [storedMoves, setStoredMoves] = useState<StoredMoveMeta[]>([]);
  const [graph, setGraph] = useState<EvalGraphPoint[]>([
    { move_index: 0, win_rate_p1: 0.5 },
  ]);
  const [positionAnalysis, setPositionAnalysis] = useState<
    Record<number, AnalysisView | null>
  >({ 0: null });

  const processedCountRef = useRef(0);
  const humanTurnAnalysisRef = useRef<AnalysisSnapshot | null>(null);
  const atLiveRef = useRef(true);

  const liveCount = state?.move_count ?? 0;
  const isAtLive = viewMoveIndex >= liveCount;

  useEffect(() => {
    if (state?.current_player === 1 && analysis && !state.is_terminal) {
      humanTurnAnalysisRef.current = toSnapshot(analysis);
    }
  }, [state?.current_player, state?.is_terminal, analysis]);

  useEffect(() => {
    if (!state) return;

    if (state.move_count < processedCountRef.current) {
      const keep = state.move_count;
      setStoredMoves((prev) => prev.slice(0, keep));
      setGraph((prev) => prev.slice(0, keep + 1));
      setPositionAnalysis((prev) => {
        const next: Record<number, AnalysisView | null> = {};
        for (let i = 0; i <= keep; i++) {
          if (prev[i] !== undefined) next[i] = prev[i];
        }
        return next;
      });
      processedCountRef.current = keep;
      setViewMoveIndex(keep);
      atLiveRef.current = true;
      return;
    }

    if (state.move_count > processedCountRef.current) {
      const newEntries = state.history.slice(processedCountRef.current);
      const additions: StoredMoveMeta[] = [];
      const graphAdds: EvalGraphPoint[] = [];

      for (const entry of newEntries) {
        const isHuman = entry.player === 1;
        let classification: MoveClassification = "unknown";
        let displayPercent: number | null = null;
        let winRatePlayed = 0.5;
        let winRateBest = 0.5;
        let wrBefore = 0.5;

        if (isHuman && humanTurnAnalysisRef.current) {
          const snap = humanTurnAnalysisRef.current;
          wrBefore = snap.winRateP1;
          const c = classifyFromAnalysis(snap, entry.row, entry.col);
          classification = c.classification;
          displayPercent = Math.round(c.accuracy ?? 0);
          winRatePlayed = c.winRatePlayed;
          winRateBest = c.winRateBest;
        }

        additions.push({
          index: entry.index,
          player: entry.player,
          row: entry.row,
          col: entry.col,
          classification,
          isHuman,
          displayPercent,
          winRatePlayed,
          winRateBest,
        });

        graphAdds.push({
          move_index: entry.index,
          win_rate_p1: winRateP1(wrBefore, entry.player),
          player: entry.player,
        });
      }

      if (additions.length > 0) {
        setStoredMoves((prev) => [...prev, ...additions]);
        setGraph((prev) => [...prev, ...graphAdds]);
      }
      processedCountRef.current = state.move_count;

      if (atLiveRef.current) {
        setViewMoveIndex(state.move_count);
      }
    }

    if (analysis && isAtLive) {
      setPositionAnalysis((prev) => ({
        ...prev,
        [state.move_count]: analysis,
      }));
    }
  }, [state, analysis, isAtLive]);

  const reset = useCallback(() => {
    processedCountRef.current = 0;
    humanTurnAnalysisRef.current = null;
    atLiveRef.current = true;
    setViewMoveIndex(0);
    setStoredMoves([]);
    setGraph([{ move_index: 0, win_rate_p1: 0.5 }]);
    setPositionAnalysis({ 0: null });
  }, []);

  const goToMove = useCallback(
    (index: number) => {
      const next = Math.max(0, Math.min(liveCount, index));
      setViewMoveIndex(next);
      atLiveRef.current = next >= liveCount;
    },
    [liveCount]
  );

  const viewedAnalysis: AnalysisView | null = isAtLive
    ? analysis
    : positionAnalysis[viewMoveIndex] ?? null;

  const historyMoves: HistoryMoveItem[] = storedMoves.map((m) => ({
    index: m.index,
    player: m.player,
    row: m.row,
    col: m.col,
    classification: m.classification,
    isHuman: m.isHuman,
    displayPercent: m.displayPercent,
  }));

  const currentStored =
    viewMoveIndex > 0 ? storedMoves[viewMoveIndex - 1] ?? null : null;

  return {
    viewMoveIndex,
    liveCount,
    goToMove,
    isAtLive,
    graph,
    historyMoves,
    viewedAnalysis,
    currentStored,
    reset,
  };
}
