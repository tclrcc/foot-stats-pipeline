"""
API FastAPI — expose le moteur de prédiction football.

Lancement (dev) :
    uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

Doc interactive : http://localhost:8000/docs
"""

import os
import sys
from typing import List
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import service
from schemas import (
    TeamRating, TeamDetail, Prediction, ModelInfo,
    ModelPerformance, UpcomingMatch,
)

app = FastAPI(
    title="Football Prediction API",
    description=(
        "Moteur de prédiction de matchs de football basé sur un modèle "
        "Dixon-Coles estimé par maximum de vraisemblance, avec ELO dynamique "
        "et calibration walk-forward. Fournit probabilités de résultats, "
        "distributions de scores et notes de force d'équipe."
    ),
    version="1.0.0",
)

# CORS : autorise le frontend React à appeler l'API.
# En production, restreindre allow_origins à ton domaine.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
@app.get("/", tags=["meta"])
def root():
    return {
        "name": "Football Prediction API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": [
            "/health", "/model/info", "/model/performance",
            "/teams", "/teams/{team}", "/predict", "/matches/upcoming",
        ],
    }


@app.get("/health", tags=["meta"])
def health():
    try:
        info = service.model_info()
        return {"status": "ok", "teams_loaded": info["n_teams"]}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Modèle indisponible : {e}")


@app.get("/model/info", response_model=ModelInfo, tags=["model"])
def get_model_info():
    return service.model_info()


@app.get("/model/performance", response_model=ModelPerformance, tags=["model"])
def get_model_performance():
    """Métriques de calibration issues du backtest walk-forward."""
    return service.model_performance()


# ─────────────────────────────────────────────────────────────────────────────
@app.get("/teams", response_model=List[TeamRating], tags=["teams"])
def get_teams():
    """Classement de toutes les équipes prédictibles (ELO + attaque/défense)."""
    return service.list_teams()


@app.get("/teams/{team}", response_model=TeamDetail, tags=["teams"])
def get_team_detail(team: str):
    result = service.get_team(team)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Équipe inconnue : '{team}'")
    return result


# ─────────────────────────────────────────────────────────────────────────────
@app.get("/predict", response_model=Prediction, tags=["prediction"])
def get_prediction(
    home: str = Query(..., description="Équipe à domicile"),
    away: str = Query(..., description="Équipe à l'extérieur"),
    neutral: bool = Query(True, description="Terrain neutre (pas d'avantage domicile)"),
):
    """Prédiction complète : xG, 1N2, over/under, BTTS, scores probables."""
    result = service.predict(home, away, neutral)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Équipe(s) inconnue(s) du modèle : '{home}' ou '{away}'",
        )
    return result


@app.get("/matches/upcoming", response_model=List[UpcomingMatch], tags=["prediction"])
def get_upcoming(
    limit: int = Query(20, ge=1, le=100),
    with_prediction: bool = Query(True),
):
    """Prochains matchs programmés, avec leur prédiction."""
    return service.upcoming_matches(limit, with_prediction)
