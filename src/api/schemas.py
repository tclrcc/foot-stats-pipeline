"""Schémas Pydantic — contrats d'entrée/sortie de l'API."""

from typing import List, Optional
from pydantic import BaseModel, Field


class TeamRating(BaseModel):
    team: str
    elo: Optional[float] = Field(None, description="Note ELO dynamique")
    attack: Optional[float] = Field(None, description="Paramètre d'attaque α (Dixon-Coles)")
    defense: Optional[float] = Field(None, description="Paramètre de défense β (plus bas = meilleur)")
    elo_rank: Optional[int] = None


class KeyPlayer(BaseModel):
    name: str
    goals: int
    dependency_pct: float


class TeamDetail(TeamRating):
    key_players: List[KeyPlayer] = []


class MarketProbabilities(BaseModel):
    home_win: float
    draw: float
    away_win: float
    over_1_5: float
    over_2_5: float
    under_2_5: float
    btts_yes: float
    btts_no: float


class ScoreLine(BaseModel):
    score: str
    probability: float


class Prediction(BaseModel):
    home_team: str
    away_team: str
    neutral: bool
    xg_home: float = Field(..., description="Buts attendus équipe à domicile (λ)")
    xg_away: float = Field(..., description="Buts attendus équipe à l'extérieur (μ)")
    markets: MarketProbabilities
    top_scorelines: List[ScoreLine]
    method: str = "dixon_coles"


class ModelInfo(BaseModel):
    gamma: float = Field(..., description="Avantage du terrain")
    rho: float = Field(..., description="Correction Dixon-Coles")
    xi_per_day: float = Field(..., description="Décroissance temporelle / jour")
    history_window_days: int
    n_teams: int


class ModelPerformance(BaseModel):
    available: bool
    run_date: Optional[str] = None
    brier: Optional[float] = None
    log_loss: Optional[float] = None
    accuracy: Optional[float] = None
    ece: Optional[float] = Field(None, description="Erreur de calibration attendue")
    message: Optional[str] = None


class UpcomingMatch(BaseModel):
    date: str
    home_team: str
    away_team: str
    prediction: Optional[Prediction] = None


# ─── Dossier de match ───
class FormMatch(BaseModel):
    date: str
    opponent: str
    score: str
    result: str
    competition: str
    venue: str


class TeamForm(BaseModel):
    matches: List[FormMatch]
    summary: dict
    streaks: dict


class H2HMatch(BaseModel):
    date: str
    home: str
    away: str
    score: str
    competition: str


class HeadToHead(BaseModel):
    played: int
    home_wins: int
    draws: int
    away_wins: int
    home_goals: int
    away_goals: int
    recent: List[H2HMatch]
    last_meeting: Optional[H2HMatch] = None


class MatchFixture(BaseModel):
    home_team: str
    away_team: str
    neutral: bool
    date: Optional[str] = None
    stage: str
    is_knockout: bool
    host_playing: Optional[str] = None


class MatchDossier(BaseModel):
    fixture: MatchFixture
    prediction: Prediction
    strength: dict
    form: dict
    head_to_head: HeadToHead
    key_players: dict
    storylines: List[str]
