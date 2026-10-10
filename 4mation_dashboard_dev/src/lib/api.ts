/**
 * Client HTTP de l'API 4mation.
 * - Préfixe configurable via VITE_API_URL (vide en dev → proxy Vite /api).
 * - Gère l'entête de session X-Session-Id (parties anonymes / invité).
 */

const API_BASE = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
const SESSION_KEY = "4mation_session_id";

/** Préfixe API (vide = même origine, proxy nginx /api). */
export function getApiBase(): string {
  return API_BASE;
}

export function getSessionId(): string | null {
  return localStorage.getItem(SESSION_KEY);
}

export function setSessionId(id: string): void {
  localStorage.setItem(SESSION_KEY, id);
}

/**
 * Erreur d'appel API.
 * - `message` : texte lisible par le joueur (jamais le corps brut d'une page HTML).
 * - `body` : corps brut de la réponse, pour les tests de cas précis (session perdue…).
 */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly body: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Traduit une réponse en erreur lisible : champ `error` du JSON, sinon message selon le code. */
export function friendlyApiMessage(status: number, body: string): string {
  try {
    const parsed = JSON.parse(body) as { error?: unknown; message?: unknown };
    const text = typeof parsed.error === "string" ? parsed.error : parsed.message;
    if (typeof text === "string" && text.trim()) return text.trim();
  } catch {
    /* corps non JSON (page d'erreur HTML de nginx ou Flask) */
  }
  if (status === 0) return "Impossible de joindre le serveur. Vérifiez votre connexion.";
  if (status === 401) return "Session expirée — reconnectez-vous via le bouton Connexion.";
  if (status === 404) return "Ressource introuvable.";
  if (status === 429) return "Trop de requêtes. Patientez quelques secondes.";
  if (status >= 502 && status <= 504) {
    return "Le serveur ne répond pas pour le moment. Réessayez dans quelques instants.";
  }
  if (status >= 500) return "Le serveur a rencontré une erreur. Réessayez dans quelques instants.";
  return `Erreur ${status}`;
}

export async function apiFetch<T = unknown>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const sid = getSessionId();
  if (sid) headers.set("X-Session-Id", sid);

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
      credentials: "include",
    });
  } catch {
    throw new ApiError(friendlyApiMessage(0, ""), 0, "");
  }

  const newSid = res.headers.get("X-Session-Id");
  if (newSid) setSessionId(newSid);

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new ApiError(friendlyApiMessage(res.status, text), res.status, text);
  }
  return (await res.json()) as T;
}
