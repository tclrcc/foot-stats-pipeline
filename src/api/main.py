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
import analysis
from schemas import (
    TeamRating, TeamDetail, Prediction, ModelInfo,
    ModelPerformance, UpcomingMatch, MatchDossier,
    ClubLeague, StandingRow, ClubResult, TopPlayer, ClubTeam,
)
import match_details
import player_details

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


@app.get("/match/dossier", response_model=MatchDossier, tags=["prediction"])
def get_match_dossier(
    home: str = Query(..., description="Équipe à domicile"),
    away: str = Query(..., description="Équipe à l'extérieur"),
    neutral: bool = Query(True, description="Terrain neutre"),
    date: str = Query(None, description="Date du match (YYYY-MM-DD) pour le contexte"),
):
    """
    Dossier d'avant-match complet : prédiction, forme récente, face-à-face,
    comparaison des forces, hommes clés et angles narratifs pour journalistes.
    """
    result = analysis.match_dossier(home, away, neutral, match_date=date)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Équipe(s) inconnue(s) du modèle : '{home}' ou '{away}'",
        )
    return result


# ─── Championnats club ───
@app.get("/clubs/leagues", response_model=List[ClubLeague], tags=["clubs"])
def get_club_leagues():
    """Championnats et saisons disponibles (table club_matches)."""
    return service.club_leagues()


@app.get("/clubs/standings", response_model=List[StandingRow], tags=["clubs"])
def get_club_standings(
    league: int = Query(..., description="ID de la ligue (61=Ligue 1, 39=PL...)"),
    season: int = Query(..., description="Saison (2025 = 2025-26)"),
):
    """Classement calculé depuis les résultats importés."""
    table = service.club_standings(league, season)
    if table is None:
        raise HTTPException(
            status_code=404,
            detail="Aucune donnée pour cette ligue/saison. Lance "
                   "'python src/sync_api_football.py results' d'abord.",
        )
    return table


@app.get("/clubs/results", response_model=List[ClubResult], tags=["clubs"])
def get_club_results(
    league: int = Query(...),
    season: int = Query(...),
    team: str = Query(None, description="Filtrer sur une équipe"),
    limit: int = Query(50, ge=1, le=400),
):
    """Derniers résultats de la ligue (ou d'une équipe), plus récents d'abord."""
    res = service.club_results(league, season, team=team, limit=limit)
    if res is None:
        raise HTTPException(status_code=404, detail="Table club_matches absente.")
    return res


@app.get("/clubs/topplayers", response_model=List[TopPlayer], tags=["clubs"])
def get_club_top_players(
    league: int = Query(...),
    season: int = Query(...),
    category: str = Query("scorers", pattern="^(scorers|assists|yellowcards|redcards)$"),
    limit: int = Query(10, ge=1, le=20),
):
    """Meilleurs buteurs ou passeurs de la ligue."""
    rows = service.club_top_players(league, season, category, limit)
    if rows is None:
        raise HTTPException(
            status_code=404,
            detail="Aucun classement joueurs pour cette ligue/saison. Lance "
                   "'python src/sync_api_football.py topplayers' d'abord.",
        )
    return rows


@app.get("/clubs/match/{fixture_id}", tags=["clubs"])
def get_club_match_detail(fixture_id: int):
    """
    Résumé d'un match : score, buteurs, cartons rouges, compositions.
    Servi depuis le cache local ; premier affichage = 1 requête API,
    puis cache définitif (un match terminé est immuable).
    """
    detail = match_details.get_match_detail(fixture_id)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail="Match introuvable (id inconnu de l'API, ou clé API absente du .env).",
        )
    return detail


@app.get("/clubs/player/{player_id}", tags=["clubs"])
def get_club_player(player_id: int, season: int = Query(2025, description="2025 = saison 2025-26")):
    """
    Fiche joueur complète : profil, stats par compétition, transferts,
    palmarès. Cache 7 jours (stats) / 30 jours (transferts, palmarès).
    """
    detail = player_details.get_player_detail(player_id, season)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail="Joueur introuvable pour cette saison (ou clé API absente du .env).",
        )
    return detail


@app.get("/clubs/players/search", tags=["clubs"])
def search_club_players(q: str = Query(..., min_length=3, description="Nom du joueur (≥ 3 caractères)")):
    """Recherche de joueurs par nom (cache 7 jours par terme)."""
    return player_details.search_players(q)


@app.get("/clubs/player/{player_id}/deep", tags=["clubs"])
def get_club_player_deep(
    player_id: int,
    season: int = Query(2025),
    team: str = Query(..., description="Nom d'équipe exact (API) de la saison analysée"),
    name: str = Query(None, description="Nom du joueur (pour compter ses passes décisives)"),
):
    """
    Analyse approfondie : buts par adversaire, domicile/extérieur, tranche
    de minutes. Premier lancement pour une équipe/saison : jusqu'à ~38
    requêtes (une par match non encore en cache) ; instantané ensuite,
    et le cache est partagé avec les résumés de match.
    """
    deep = player_details.get_player_deep(player_id, season, team, name=name)
    if deep is None:
        raise HTTPException(
            status_code=404,
            detail=f"Aucun match trouvé pour '{team}' sur la saison {season} dans club_matches.",
        )
    return deep


# ─── Modèle club (Dixon-Coles par championnat) ───
@app.get("/clubs/models", tags=["clubs"])
def get_club_models():
    """Championnats entraînés : avantage du terrain, corpus, dernier backtest."""
    return service.club_models_info()


@app.get("/clubs/teams", response_model=List[ClubTeam], tags=["clubs"])
def get_club_teams(league: int = Query(...)):
    """Équipes connues du modèle de la ligue (dernière saison en premier)."""
    teams = service.club_teams(league)
    if teams is None:
        raise HTTPException(
            status_code=404,
            detail="Ligue non entraînée. Lance "
                   "'python src/models/club_dixon_coles.py train --league <id>'.",
        )
    return teams


@app.get("/clubs/predict", response_model=Prediction, tags=["clubs"])
def get_club_predict(
    league: int = Query(..., description="61=Ligue 1, 39=PL, 140=Liga, 135=Serie A, 78=Bundesliga"),
    home: str = Query(...),
    away: str = Query(...),
):
    """Prédiction d'un match de club, avantage du terrain réel de la ligue."""
    pred = service.club_predict(league, home, away)
    if pred is None:
        raise HTTPException(
            status_code=404,
            detail=f"Ligue {league} non entraînée, ou équipe inconnue : '{home}' / '{away}'.",
        )
    return pred
