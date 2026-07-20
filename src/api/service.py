"""
Couche service : accès aux données + logique de prédiction.

Réutilise le moteur Dixon-Coles existant (src/models/dixon_coles.py). Aucune
dépendance au CLI predict_upcoming — l'API est autonome et agnostique au sport
(prête pour la Ligue 1 comme pour la CDM).
"""

import os
import json
import sqlite3
import pandas as pd
from functools import lru_cache

# Import du moteur existant
import sys
MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
sys.path.insert(0, MODELS_DIR)
import dixon_coles as dc

SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SRC_DIR)
from sync_api_football import is_cup_competition, league_display_name

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(PROJECT_ROOT, "data/db/foot_stats.db")


def _connect():
    # check_same_thread=False : FastAPI peut servir depuis plusieurs threads
    return sqlite3.connect(DB_PATH, check_same_thread=False)


# ─────────────────────────────────────────────────────────────────────────────
# Paramètres du modèle (mis en cache — rechargés au redémarrage du serveur)
# ─────────────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def get_model_params():
    """Renvoie (team_params_df, global_dict). Cache en mémoire."""
    team_params, glob = dc.load_params()
    return team_params, glob


def clear_cache():
    get_model_params.cache_clear()


# ─────────────────────────────────────────────────────────────────────────────
# Équipes & notes
# ─────────────────────────────────────────────────────────────────────────────
def list_teams():
    """Toutes les équipes prédictibles (celles ayant des paramètres DC), avec ELO."""
    conn = _connect()
    cur = conn.cursor()
    rows = cur.execute("""
        SELECT p.team, p.alpha, p.beta, e.elo_rating
        FROM dc_team_params p
        LEFT JOIN team_elo e ON e.team = p.team
        ORDER BY e.elo_rating DESC NULLS LAST
    """).fetchall()
    conn.close()

    # Rang ELO
    ranked = sorted(
        [r for r in rows if r[3] is not None],
        key=lambda r: r[3], reverse=True
    )
    rank_by_team = {r[0]: i + 1 for i, r in enumerate(ranked)}

    return [
        {
            "team": r[0],
            "attack": round(r[1], 3),
            "defense": round(r[2], 3),
            "elo": round(r[3], 1) if r[3] is not None else None,
            "elo_rank": rank_by_team.get(r[0]),
        }
        for r in rows
    ]


def get_team(team_name):
    """Détail d'une équipe : notes + joueurs clés. None si inconnue."""
    conn = _connect()
    cur = conn.cursor()
    row = cur.execute("""
        SELECT p.team, p.alpha, p.beta, e.elo_rating
        FROM dc_team_params p
        LEFT JOIN team_elo e ON e.team = p.team
        WHERE p.team = ?
    """, (team_name,)).fetchone()

    if not row:
        conn.close()
        return None

    players = cur.execute("""
        SELECT scorer, goals, dependency_pct
        FROM team_scorer_depth
        WHERE team = ?
        ORDER BY rank ASC
        LIMIT 8
    """, (team_name,)).fetchall()
    conn.close()

    # Rang ELO global
    teams = list_teams()
    rank = next((t["elo_rank"] for t in teams if t["team"] == team_name), None)

    return {
        "team": row[0],
        "attack": round(row[1], 3),
        "defense": round(row[2], 3),
        "elo": round(row[3], 1) if row[3] is not None else None,
        "elo_rank": rank,
        "key_players": [
            {"name": p[0], "goals": int(p[1]), "dependency_pct": round(p[2], 1)}
            for p in players
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Prédiction d'un match
# ─────────────────────────────────────────────────────────────────────────────
def predict(home, away, neutral=True, lam_mult=1.0, mu_mult=1.0):
    """
    Prédiction complète pour un match. None si équipe inconnue.
    lam_mult / mu_mult : multiplicateurs appliqués aux xG (compo, contexte…).
    """
    team_params, glob = get_model_params()
    gamma = glob.get("gamma", 1.3)
    rho = glob.get("rho", -0.1)

    lam, mu = dc.predict_lambdas(home, away, neutral, team_params, gamma)
    if lam is None:
        return None

    lam *= lam_mult
    mu  *= mu_mult

    probs = dc.market_probabilities(lam, mu, rho)

    # Top scorelines depuis la matrice
    mat = dc.score_matrix(lam, mu, rho, max_goals=8)
    scores = [
        (f"{i}-{j}", float(mat[i, j]))
        for i in range(mat.shape[0]) for j in range(mat.shape[1])
    ]
    top = sorted(scores, key=lambda x: x[1], reverse=True)[:5]

    return {
        "home_team": home,
        "away_team": away,
        "neutral": neutral,
        "xg_home": round(lam, 3),
        "xg_away": round(mu, 3),
        "markets": {
            "home_win": round(probs["home"] * 100, 1),
            "draw": round(probs["draw"] * 100, 1),
            "away_win": round(probs["away"] * 100, 1),
            "over_1_5": round(probs["over_1_5"] * 100, 1),
            "over_2_5": round(probs["over_2_5"] * 100, 1),
            "under_2_5": round(probs["under_2_5"] * 100, 1),
            "btts_yes": round(probs["btts_yes"] * 100, 1),
            "btts_no": round(probs["btts_no"] * 100, 1),
        },
        "top_scorelines": [
            {"score": s, "probability": round(p * 100, 1)} for s, p in top
        ],
        "method": "dixon_coles" if (lam_mult == 1.0 and mu_mult == 1.0) else "dixon_coles+compo",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Infos & performance du modèle
# ─────────────────────────────────────────────────────────────────────────────
def model_info():
    _, glob = get_model_params()
    conn = _connect()
    n = conn.execute("SELECT COUNT(*) FROM dc_team_params").fetchone()[0]
    conn.close()
    return {
        "gamma": round(float(glob.get("gamma", 0)), 4),
        "rho": round(float(glob.get("rho", 0)), 4),
        "xi_per_day": float(glob.get("xi_per_day", 0)),
        "history_window_days": int(glob.get("history_window_days", 0)),
        "n_teams": n,
    }


def model_performance():
    conn = _connect()
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")]
    if "backtest_log" not in tables:
        conn.close()
        return {"available": False,
                "message": "Backtest non lancé. Exécute : python src/models/backtest.py"}
    row = None
    try:
        row = conn.execute("""
            SELECT run_date, brier, log_loss, accuracy, ece, brier_baseline
            FROM backtest_log ORDER BY run_date DESC LIMIT 1
        """).fetchone()
    except Exception:
        row = conn.execute("""
            SELECT run_date, brier, log_loss, accuracy, ece, NULL
            FROM backtest_log ORDER BY run_date DESC LIMIT 1
        """).fetchone()
    conn.close()
    if not row:
        return {"available": False, "message": "Aucun résultat de backtest."}
    gain = None
    if row[5]:
        gain = round((row[5] - row[1]) / row[5] * 100, 1)
    return {
        "available": True,
        "run_date": row[0],
        "brier": round(row[1], 4),
        "log_loss": round(row[2], 4),
        "accuracy": round(row[3] * 100, 1),
        "ece": round(row[4] * 100, 2),
        "gain_vs_baseline_pct": gain,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Matchs à venir (CDM 2026 — sera généralisable à d'autres compétitions)
# ─────────────────────────────────────────────────────────────────────────────
def upcoming_matches(limit=20, with_prediction=True):
    """
    Matchs à venir : fusionne les matchs 'scheduled' de cdm_2026 (issus de
    l'API worldcup26.ir) avec un fichier manuel data/fixtures.json.

    Le fichier manuel garantit que le tableau (ex. 8es de finale) reste
    disponible même quand l'API planning est indisponible. Format :
      [{"date": "2026-07-04 19:00", "home": "Canada", "away": "Morocco",
        "stage": "Round of 16"}, ...]
    """
    seen = set()
    fixtures = []

    # 1) cdm_2026 (scheduled)
    conn = _connect()
    try:
        rows = conn.execute("""
            SELECT date, home_team, away_team
            FROM cdm_2026 WHERE match_status = 'scheduled'
            ORDER BY date ASC
        """).fetchall()
    except Exception:
        rows = []
    conn.close()
    for date, home, away in rows:
        key = (str(date)[:10], home, away)
        if key in seen:
            continue
        seen.add(key)
        fixtures.append({"date": date, "home_team": home, "away_team": away, "stage": None})

    # 2) fixtures.json (manuel) — complète / garantit le tableau
    import json
    fpath = os.path.join(PROJECT_ROOT, "data/fixtures.json")
    if os.path.exists(fpath):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                raw = json.load(f)
            entries = raw if isinstance(raw, list) else raw.get("fixtures", [])
            for e in entries:
                home, away = e.get("home"), e.get("away")
                date = e.get("date", "")
                if not home or not away:
                    continue
                key = (str(date)[:10], home, away)
                if key in seen:
                    continue
                seen.add(key)
                fixtures.append({"date": date, "home_team": home,
                                 "away_team": away, "stage": e.get("stage")})
        except Exception:
            pass

    # Tri chronologique
    fixtures.sort(key=lambda x: str(x["date"]))
    fixtures = fixtures[:limit]

    out = []
    for fx in fixtures:
        pred = predict(fx["home_team"], fx["away_team"], neutral=True) if with_prediction else None
        out.append({"date": str(fx["date"]), "home_team": fx["home_team"],
                    "away_team": fx["away_team"], "stage": fx.get("stage"),
                    "prediction": pred})
    return out


# ─────────────────────────────────────────────────────────────────────────────
# CHAMPIONNATS CLUB (table club_matches, alimentée par sync_api_football results)
# ─────────────────────────────────────────────────────────────────────────────
def _club_table_exists(conn):
    r = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='club_matches'"
    ).fetchone()
    return r is not None


def club_leagues():
    """Ligues et saisons disponibles dans club_matches, avec volumes."""
    conn = _connect()
    if not _club_table_exists(conn):
        conn.close()
        return []
    rows = conn.execute("""
        SELECT league_id, league_name, season, COUNT(*)
        FROM club_matches GROUP BY league_id, season
        ORDER BY league_name, season DESC
    """).fetchall()
    conn.close()
    out = {}
    for lid, lname, season, n in rows:
        e = out.setdefault(lid, {"league_id": lid, "league_name": lname, "seasons": [],
                                 "type": "cup" if is_cup_competition(lid) else "league"})
        e["seasons"].append({"season": season, "matches": n})
    return list(out.values())


def club_standings(league_id, season):
    """
    Classement calculé depuis les résultats : Pts (3/1/0), diff, buts,
    forme sur les 5 derniers matchs. Départage simplifié points > diff >
    buts marqués (les règles officielles varient selon les championnats).
    """
    conn = _connect()
    if not _club_table_exists(conn):
        conn.close()
        return None
    rows = conn.execute("""
        SELECT date, home_team, away_team, home_score, away_score
        FROM club_matches WHERE league_id=? AND season=? AND date <= date('now')
        ORDER BY date ASC
    """, (league_id, season)).fetchall()
    conn.close()
    if not rows:
        return None

    t = {}
    def team(name):
        return t.setdefault(name, {"team": name, "played": 0, "won": 0, "drawn": 0,
                                   "lost": 0, "gf": 0, "ga": 0, "points": 0, "form": []})
    for date, h, a, hs, as_ in rows:
        th, ta = team(h), team(a)
        th["played"] += 1; ta["played"] += 1
        th["gf"] += hs; th["ga"] += as_
        ta["gf"] += as_; ta["ga"] += hs
        if hs > as_:
            th["won"] += 1; th["points"] += 3; ta["lost"] += 1
            th["form"].append("V"); ta["form"].append("D")
        elif hs < as_:
            ta["won"] += 1; ta["points"] += 3; th["lost"] += 1
            ta["form"].append("V"); th["form"].append("D")
        else:
            th["drawn"] += 1; ta["drawn"] += 1
            th["points"] += 1; ta["points"] += 1
            th["form"].append("N"); ta["form"].append("N")

    table = []
    for e in t.values():
        e["gd"] = e["gf"] - e["ga"]
        e["form"] = e["form"][-5:]
        table.append(e)
    table.sort(key=lambda e: (-e["points"], -e["gd"], -e["gf"], e["team"]))
    for i, e in enumerate(table, 1):
        e["rank"] = i
    return table


def club_results(league_id, season, team=None, limit=50):
    """Derniers résultats (les plus récents d'abord), filtrables par équipe."""
    conn = _connect()
    if not _club_table_exists(conn):
        conn.close()
        return None
    q = """SELECT fixture_id, date, round, home_team, away_team, home_score, away_score
           FROM club_matches WHERE league_id=? AND season=?"""
    params = [league_id, season]
    if team:
        q += " AND (home_team=? OR away_team=?)"
        params += [team, team]
    q += " ORDER BY date DESC, fixture_id DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    out = []
    for fid, date, rnd, h, a, hs, as_ in rows:
        j = None
        if rnd and "- " in rnd:
            tail = rnd.rsplit("- ", 1)[-1].strip()
            j = f"J{tail}" if tail.isdigit() else rnd
        out.append({"fixture_id": fid, "date": date, "round": j or rnd,
                    "home_team": h, "away_team": a,
                    "home_score": hs, "away_score": as_})
    return out


def club_top_players(league_id, season, category="scorers", limit=10):
    """Classement des buteurs ou passeurs (table club_top_players)."""
    conn = _connect()
    try:
        rows = conn.execute("""
            SELECT rank, player_name, team_name, appearances, minutes,
                   goals, assists, penalties, rating, yellow_cards, red_cards,
                   player_id
            FROM club_top_players
            WHERE league_id=? AND season=? AND category=?
            ORDER BY rank ASC LIMIT ?
        """, (league_id, season, category, limit)).fetchall()
    except Exception:
        conn.close()
        return None
    conn.close()
    if not rows:
        return None
    return [{"rank": r[0], "player": r[1], "team": r[2], "appearances": r[3],
             "minutes": r[4], "goals": r[5], "assists": r[6],
             "penalties": r[7], "rating": r[8],
             "yellow_cards": r[9], "red_cards": r[10],
             "player_id": r[11]} for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# MODÈLE CLUB (Dixon-Coles par championnat — tables club_dc_*)
# ─────────────────────────────────────────────────────────────────────────────
_CLUB_PARAMS_CACHE = {}


def get_club_params(league_id):
    """Params entraînés d'une ligue (cache mémoire par ligue). None si non entraînée."""
    if league_id not in _CLUB_PARAMS_CACHE:
        import club_dixon_coles as cdc
        _CLUB_PARAMS_CACHE[league_id] = cdc.load_league_params(league_id)
    return _CLUB_PARAMS_CACHE[league_id]


def clear_club_cache():
    _CLUB_PARAMS_CACHE.clear()


def club_predict(league_id, home, away, lam_mult=1.0, mu_mult=1.0):
    """Prédiction club — même format que predict() ; avantage du terrain réel."""
    loaded = get_club_params(league_id)
    if loaded is None:
        return None
    team_params, glob = loaded
    gamma, rho = glob["gamma"], glob["rho"]

    lam, mu = dc.predict_lambdas(home, away, False, team_params, gamma)
    if lam is None:
        return None
    lam *= lam_mult
    mu *= mu_mult

    def _is_estimated(team):
        try:
            v = team_params.loc[team, "source_league_id"]
            return v is not None and not pd.isna(v)
        except Exception:
            return False
    estimated = _is_estimated(home) or _is_estimated(away)

    probs = dc.market_probabilities(lam, mu, rho)
    mat = dc.score_matrix(lam, mu, rho, max_goals=8)
    scores = [(f"{i}-{j}", float(mat[i, j]))
              for i in range(mat.shape[0]) for j in range(mat.shape[1])]
    top = sorted(scores, key=lambda x: x[1], reverse=True)[:5]

    return {
        "home_team": home,
        "away_team": away,
        "neutral": False,
        "xg_home": round(lam, 3),
        "xg_away": round(mu, 3),
        "markets": {
            "home_win": round(probs["home"] * 100, 1),
            "draw": round(probs["draw"] * 100, 1),
            "away_win": round(probs["away"] * 100, 1),
            "over_1_5": round(probs["over_1_5"] * 100, 1),
            "over_2_5": round(probs["over_2_5"] * 100, 1),
            "under_2_5": round(probs["under_2_5"] * 100, 1),
            "btts_yes": round(probs["btts_yes"] * 100, 1),
            "btts_no": round(probs["btts_no"] * 100, 1),
        },
        "top_scorelines": [
            {"score": s, "probability": round(p * 100, 1)} for s, p in top
        ],
        "method": "dixon_coles_club" + ("+estimation" if estimated else ""),
    }


def club_teams(league_id):
    """
    Équipes connues du modèle de la ligue, celles de la dernière saison
    importée en premier (pertinence : promus/relégués).
    """
    loaded = get_club_params(league_id)
    if loaded is None:
        return None
    team_params, _ = loaded
    conn = _connect()
    last_season = conn.execute(
        "SELECT MAX(season) FROM club_matches WHERE league_id=?", (league_id,)
    ).fetchone()[0]
    current = {r[0] for r in conn.execute(
        "SELECT DISTINCT home_team FROM club_matches WHERE league_id=? AND season=?",
        (league_id, last_season))}
    conn.close()
    out = []
    for team, row in team_params.iterrows():
        out.append({"team": team, "attack": round(float(row["alpha"]), 3),
                    "defense": round(float(row["beta"]), 3),
                    "in_current_season": team in current})
    out.sort(key=lambda t: (not t["in_current_season"], -t["attack"]))
    return out


def club_models_info():
    """Ligues entraînées : params globaux + dernier backtest. Liste (peut être vide)."""
    conn = _connect()
    try:
        globs = conn.execute("""
            SELECT g.league_id, g.gamma, g.rho, g.n_matches, g.trained_at
            FROM club_dc_global g ORDER BY g.league_id
        """).fetchall()
    except Exception:
        conn.close()
        return []
    names = dict(conn.execute(
        "SELECT DISTINCT league_id, league_name FROM club_matches").fetchall())
    out = []
    for lid, gamma, rho, n, trained in globs:
        bt = None
        try:
            row = conn.execute("""
                SELECT test_season, n_matches, accuracy, brier, brier_baseline, ece
                FROM club_backtest WHERE league_id=?
                ORDER BY test_season DESC LIMIT 1""", (lid,)).fetchone()
            if row:
                bt = {"test_season": row[0], "n_matches": row[1],
                      "accuracy": round(row[2], 4), "brier": round(row[3], 4),
                      "brier_baseline": round(row[4], 4),
                      "gain_vs_baseline_pct": round((row[4] - row[3]) / row[4] * 100, 1),
                      "ece": round(row[5], 4) if row[5] is not None else None}
        except Exception:
            pass
        out.append({"league_id": lid, "league_name": names.get(lid, str(lid)),
                    "gamma": round(gamma, 3), "rho": round(rho, 3),
                    "n_matches": n, "trained_at": trained, "backtest": bt})
    conn.close()
    return out


def club_upcoming(league_id=None, limit=30):
    """
    Matchs à venir (table club_upcoming, remplie par la commande
    'upcoming'), avec la prédiction du modèle de la ligue attachée quand
    les deux équipes sont connues (None sinon — ex. promu inconnu).
    """
    conn = _connect()
    try:
        q = """SELECT fixture_id, league_id, league_name, season, date, round,
                      home_team, away_team
               FROM club_upcoming"""
        params = []
        if league_id is not None:
            q += " WHERE league_id=?"
            params.append(league_id)
        q += " ORDER BY date ASC LIMIT ?"
        params.append(limit)
        rows = conn.execute(q, params).fetchall()
    except Exception:
        conn.close()
        return []
    conn.close()

    out = []
    for fid, lid, lname, season, date, rnd, home, away in rows:
        j = None
        if rnd and "- " in rnd:
            tail = rnd.rsplit("- ", 1)[-1].strip()
            j = f"J{tail}" if tail.isdigit() else rnd
        pred = club_predict(lid, home, away)
        out.append({
            "fixture_id": fid, "league_id": lid, "league_name": lname,
            "season": season, "date": date, "round": j or rnd,
            "home_team": home, "away_team": away,
            "prediction": pred,
        })
    return out


def _club_storylines(home, away, pred, standings, form, h2h, h2h_balance):
    """
    Synthèse narrative du dossier club — même esprit que generate_storylines
    côté sélections (analysis.py), reconstruite depuis les données déjà
    calculées par club_dossier (aucune source supplémentaire). Pas de
    'hommes clés' ici : aucune table de profondeur d'effectif club n'existe
    pour calculer une dépendance par buteur fiable (contrairement aux
    sélections) — volontairement absent plutôt qu'inventé.
    """
    s = []

    # Écart au classement
    snap_h, snap_a = standings.get("home"), standings.get("away")
    if snap_h and snap_a:
        gap = abs(snap_h["rank"] - snap_a["rank"])
        if gap >= 8:
            s.append(f"Gros écart au classement : {home} (#{snap_h['rank']}) "
                     f"reçoit {away} (#{snap_a['rank']}).")
        elif gap <= 2:
            s.append("Deux équipes proches au classement : match d'écurie serré sur le papier.")
        else:
            better = home if snap_h["rank"] < snap_a["rank"] else away
            s.append(f"Avantage au classement pour {better} (#{min(snap_h['rank'], snap_a['rank'])} "
                     f"contre #{max(snap_h['rank'], snap_a['rank'])}).")

    # Prédiction du modèle
    if pred:
        m = pred["markets"]
        top = max(("home", m["home_win"]), ("draw", m["draw"]), ("away", m["away_win"]), key=lambda x: x[1])
        label = {"home": home, "draw": "le nul", "away": away}[top[0]]
        s.append(f"Le modèle penche pour {label} ({top[1]:.0f}%). "
                 f"Score le plus probable : {pred['top_scorelines'][0]['score']}.")
        total_xg = pred["xg_home"] + pred["xg_away"]
        if total_xg > 3.1:
            s.append(f"Rencontre attendue ouverte : {total_xg:.1f} buts espérés au total.")
        elif total_xg < 2.2:
            s.append(f"Match attendu fermé : seulement {total_xg:.1f} buts espérés au total.")

    # Face-à-face
    if h2h:
        lm = h2h[0]
        s.append(f"Dernière confrontation : {lm['home_team']} {lm['home_score']}-{lm['away_score']} {lm['away_team']} "
                 f"({str(lm['date'])[:4]}).")
        played = len(h2h)
        if played >= 4:
            if h2h_balance["home_wins"] >= h2h_balance["away_wins"] * 2 and h2h_balance["home_wins"] >= 3:
                s.append(f"Ascendant psychologique pour {home} : {h2h_balance['home_wins']} victoires "
                         f"contre {h2h_balance['away_wins']} sur les {played} dernières confrontations.")
            elif h2h_balance["away_wins"] >= h2h_balance["home_wins"] * 2 and h2h_balance["away_wins"] >= 3:
                s.append(f"Ascendant psychologique pour {away} : {h2h_balance['away_wins']} victoires "
                         f"contre {h2h_balance['home_wins']} sur les {played} dernières confrontations.")
        best_margin = max(h2h, key=lambda m: abs(m["home_score"] - m["away_score"]))
        margin = abs(best_margin["home_score"] - best_margin["away_score"])
        if margin >= 4:
            s.append(f"Écart marqué lors d'une confrontation récente : {best_margin['home_team']} "
                     f"{best_margin['home_score']}-{best_margin['away_score']} {best_margin['away_team']} "
                     f"({str(best_margin['date'])[:4]}).")

    # Formes (séries en cours, calculées depuis les résultats les plus récents)
    for team, entries in ((home, form.get("home", [])), (away, form.get("away", []))):
        if not entries:
            continue
        results = [e["result"] for e in entries]  # plus récent en premier
        unbeaten = 0
        for r in results:
            if r in ("V", "N"):
                unbeaten += 1
            else:
                break
        winless = 0
        for r in results:
            if r != "V":
                winless += 1
            else:
                break
        scoring = 0
        for e in entries:
            gf = e["score"].split("-")[0] if e["venue"] == "home" else e["score"].split("-")[1]
            if int(gf) > 0:
                scoring += 1
            else:
                break
        if unbeaten >= 4:
            s.append(f"{team} reste sur {unbeaten} matchs sans défaite.")
        elif winless >= 3:
            s.append(f"{team} traverse une période délicate : {winless} matchs sans victoire.")
        if scoring >= 5:
            s.append(f"{team} a marqué lors de chacun de ses {scoring} derniers matchs.")

    return s


def club_dossier(league_id, home, away):
    """
    Dossier d'avant-match club : prédiction, physionomie, positions au
    classement, forme récente (5 derniers), confrontations directes.
    Tout est calculé depuis club_matches + le modèle de la ligue.
    """
    conn = _connect()
    try:
        latest = conn.execute(
            "SELECT MAX(season) FROM club_matches WHERE league_id=?",
            (league_id,)).fetchone()[0]
    except Exception:
        conn.close()
        return None
    if latest is None:
        conn.close()
        return None

    def known(team):
        return conn.execute(
            """SELECT 1 FROM club_matches
               WHERE league_id=? AND (home_team=? OR away_team=?) LIMIT 1""",
            (league_id, team, team)).fetchone() is not None

    if not known(home) or not known(away):
        conn.close()
        return None

    # ── Forme : 5 derniers matchs toutes saisons confondues ──
    def recent_form(team, n=5):
        rows = conn.execute("""
            SELECT date, home_team, away_team, home_score, away_score
            FROM club_matches
            WHERE league_id=? AND date <= date('now') AND (home_team=? OR away_team=?)
            ORDER BY date DESC LIMIT ?""",
            (league_id, team, team, n)).fetchall()
        out = []
        for date, h, a, hs, as_ in rows:
            at_home = (h == team)
            gf, ga = (hs, as_) if at_home else (as_, hs)
            res = "V" if gf > ga else ("N" if gf == ga else "D")
            out.append({"date": date, "opponent": a if at_home else h,
                        "venue": "home" if at_home else "away",
                        "score": f"{gf}-{ga}", "result": res})
        return out

    # ── Confrontations directes (les 6 dernières) ──
    h2h_rows = conn.execute("""
        SELECT date, season, home_team, away_team, home_score, away_score
        FROM club_matches
        WHERE league_id=? AND date <= date('now')
              AND ((home_team=? AND away_team=?) OR (home_team=? AND away_team=?))
        ORDER BY date DESC LIMIT 6""",
        (league_id, home, away, away, home)).fetchall()

    form_home = recent_form(home)
    form_away = recent_form(away)
    lname = conn.execute(
        "SELECT league_name FROM club_matches WHERE league_id=? LIMIT 1",
        (league_id,)).fetchone()
    conn.close()

    h2h = [{"date": d, "season": se, "home_team": h, "away_team": a,
            "home_score": hs, "away_score": as_}
           for d, se, h, a, hs, as_ in h2h_rows]
    balance = {"home_wins": 0, "draws": 0, "away_wins": 0}
    for m in h2h:
        winner = None if m["home_score"] == m["away_score"] else \
            (m["home_team"] if m["home_score"] > m["away_score"] else m["away_team"])
        if winner is None:
            balance["draws"] += 1
        elif winner == home:
            balance["home_wins"] += 1
        else:
            balance["away_wins"] += 1

    # ── Positions au classement (dernière saison) — non pertinent en cup ──
    is_cup = is_cup_competition(league_id)
    standings_note = None
    if is_cup:
        table = []
        standings_note = ("Classement non calculé : compétition à phases mixtes "
                          "(groupes + élimination directe) — un tableau de points "
                          "n'a pas de sens pour ce format.")
    else:
        table = club_standings(league_id, latest) or []

    def snap(team):
        for r in table:
            if r["team"] == team:
                return {"rank": r["rank"], "points": r["points"],
                        "played": r["played"], "gd": r["gd"], "form": r["form"]}
        return None

    # ── Prédiction + physionomie ──
    pred = club_predict(league_id, home, away)
    physio = None
    if pred:
        total = pred["xg_home"] + pred["xg_away"]
        diff = abs(pred["xg_home"] - pred["xg_away"])
        if total < 2.2:
            profile = "Match fermé attendu"
        elif total > 3.1:
            profile = "Match ouvert attendu"
        else:
            profile = "Rythme équilibré attendu"
        if diff >= 0.8:
            fav = home if pred["xg_home"] > pred["xg_away"] else away
            profile += f", ascendant net pour {fav}"
        physio = {"total_xg": round(total, 2), "profile": profile}

    # ── Compo officielle + infirmerie (seulement si match à venir connu) ──
    fixture_id, kickoff = None, None
    lineups, absences = None, None
    conn3 = _connect()
    try:
        up = conn3.execute("""SELECT fixture_id, date FROM club_upcoming
            WHERE league_id=? AND home_team=? AND away_team=?
            ORDER BY date LIMIT 1""", (league_id, home, away)).fetchone()
    except Exception:
        up = None
    if up:
        fixture_id, kickoff = up
        try:
            row = conn3.execute(
                "SELECT data_json FROM club_lineups WHERE fixture_id=?",
                (fixture_id,)).fetchone()
            if row:
                lineups = json.loads(row[0])
        except Exception:
            lineups = None
        try:
            abs_rows = conn3.execute("""SELECT team, player_name, reason
                FROM club_absences WHERE league_id=? AND team IN (?,?)""",
                (league_id, home, away)).fetchall()
            absences = {"home": [], "away": []}
            for team, player, reason in abs_rows:
                side = "home" if team == home else "away"
                absences[side].append({"name": player, "reason": reason})
        except Exception:
            absences = None
    conn3.close()

    standings_out = {"home": snap(home), "away": snap(away)}
    return {
        "league_id": league_id,
        "league_name": lname[0] if lname else str(league_id),
        "season": latest,
        "home_team": home,
        "away_team": away,
        "fixture_id": fixture_id,
        "kickoff": kickoff,
        "prediction": pred,
        "physionomie": physio,
        "standings": standings_out,
        "standings_note": standings_note,
        "form": {"home": form_home, "away": form_away},
        "h2h": h2h,
        "h2h_balance": balance,
        "storylines": _club_storylines(
            home, away, pred, standings_out,
            {"home": form_home, "away": form_away}, h2h, balance),
        "lineups": lineups,
        "absences": absences,
    }
