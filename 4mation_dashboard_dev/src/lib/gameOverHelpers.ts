import type { GameOverIntro } from "../components/game/GameOverOverlay";
import type { GameMode, GameState, SavedGameInfo } from "./gameApi";

export function gameStateToIntro(
  state: GameState,
  options: {
    mode: GameMode;
    opponentName: string;
    savedGame?: SavedGameInfo | null;
  }
): GameOverIntro {
  const result: GameOverIntro["result"] =
    state.winner === 1 ? "win" : state.winner === 2 ? "loss" : "draw";

  let subtitle = "Égalité parfaite.";
  if (state.winner === 1) subtitle = "Belle partie !";
  else if (state.winner === 2) {
    subtitle =
      options.mode === "learning"
        ? "Le coach a remporté la partie."
        : "Dommage, retentez votre chance.";
  }

  const hasElo =
    options.savedGame?.elo_after != null && options.savedGame?.elo_delta != null;

  return {
    result,
    subtitle,
    opponentName: options.opponentName,
    eloAfter: options.savedGame?.elo_after,
    eloDelta: options.savedGame?.elo_delta,
    isGuest: hasElo ? false : undefined,
  };
}
