import type { Move } from "../components/game/Board";

export interface BoardInteractionState {
  is_terminal?: boolean;
  current_player: number;
  move_count: number;
  valid_actions: Move[];
}

export interface BoardInteractionOptions {
  /** Couleur du joueur local (1 = rouge par défaut). */
  humanColor?: number;
  /** Si false, aucun coup n'est jouable (relecture, attente…). */
  active?: boolean;
}

export interface BoardInteractionProps {
  playable: Move[];
  dimInvalid: boolean;
  muteEmpty: boolean;
}

/** Coups légaux, assombrissement connexité et cases vides — même logique que le mode en ligne. */
export function boardInteractionProps(
  state: BoardInteractionState | null | undefined,
  options: BoardInteractionOptions = {}
): BoardInteractionProps {
  const humanColor = options.humanColor ?? 1;
  const active = options.active ?? true;

  if (!state || state.is_terminal || !active) {
    return {
      playable: [],
      dimInvalid: false,
      muteEmpty: Boolean(state && !state.is_terminal && !active),
    };
  }

  const isYourTurn = state.current_player === humanColor;

  return {
    playable: isYourTurn ? state.valid_actions : [],
    dimInvalid: isYourTurn && state.move_count > 0,
    muteEmpty: !isYourTurn,
  };
}
