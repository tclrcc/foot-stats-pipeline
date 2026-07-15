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
  gain_vs_baseline_pct: number | null;
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
export interface LineupPlayer {
  pos: string;
  name?: string;
  rating?: number;
}
export interface MatchLineups {
  home: { formation?: string; xi: LineupPlayer[] };
  away: { formation?: string; xi: LineupPlayer[] };
}
export interface AbsentPlayer {
  name: string;
  reason: string | null;
  dependency_pct: number | null;
}
export interface MatchAbsences {
  home: AbsentPlayer[];
  away: AbsentPlayer[];
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
  lineups: MatchLineups | null;
  absences: MatchAbsences | null;
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

// ─── Championnats club ───
export interface ClubSeason { season: number; matches: number }
export interface ClubLeague { league_id: number; league_name: string; seasons: ClubSeason[]; type: "league" | "cup" }
export interface StandingRow {
  rank: number; team: string; played: number; won: number; drawn: number;
  lost: number; gf: number; ga: number; gd: number; points: number; form: string[];
}
export interface ClubResult {
  fixture_id: number | null;
  date: string; round: string | null;
  home_team: string; away_team: string; home_score: number; away_score: number;
}

export const clubs = {
  leagues: () => get<ClubLeague[]>("/clubs/leagues", 0),
  standings: (league: number, season: number) =>
    get<StandingRow[]>(`/clubs/standings?league=${league}&season=${season}`, 0),
  results: (league: number, season: number, team?: string, limit = 60) =>
    get<ClubResult[]>(
      `/clubs/results?league=${league}&season=${season}&limit=${limit}${team ? `&team=${encodeURIComponent(team)}` : ""}`,
      0
    ),
};

export interface TopPlayer {
  player_id: number | null;
  rank: number; player: string; team: string | null;
  appearances: number | null; minutes: number | null;
  goals: number; assists: number; penalties: number; rating: number | null;
  yellow_cards: number | null; red_cards: number | null;
}
export interface MatchGoal {
  minute: number | null; extra: number | null; side: "home" | "away" | null;
  player: string | null; player_id?: number | null; assist?: string | null; detail: string | null;
}
export interface MatchDetail {
  fixture_id: number; date: string; venue: string | null; city: string | null;
  league_name: string | null; season: number | null; round: string | null;
  home_team: string; away_team: string;
  home_score: number | null; away_score: number | null;
  halftime: { home: number | null; away: number | null };
  events: { goals: MatchGoal[]; cards: MatchGoal[] };
  lineups: {
    home: { team: string; formation: string | null; coach: string | null; xi: { id: number | null; name: string; number: number | null; pos: string | null; rating: number | null }[] };
    away: { team: string; formation: string | null; coach: string | null; xi: { id: number | null; name: string; number: number | null; pos: string | null; rating: number | null }[] };
  } | null;
  statistics: { label: string; home: string; away: string }[] | null;
  best_player: { name: string; team: string | null; rating: number } | null;
}

export const clubsExtra = {
  topplayers: (league: number, season: number, category: "scorers" | "assists" | "yellowcards" | "redcards", limit = 10) =>
    get<TopPlayer[]>(`/clubs/topplayers?league=${league}&season=${season}&category=${category}&limit=${limit}`, 0),
  matchDetail: (fixtureId: number) => get<MatchDetail>(`/clubs/match/${fixtureId}`, 0),
};


export interface PlayerCompStats {
  competition: string | null; country: string | null; team: string | null;
  appearances: number; lineups: number | null; minutes: number | null;
  position: string | null; rating: number | null; captain: boolean;
  goals: number; assists: number; shots: number | null; shots_on: number | null;
  key_passes: number | null; pass_accuracy: number | null;
  dribbles_success: number | null; dribbles_attempts: number | null;
  tackles: number | null; duels_won: number | null; duels_total: number | null;
  yellow_cards: number; red_cards: number;
  penalties_scored: number; penalties_missed: number;
}
export interface PlayerDetail {
  player_id: number; name: string; firstname: string | null; lastname: string | null;
  photo: string | null; age: number | null;
  birth_date: string | null; birth_place: string | null; birth_country: string | null;
  nationality: string | null; height: string | null; weight: string | null;
  injured: boolean; current_team: string | null; season: number;
  stats: PlayerCompStats[];
  transfers: { date: string | null; type: string | null; from_team: string | null; to_team: string | null }[];
  trophies: { league: string | null; country: string | null; season: string | null; place: string | null }[];
  sidelined: { type: string | null; start: string | null; end: string | null }[];
}

export interface PlayerSearchResult {
  player_id: number; name: string; firstname: string | null; lastname: string | null;
  age: number | null; birth_date: string | null; nationality: string | null;
  position: string | null; photo: string | null;
}
export interface PlayerDeep {
  player_id: number; team: string; season: number;
  analyzed_matches: number; missing_matches: number;
  goals_total: number; assists_total: number; penalties: number;
  matches_with_goal: number;
  venue: { home: number; away: number };
  by_minute: { bucket: string; goals: number }[];
  by_opponent: { opponent: string; goals: number; assists: number; matches: number }[];
}

export const players = {
  detail: (playerId: number, season: number) =>
    get<PlayerDetail>(`/clubs/player/${playerId}?season=${season}`, 0),
  search: (q: string) =>
    get<PlayerSearchResult[]>(`/clubs/players/search?q=${encodeURIComponent(q)}`, 0),
  deep: (playerId: number, season: number, team: string, name?: string) =>
    get<PlayerDeep>(
      `/clubs/player/${playerId}/deep?season=${season}&team=${encodeURIComponent(team)}${name ? `&name=${encodeURIComponent(name)}` : ""}`,
      0
    ),
};


// ─── Modèle club (Dixon-Coles par championnat) ───
export interface ClubModelBacktest {
  test_season: number; n_matches: number; accuracy: number;
  brier: number; brier_baseline: number; gain_vs_baseline_pct: number;
  ece: number | null;
}
export interface ClubModelInfo {
  league_id: number; league_name: string;
  gamma: number; rho: number; n_matches: number; trained_at: string;
  backtest: ClubModelBacktest | null;
}

export const clubModel = {
  models: () => get<ClubModelInfo[]>("/clubs/models", 0),
  teams: (league: number) => get<ClubTeam[]>(`/clubs/teams?league=${league}`, 0),
  predict: (league: number, home: string, away: string) =>
    get<Prediction>(
      `/clubs/predict?league=${league}&home=${encodeURIComponent(home)}&away=${encodeURIComponent(away)}`,
      0
    ),
};
export interface ClubTeam {
  team: string; attack: number; defense: number; in_current_season: boolean;
}


export interface ClubUpcomingMatch {
  fixture_id: number; league_id: number; league_name: string;
  season: number | null; date: string; round: string | null;
  home_team: string; away_team: string;
  prediction: Prediction | null;
}
export const clubUpcoming = {
  list: (league?: number, limit = 30) =>
    get<ClubUpcomingMatch[]>(
      `/clubs/upcoming?limit=${limit}${league ? `&league=${league}` : ""}`,
      0
    ),
};

// ─── Dossier d'avant-match club ───
export interface ClubFormEntry {
  date: string; opponent: string; venue: "home" | "away"; score: string; result: "V" | "N" | "D";
}
export interface ClubStandingSnap {
  rank: number; points: number; played: number; gd: number; form: string[];
}
export interface ClubDossier {
  league_id: number; league_name: string; season: number;
  home_team: string; away_team: string;
  fixture_id: number | null; kickoff: string | null;
  prediction: Prediction | null;
  physionomie: { total_xg: number; profile: string } | null;
  standings: { home: ClubStandingSnap | null; away: ClubStandingSnap | null };
  standings_note: string | null;
  form: { home: ClubFormEntry[]; away: ClubFormEntry[] };
  h2h: { date: string; season: number; home_team: string; away_team: string; home_score: number; away_score: number }[];
  h2h_balance: { home_wins: number; draws: number; away_wins: number };
  storylines: string[];
  lineups: {
    home: { team: string; formation: string | null; xi: { id: number | null; name: string; pos: string | null }[] };
    away: { team: string; formation: string | null; xi: { id: number | null; name: string; pos: string | null }[] };
  } | null;
  absences: {
    home: { name: string; reason: string | null }[];
    away: { name: string; reason: string | null }[];
  } | null;
}
export const clubDossier = {
  get: (league: number, home: string, away: string) =>
    get<ClubDossier>(
      `/clubs/dossier?league=${league}&home=${encodeURIComponent(home)}&away=${encodeURIComponent(away)}`,
      0
    ),
};
