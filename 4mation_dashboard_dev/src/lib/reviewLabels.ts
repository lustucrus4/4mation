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
