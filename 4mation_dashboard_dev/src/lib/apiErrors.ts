/** Messages d'erreur API lisibles côté UI. */
export function parseApiErrorMessage(err: unknown, fallback: string): string {
  const raw = err instanceof Error ? err.message : String(err ?? "");
  if (!raw.trim()) return fallback;

  try {
    const parsed = JSON.parse(raw) as { error?: string };
    if (parsed.error === "Connexion requise") {
      return "Session expirée — reconnectez-vous via le bouton Connexion.";
    }
    if (parsed.error === "Base de données indisponible") {
      return "Historique temporairement indisponible (PostgreSQL). Réessayez dans quelques secondes.";
    }
    if (parsed.error) return parsed.error;
  } catch {
    /* corps non JSON */
  }

  if (raw.includes("Connexion requise") || raw.includes("401")) {
    return "Session expirée — reconnectez-vous via le bouton Connexion.";
  }
  if (raw.includes("Base de données indisponible") || raw.includes("503")) {
    return "Historique temporairement indisponible (PostgreSQL). Réessayez dans quelques secondes.";
  }

  return fallback;
}
