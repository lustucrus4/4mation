/**
 * Client HTTP de l'API 4mation.
 * - Préfixe configurable via VITE_API_URL (vide en dev → proxy Vite /api).
 * - Gère l'entête de session X-Session-Id (parties anonymes / invité).
 */

const API_BASE = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
const SESSION_KEY = "4mation_session_id";

export function getSessionId(): string | null {
  return localStorage.getItem(SESSION_KEY);
}

export function setSessionId(id: string): void {
  localStorage.setItem(SESSION_KEY, id);
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

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });

  const newSid = res.headers.get("X-Session-Id");
  if (newSid) setSessionId(newSid);

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `Erreur ${res.status}`);
  }
  return (await res.json()) as T;
}
