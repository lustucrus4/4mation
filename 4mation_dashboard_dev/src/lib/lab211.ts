/**
 * Intégration SSO Lab211 (SDK distant chargé dans index.html).
 */
const AUTH_API_BASE =
  import.meta.env.VITE_LAB211_AUTH_API_BASE || "https://auth.lab211.fr";
const SITE_KEY = "4mation";

export interface Lab211User {
  id: string;
  username?: string;
  email?: string;
  display_name?: string;
}

export interface Lab211Session {
  authenticated: boolean;
  user: Lab211User | null;
}

let initPromise: Promise<void> | null = null;

function waitForSdk(maxAttempts = 50, delayMs = 100): Promise<Lab211AuthSdk> {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    const tick = () => {
      if (window.Lab211Auth) return resolve(window.Lab211Auth);
      attempts += 1;
      if (attempts > maxAttempts) return reject(new Error("SDK Lab211 indisponible"));
      setTimeout(tick, delayMs);
    };
    tick();
  });
}

async function ensureInit(): Promise<Lab211AuthSdk> {
  const sdk = await waitForSdk();
  if (!initPromise) {
    initPromise = Promise.resolve(
      sdk.init({ siteKey: SITE_KEY, baseUrl: AUTH_API_BASE })
    ).then(() => undefined);
  }
  await initPromise;
  return sdk;
}

/** Monte le bouton SSO dans `el`. */
export async function mountLab211Button(el: HTMLElement): Promise<void> {
  try {
    const sdk = await ensureInit();
    el.replaceChildren();
    sdk.mountButton(el, {
      className: "lab211-auth-btn",
      loginLabel: "Connexion",
      logoutLabel: "Se déconnecter",
    });
  } catch {
    /* auth indisponible — le site reste utilisable en invité */
  }
}

/** Session courante via le SDK (cache 30 s côté SDK). */
export async function getLab211Session(force = false): Promise<Lab211Session> {
  try {
    const sdk = await ensureInit();
    if (sdk.getSession) {
      const s = await sdk.getSession({ force });
      return {
        authenticated: Boolean(s?.authenticated),
        user: (s?.user as Lab211User) ?? null,
      };
    }
    const user = sdk.getUser?.();
    return { authenticated: Boolean(user?.id), user: user ?? null };
  } catch {
    return { authenticated: false, user: null };
  }
}

/** Abonnement aux changements de session (connexion / déconnexion). */
export async function onLab211SessionChange(
  cb: (session: Lab211Session) => void
): Promise<() => void> {
  const sdk = await ensureInit();
  if (!sdk.onChange) return () => {};
  return sdk.onChange((payload: unknown) => {
    const p = payload as { authenticated?: boolean; user?: Lab211User | null };
    cb({
      authenticated: Boolean(p?.authenticated ?? p?.user),
      user: p?.user ?? null,
    });
  });
}
