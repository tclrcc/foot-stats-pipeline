# API de prédiction football

API REST (FastAPI) exposant le moteur Dixon-Coles / ELO.

## Lancement

```bash
pip install -r requirements.txt
python src/refresh_all.py        # génère les données + paramètres du modèle
python src/models/backtest.py    # (optionnel) alimente /model/performance
./run_api.sh                     # dev, ou ./run_api.sh prod sur le VPS
```

Doc interactive auto-générée : http://localhost:8000/docs

## Endpoints

| Méthode | Route | Description |
|---|---|---|
| GET | `/health` | État du service |
| GET | `/model/info` | Hyperparamètres du modèle (γ, ρ, ξ) |
| GET | `/model/performance` | Métriques de calibration (Brier, log-loss, ECE) |
| GET | `/teams` | Classement des équipes (ELO + attaque/défense) |
| GET | `/teams/{team}` | Détail d'une équipe + joueurs clés |
| GET | `/predict?home=X&away=Y&neutral=true` | Prédiction complète d'un match |
| GET | `/matches/upcoming` | Prochains matchs + prédictions |

## Exemple

```bash
curl "http://localhost:8000/predict?home=France&away=Brazil&neutral=true"
```

Renvoie xG, probabilités 1N2 / over-under / BTTS, et les scores les plus probables.
