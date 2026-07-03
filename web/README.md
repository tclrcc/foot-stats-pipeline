# Pitch — Frontend

Interface web (Next.js 14 + TypeScript + Tailwind) de la plateforme d'analyse
football. Next.js sert de *backend-for-frontend* : le navigateur parle à Next.js,
qui relaie vers l'API FastAPI en interne (pas de CORS, API non exposée).

## Prérequis

- Node.js 18+
- L'API FastAPI lancée (voir `src/api/`), accessible via `API_BASE`.

## Lancement

```bash
cd web
cp .env.example .env.local     # ajuste API_BASE si besoin (défaut http://localhost:8000)
npm install
npm run dev                    # dev sur http://localhost:3000
# ou
npm run build && npm start     # production
```

## Pages

- `/` — dashboard (hero, métriques de performance, top classement)
- `/predict` — simulateur interactif : xG, 1N2, over/under, BTTS, heatmap des scores
- `/teams` — classement ELO + attaque/défense
- `/model` — transparence : diagramme de fiabilité, Brier, log-loss, ECE

## Architecture

```
navigateur ──HTTP──> Next.js (SSR + /api proxy) ──HTTP──> FastAPI ──> moteur Dixon-Coles
```

Le client API typé est dans `lib/api.ts` (types miroir des schémas Pydantic).
