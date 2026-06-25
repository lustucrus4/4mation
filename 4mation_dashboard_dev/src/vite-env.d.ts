/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_API_PROXY_TARGET?: string;
  readonly VITE_LAB211_AUTH_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

/** SDK SSO Lab211 chargé via <script src="https://auth.lab211.fr/sdk/lab211-auth.js"> */
interface Lab211AuthSdk {
  init(opts: { siteKey: string; baseUrl?: string }): Promise<unknown>;
  mountButton(
    el: HTMLElement,
    opts?: { className?: string; loginLabel?: string; logoutLabel?: string }
  ): void;
  getSession?(opts?: { force?: boolean }): Promise<{
    authenticated?: boolean;
    user?: Lab211User | null;
  }>;
  getUser?: () => Lab211User | null;
  onChange?: (cb: (payload: unknown) => void) => () => void;
}

interface Lab211User {
  id?: string;
  username?: string;
  name?: string;
  email?: string;
  display_name?: string;
}

interface Window {
  Lab211Auth?: Lab211AuthSdk;
}
