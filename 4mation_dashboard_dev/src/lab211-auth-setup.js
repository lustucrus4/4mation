/**
 * Intégration SSO Lab211 — bouton Connexion / nom du compte.
 */

const AUTH_API_BASE = import.meta.env.VITE_LAB211_AUTH_API_BASE || "https://auth.lab211.fr";
const SITE_KEY = "4mation";

function getSdk() {
  return window.Lab211Auth ?? null;
}

/**
 * Monte le bouton SSO dans `slotEl` (via SDK mountButton).
 * @param {HTMLElement | null} slotEl
 */
export function setupLab211Auth(slotEl) {
  if (!slotEl) return;

  let attempts = 0;

  const tryMount = () => {
    const sdk = getSdk();
    if (!sdk) {
      attempts += 1;
      if (attempts > 50) return;
      setTimeout(tryMount, 100);
      return;
    }

    sdk
      .init({ siteKey: SITE_KEY, baseUrl: AUTH_API_BASE })
      .then(() => {
        sdk.mountButton(slotEl, {
          className: "btn btn-ghost",
          loginLabel: "Connexion",
          logoutLabel: "Se déconnecter",
        });
      })
      .catch(() => {
        /* accès refusé ou auth indisponible — le jeu reste utilisable si sans_connexion */
      });
  };

  tryMount();
}
