const LABELS: Record<string, string> = {
  best: "Meilleur coup",
  excellent: "Excellent",
  good: "Bon coup",
  inaccuracy: "Imprécision",
  mistake: "Erreur",
  blunder: "Gaffe",
  unknown: "—",
};

const COLORS: Record<string, string> = {
  best: "#7bed9f",
  excellent: "#a8e6cf",
  good: "#11f1cc",
  inaccuracy: "#feca57",
  mistake: "#ff9f43",
  blunder: "#ff4757",
  unknown: "rgba(255,255,255,0.4)",
};

export function classificationLabel(c: string): string {
  return LABELS[c] ?? c;
}

export function classificationColor(c: string): string {
  return COLORS[c] ?? COLORS.unknown;
}

const PHASE_LABELS: Record<string, string> = {
  opening: "Ouverture",
  middlegame: "Milieu de partie",
  endgame: "Finale",
};

export function phaseLabel(p: string): string {
  return PHASE_LABELS[p] ?? p;
}

const NATURE_LABELS: Record<string, string> = {
  proven: "Prouvé",
  estimated: "Estimé",
  unknown: "Non analysé",
};

const NATURE_COLORS: Record<string, string> = {
  proven: "#7bed9f",
  estimated: "#feca57",
  unknown: "rgba(255,255,255,0.4)",
};

export function natureLabel(n: string): string {
  return NATURE_LABELS[n] ?? n;
}

export function natureColor(n: string): string {
  return NATURE_COLORS[n] ?? NATURE_COLORS.unknown;
}
