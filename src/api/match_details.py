"""
Détail d'un match club (buteurs, cartons, compos) — chargement à la demande.

Pattern : au premier affichage d'un match, on appelle /fixtures?id= (une seule
requête, qui embarque events + lineups), on stocke le JSON brut dans la table
club_match_details, et toutes les consultations suivantes viennent du cache.
Un match terminé étant immuable, le cache est définitif. Coût total :
1 requête par match réellement consulté.
"""

import os
import sys
import json
import sqlite3

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(PROJECT_ROOT, "data/db/foot_stats.db")
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))


def _connect():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def _ensure_cache():
    conn = _connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS club_match_details (
            fixture_id INTEGER PRIMARY KEY,
            raw_json TEXT,
            fetched_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def _fetch_from_api(fixture_id):
    """Appelle /fixtures?id= (réutilise le client robuste du module de synchro)."""
    try:
        from sync_api_football import _get
    except ImportError:
        return None
    resp = _get("/fixtures", {"id": fixture_id})
    return resp[0] if resp else None


def get_match_detail(fixture_id):
    """
    Renvoie le détail parsé d'un match (ou None si introuvable).
    Cache d'abord ; sinon appel API puis mise en cache.
    """
    _ensure_cache()
    conn = _connect()
    row = conn.execute(
        "SELECT raw_json FROM club_match_details WHERE fixture_id=?", (fixture_id,)
    ).fetchone()
    raw = None
    if row:
        try:
            raw = json.loads(row[0])
        except Exception:
            raw = None
    if raw is None:
        raw = _fetch_from_api(fixture_id)
        if raw is not None:
            conn.execute(
                "INSERT OR REPLACE INTO club_match_details (fixture_id, raw_json) VALUES (?, ?)",
                (fixture_id, json.dumps(raw, ensure_ascii=False)),
            )
            conn.commit()
    conn.close()
    if raw is None:
        return None
    return _parse(raw)


# Statistiques d'équipe : sélection ordonnée + libellés français
STAT_LABELS = [
    ("Ball Possession", "Possession"),
    ("expected_goals", "xG (buts attendus)"),
    ("Total Shots", "Tirs"),
    ("Shots on Goal", "Tirs cadrés"),
    ("Corner Kicks", "Corners"),
    ("Fouls", "Fautes"),
    ("Offsides", "Hors-jeu"),
    ("Yellow Cards", "Cartons jaunes"),
    ("Red Cards", "Cartons rouges"),
    ("Goalkeeper Saves", "Arrêts du gardien"),
    ("Passes %", "Précision des passes"),
]


def _parse_statistics(m, home_name):
    """[{label, home, away}] depuis l'objet statistics embarqué (ou None)."""
    stats_raw = m.get("statistics") or []
    if len(stats_raw) != 2:
        return None
    by_side = {}
    for block in stats_raw:
        side = "home" if (block.get("team") or {}).get("name") == home_name else "away"
        by_side[side] = {s.get("type"): s.get("value")
                         for s in (block.get("statistics") or [])}
    out = []
    for api_key, label in STAT_LABELS:
        h = by_side.get("home", {}).get(api_key)
        a = by_side.get("away", {}).get(api_key)
        if h is None and a is None:
            continue
        out.append({"label": label,
                    "home": str(h) if h is not None else "0",
                    "away": str(a) if a is not None else "0"})
    return out or None


def _player_ratings(m):
    """Notes du match par joueur : {player_id: rating} + meilleur joueur."""
    ratings = {}
    best = None
    for block in m.get("players") or []:
        team_name = (block.get("team") or {}).get("name")
        for item in block.get("players") or []:
            p = item.get("player") or {}
            st = (item.get("statistics") or [{}])[0]
            r = (st.get("games") or {}).get("rating")
            try:
                r = float(r) if r is not None else None
            except (TypeError, ValueError):
                r = None
            if r is None:
                continue
            if p.get("id") is not None:
                ratings[p["id"]] = r
            if best is None or r > best["rating"]:
                best = {"name": p.get("name"), "team": team_name, "rating": r}
    return ratings, best


def _parse(m):
    """Réduit la réponse API au strict utile pour la page de résumé."""
    teams = m.get("teams", {})
    home_name = (teams.get("home") or {}).get("name")
    away_name = (teams.get("away") or {}).get("name")

    def side_of(team_obj):
        name = (team_obj or {}).get("name")
        if name == home_name:
            return "home"
        if name == away_name:
            return "away"
        return None

    fx = m.get("fixture", {}) or {}
    league = m.get("league", {}) or {}
    goals = m.get("goals", {}) or {}
    score = m.get("score", {}) or {}
    ht = score.get("halftime") or {}

    events_out = {"goals": [], "cards": []}
    for e in m.get("events", []) or []:
        t = e.get("time", {}) or {}
        minute = t.get("elapsed")
        extra = t.get("extra")
        base = {
            "minute": minute,
            "extra": extra,
            "side": side_of(e.get("team")),
            "player": (e.get("player") or {}).get("name"),
            "detail": e.get("detail"),
        }
        if e.get("type") == "Goal" and base["detail"] != "Missed Penalty":
            base["assist"] = (e.get("assist") or {}).get("name")
            events_out["goals"].append(base)
        elif e.get("type") == "Card" and base["detail"] == "Red Card":
            events_out["cards"].append(base)

    lineups_out = None
    lus = m.get("lineups", []) or []
    ratings, best_player = _player_ratings(m)
    if len(lus) == 2:
        def to_side(lu):
            return {
                "team": (lu.get("team") or {}).get("name"),
                "formation": lu.get("formation"),
                "coach": (lu.get("coach") or {}).get("name"),
                "xi": [
                    {
                        "name": (p.get("player") or {}).get("name"),
                        "number": (p.get("player") or {}).get("number"),
                        "pos": (p.get("player") or {}).get("pos"),
                        "rating": ratings.get((p.get("player") or {}).get("id")),
                    }
                    for p in lu.get("startXI", []) or []
                ],
            }
        a, b = lus
        if side_of(a.get("team")) == "away" or side_of(b.get("team")) == "home":
            a, b = b, a
        lineups_out = {"home": to_side(a), "away": to_side(b)}

    return {
        "fixture_id": fx.get("id"),
        "date": str(fx.get("date", ""))[:16].replace("T", " "),
        "venue": ((fx.get("venue") or {}).get("name")),
        "city": ((fx.get("venue") or {}).get("city")),
        "league_name": league.get("name"),
        "season": league.get("season"),
        "round": league.get("round"),
        "home_team": home_name,
        "away_team": away_name,
        "home_score": goals.get("home"),
        "away_score": goals.get("away"),
        "halftime": {"home": ht.get("home"), "away": ht.get("away")},
        "events": events_out,
        "lineups": lineups_out,
        "statistics": _parse_statistics(m, home_name),
        "best_player": best_player,
    }
