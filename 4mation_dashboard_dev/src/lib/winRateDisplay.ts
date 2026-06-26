/** Affichage pédagogique des taux de victoire (mode apprentissage). */

export type PositionStatus =
  | "proven_losing"
  | "proven_winning"
  | "proven_draw"
  | "estimated";

/** Texte affiché sur une case jouable. */
export function formatCellWinRate(rate: number, exact: boolean, provenLoss?: boolean): string {
  const r = Math.max(0, Math.min(1, rate));
  if (exact && (provenLoss || r <= 0.005)) {
    return "0%";
  }
  if (!exact && r <= 0.03) {
    return "<5%";
  }
  return `${Math.round(r * 100)}%`;
}

/** Texte pour la barre W/L (joueur 1). */
export function formatBarWinRate(
  rate: number,
  exact: boolean,
  positionStatus?: PositionStatus
): string {
  const r = Math.max(0, Math.min(1, rate));
  if (positionStatus === "proven_losing") {
    return "0%";
  }
  if (positionStatus === "proven_winning") {
    return "100%";
  }
  if (!exact && r <= 0.03) {
    return "<5%";
  }
  return `${Math.round(r * 100)}%`;
}

export function positionStatusHint(status?: PositionStatus): string | null {
  switch (status) {
    case "proven_losing":
      return "Position perdante prouvée — tous les coups mènent à la défaite si le coach joue parfaitement.";
    case "proven_winning":
      return "Position gagnante prouvée — victoire forcée avec le bon jeu.";
    case "proven_draw":
      return "Nul prouvé avec le jeu parfait des deux côtés.";
    default:
      return null;
  }
}

/** Plafond après un coup à défaite prouvée (évite un faux rebond MCTS). */
export const AFTER_PROVEN_LOSS_CAP = 0.05;
