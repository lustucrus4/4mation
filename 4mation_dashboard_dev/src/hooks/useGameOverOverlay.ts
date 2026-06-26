import { useCallback, useEffect, useRef, useState } from "react";
import type { GameOverIntro } from "../components/game/GameOverOverlay";

export const GAME_OVER_OVERLAY_MS = 10_000;

export function useGameOverOverlay(autoDismissMs = GAME_OVER_OVERLAY_MS) {
  const [intro, setIntro] = useState<GameOverIntro | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, []);

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const dismiss = useCallback(() => {
    clearTimer();
    setIntro(null);
  }, [clearTimer]);

  const show = useCallback(
    (next: GameOverIntro) => {
      clearTimer();
      setIntro(next);
      if (autoDismissMs > 0) {
        timerRef.current = setTimeout(() => {
          if (!mountedRef.current) return;
          setIntro(null);
          timerRef.current = null;
        }, autoDismissMs);
      }
    },
    [autoDismissMs, clearTimer]
  );

  return { intro, show, dismiss };
}
