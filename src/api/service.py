"""
Couche service : accès aux données + logique de prédiction.

Réutilise le moteur Dixon-Coles existant (src/models/dixon_coles.py). Aucune
dépendance au CLI predict_upcoming — l'API est autonome et agnostique au sport
(prête pour la Ligue 1 comme pour la CDM).
"""

import os
import sqlite3
from functools import lru_cache

# Import du moteur existant
import sys
MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
sys.path.insert(0, MODELS_DIR)
import dixon_coles as dc

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
    row = conn.execute("""
        SELECT run_date, brier, log_loss, accuracy, ece
        FROM backtest_log ORDER BY run_date DESC LIMIT 1
    """).fetchone()
    conn.close()
    if not row:
        return {"available": False, "message": "Aucun résultat de backtest."}
    return {
        "available": True,
        "run_date": row[0],
        "brier": round(row[1], 4),
        "log_loss": round(row[2], 4),
        "accuracy": round(row[3] * 100, 1),
        "ece": round(row[4] * 100, 2),
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
