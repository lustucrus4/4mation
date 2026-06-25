# Frontend 4mation (développement)

Interface web **React + TypeScript + Vite + Tailwind CSS v4**, refonte inspirée
de l'architecture chess.com (Jouer / Apprendre / Analyser / Profil), branchée au
SSO Lab211.

## Stack

- **React 19** + **React Router 7** (routing client)
- **TanStack Query** (état serveur) + **Zustand** (état jeu/UI)
- **Tailwind CSS v4** (design tokens repris de l'ADN visuel d'origine)
- **socket.io-client** (jeu en ligne temps réel, phases ultérieures)
- **Vite 8** (build, dev server, proxy API)

## Commandes

```bash
npm install
npm run dev      # http://localhost:5173 (proxy /api → http://127.0.0.1:5000)
npm run build    # sortie statique → ../4mation_dashboard_deploy
npm run preview  # prévisualiser le build
```

## Variables d'environnement (optionnelles)

| Variable | Rôle | Défaut |
|---|---|---|
| `VITE_API_URL` | Préfixe API en prod (ex. `https://api-4mation.lab211.fr`) | vide (proxy Vite) |
| `VITE_API_PROXY_TARGET` | Cible du proxy `/api` en dev | `http://127.0.0.1:5000` |
| `VITE_LAB211_AUTH_API_BASE` | Base du service SSO Lab211 | `https://auth.lab211.fr` |

## Structure

```
src/
  main.tsx              Point d'entrée React
  App.tsx               Routes (AppShell + pages)
  index.css             Tailwind v4 + design tokens (@theme)
  lib/
    api.ts              Client HTTP (entête X-Session-Id)
    lab211.ts           Intégration SSO Lab211
  components/
    layout/             AppShell, NavBar
    auth/               AuthButton (bouton SSO)
    ui/                 Button, Card
    game/               Board (plateau 7×7), WinBar (barre W/L)
  pages/                Home, Play, Learn, Analyze, Profile, NotFound
public/
  .htaccess             Routage SPA (Hostinger / Apache)
  favicon.svg
```

## Pages héritées

- `solver.html` (+ `src/solver.js`, `src/style.css`, `src/lab211-auth-setup.js`) :
  tableau de bord d'avancement du solveur, **conservé** comme entrée Vite séparée.

## Build & déploiement

Le build produit un site statique dans `../4mation_dashboard_deploy`, synchronisé
vers Hostinger. Le `.htaccess` redirige les routes client vers `index.html`
(en laissant passer `solver.html` et les assets réels).

> Refonte en cours — Phase 0 (fondations : socle React, design system, navigation,
> SSO). Les fonctionnalités (jeu vs bots, comptes, analyse, apprentissage, jeu en
> ligne) arrivent dans les phases suivantes.
