// Client API typé — appelé côté serveur Next.js (BFF).
// Le navigateur ne parle jamais directement à FastAPI : Next.js relaie.

const API_BASE = process.env.API_BASE || "http://localhost:8000";

// ─── Types (miroir des schémas Pydantic de l'API) ───
export interface TeamRating {
  team: string;
  elo: number | null;
  attack: number | null;
  defense: number | null;
  elo_rank: number | null;
}

export interface KeyPlayer {
  name: string;
  goals: number;
  dependency_pct: number;
}

export interface TeamDetail extends TeamRating {
  key_players: KeyPlayer[];
}

export interface MarketProbabilities {
  home_win: number;
  draw: number;
  away_win: number;
  over_1_5: number;
  over_2_5: number;
  under_2_5: number;
  btts_yes: number;
  btts_no: number;
}

export interface ScoreLine {
  score: string;
  probability: number;
}

export interface Prediction {
  home_team: string;
  away_team: string;
  neutral: boolean;
  xg_home: number;
  xg_away: number;
  markets: MarketProbabilities;
  top_scorelines: ScoreLine[];
  method: string;
}

export interface ModelInfo {
  gamma: number;
  rho: number;
  xi_per_day: number;
  history_window_days: number;
  n_teams: number;
}

export interface ModelPerformance {
  available: boolean;
  run_date: string | null;
  brier: number | null;
  log_loss: number | null;
  accuracy: number | null;
  ece: number | null;
  message: string | null;
}

export interface FormMatch {
  date: string; opponent: string; score: string;
  result: string; competition: string; venue: string;
}
export interface TeamFormData {
  matches: FormMatch[];
  summary: { w: number; d: number; l: number; gf: number; ga: number };
  streaks: { unbeaten: number; winless: number; scoring: number; clean_sheets: number };
}
export interface H2HMatch {
  date: string; home: string; away: string; score: string; competition: string;
}
export interface HeadToHead {
  played: number; home_wins: number; draws: number; away_wins: number;
  home_goals: number; away_goals: number;
  recent: H2HMatch[]; last_meeting: H2HMatch | null;
}
export interface StrengthSide {
  elo: number | null; elo_rank: number | null;
  attack: number | null; defense: number | null;
}
export interface MatchDynamics {
  profile: string;
  openness: string;
  tempo: number;
  total_xg: number;
  scenarios: {
    tight: number; blowout: number;
    clean_sheet_home: number; clean_sheet_away: number;
    under_1_5: number; over_3_5: number;
    extra_time: number | null;
  };
  tactical_read: string[];
}
export interface CoachInfo {
  name: string;
  since?: string;
  context?: string;
  style?: string[];
  formation?: string;
  note?: string;
}
export interface MatchDossier {
  fixture: {
    home_team: string; away_team: string; neutral: boolean;
    date: string | null; stage: string; is_knockout: boolean;
    host_playing: string | null;
  };
  prediction: Prediction;
  dynamics: MatchDynamics | null;
  strength: { home: StrengthSide; away: StrengthSide; elo_gap: number | null; favorite: string | null };
  form: { home: TeamFormData; away: TeamFormData };
  head_to_head: HeadToHead;
  key_players: { home: KeyPlayer[]; away: KeyPlayer[] };
  coaches: { home: CoachInfo | null; away: CoachInfo | null } | null;
  storylines: string[];
}

export interface UpcomingMatch {
  date: string;
  home_team: string;
  away_team: string;
  stage: string | null;
  prediction: Prediction | null;
}

// ─── Helpers de fetch (revalidation ISR : 1h pour les données stables) ───
async function get<T>(path: string, revalidate = 3600): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${path} → ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  teams: () => get<TeamRating[]>("/teams"),
  team: (name: string) => get<TeamDetail>(`/teams/${encodeURIComponent(name)}`),
  modelInfo: () => get<ModelInfo>("/model/info"),
  modelPerformance: () => get<ModelPerformance>("/model/performance"),
  // Prédiction : pas de cache (paramétrable), utilisée par le proxy /api/predict
  predict: (home: string, away: string, neutral: boolean) =>
    get<Prediction>(
      `/predict?home=${encodeURIComponent(home)}&away=${encodeURIComponent(
        away
      )}&neutral=${neutral}`,
      0
    ),
  dossier: (home: string, away: string, neutral: boolean, date?: string) =>
    get<MatchDossier>(
      `/match/dossier?home=${encodeURIComponent(home)}&away=${encodeURIComponent(
        away
      )}&neutral=${neutral}${date ? `&date=${date}` : ""}`,
      0
    ),
  upcoming: (limit = 20) =>
    get<UpcomingMatch[]>(`/matches/upcoming?limit=${limit}&with_prediction=true`, 0),
};

export { API_BASE };
