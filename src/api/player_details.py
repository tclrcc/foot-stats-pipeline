"""
Fiche joueur — chargement à la demande avec cache à durée de vie.

Contrairement aux matchs terminés (immuables), les stats d'un joueur sur la
saison en cours évoluent : le cache a donc un TTL.
  - Profil + stats saison (/players?id=&season=)   : TTL 7 jours
  - Transferts (/transfers?player=)                 : TTL 30 jours
  - Palmarès (/trophies?player=)                    : TTL 30 jours

Premier affichage d'un joueur = 3 requêtes, puis cache.
"""

import os
import sys
import json
import sqlite3

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(PROJECT_ROOT, "data/db/foot_stats.db")
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

TTL_STATS_DAYS = 7
TTL_EXTRA_DAYS = 30


def _connect():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def _ensure_tables():
    conn = _connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS player_details (
            player_id INTEGER, season INTEGER, raw_json TEXT,
            fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (player_id, season)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS player_extra (
            player_id INTEGER, kind TEXT, raw_json TEXT,
            fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (player_id, kind)
        )
    """)
    conn.commit()
    conn.close()


def _cached(conn, table, keys, ttl_days):
    where = " AND ".join(f"{k}=?" for k in keys)
    row = conn.execute(
        f"""SELECT raw_json FROM {table}
            WHERE {where} AND julianday('now') - julianday(fetched_at) < ?""",
        (*keys.values(), ttl_days),
    ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except Exception:
        return None


def _api_get(path, params):
    try:
        from sync_api_football import _get
    except ImportError:
        return None
    return _get(path, params)


def get_player_detail(player_id, season):
    """Fiche complète : profil, stats par compétition, transferts, palmarès."""
    _ensure_tables()
    conn = _connect()

    # ── Profil + stats saison ──
    raw = _cached(conn, "player_details", {"player_id": player_id, "season": season}, TTL_STATS_DAYS)
    if raw is None:
        resp = _api_get("/players", {"id": player_id, "season": season})
        raw = resp[0] if resp else None
        if raw is not None:
            conn.execute(
                "INSERT OR REPLACE INTO player_details (player_id, season, raw_json) VALUES (?,?,?)",
                (player_id, season, json.dumps(raw, ensure_ascii=False)),
            )
            conn.commit()
    if raw is None:
        conn.close()
        return None

    # ── Transferts & palmarès (best effort : la fiche vit sans eux) ──
    extras = {}
    for kind, path, params in (
        ("transfers", "/transfers", {"player": player_id}),
        ("trophies", "/trophies", {"player": player_id}),
        ("sidelined", "/sidelined", {"player": player_id}),
    ):
        data = _cached(conn, "player_extra", {"player_id": player_id, "kind": kind}, TTL_EXTRA_DAYS)
        if data is None:
            resp = _api_get(path, params)
            if resp is not None:
                data = resp
                conn.execute(
                    "INSERT OR REPLACE INTO player_extra (player_id, kind, raw_json) VALUES (?,?,?)",
                    (player_id, kind, json.dumps(data, ensure_ascii=False)),
                )
                conn.commit()
        extras[kind] = data or []
    conn.close()

    return _parse(raw, extras, season)


def _num(x):
    try:
        return float(x) if x is not None else None
    except (TypeError, ValueError):
        return None


def _parse(raw, extras, season):
    p = raw.get("player", {}) or {}
    birth = p.get("birth", {}) or {}

    stats_out = []
    current_team = None
    best_apps = -1
    for st in raw.get("statistics", []) or []:
        games = st.get("games", {}) or {}
        goals = st.get("goals", {}) or {}
        shots = st.get("shots", {}) or {}
        passes = st.get("passes", {}) or {}
        drb = st.get("dribbles", {}) or {}
        tkl = st.get("tackles", {}) or {}
        duels = st.get("duels", {}) or {}
        cards = st.get("cards", {}) or {}
        pen = st.get("penalty", {}) or {}
        apps = games.get("appearences") or 0
        team_name = (st.get("team") or {}).get("name")
        if apps > best_apps:
            best_apps, current_team = apps, team_name
        stats_out.append({
            "competition": (st.get("league") or {}).get("name"),
            "country": (st.get("league") or {}).get("country"),
            "team": team_name,
            "appearances": apps,
            "lineups": games.get("lineups"),
            "minutes": games.get("minutes"),
            "position": games.get("position"),
            "rating": round(_num(games.get("rating")), 2) if _num(games.get("rating")) else None,
            "captain": bool(games.get("captain")),
            "goals": goals.get("total") or 0,
            "assists": goals.get("assists") or 0,
            "shots": shots.get("total"),
            "shots_on": shots.get("on"),
            "key_passes": passes.get("key"),
            "pass_accuracy": passes.get("accuracy"),
            "dribbles_success": drb.get("success"),
            "dribbles_attempts": drb.get("attempts"),
            "tackles": tkl.get("total"),
            "duels_won": duels.get("won"),
            "duels_total": duels.get("total"),
            "yellow_cards": cards.get("yellow") or 0,
            "red_cards": (cards.get("red") or 0) + (cards.get("yellowred") or 0),
            "penalties_scored": pen.get("scored") or 0,
            "penalties_missed": pen.get("missed") or 0,
        })
    # Compétitions les plus jouées d'abord
    stats_out.sort(key=lambda s: -(s["appearances"] or 0))

    transfers_out = []
    for t in extras.get("transfers", []) or []:
        for tr in t.get("transfers", []) or []:
            transfers_out.append({
                "date": tr.get("date"),
                "type": tr.get("type"),
                "from_team": ((tr.get("teams") or {}).get("out") or {}).get("name"),
                "to_team": ((tr.get("teams") or {}).get("in") or {}).get("name"),
            })
    transfers_out.sort(key=lambda t: str(t.get("date") or ""), reverse=True)

    sidelined_out = []
    for sd in extras.get("sidelined", []) or []:
        sidelined_out.append({
            "type": sd.get("type"),
            "start": sd.get("start"),
            "end": sd.get("end"),
        })
    sidelined_out.sort(key=lambda x: str(x.get("start") or ""), reverse=True)

    trophies_out = []
    for tr in extras.get("trophies", []) or []:
        trophies_out.append({
            "league": tr.get("league"),
            "country": tr.get("country"),
            "season": tr.get("season"),
            "place": tr.get("place"),
        })

    return {
        "player_id": p.get("id"),
        "name": p.get("name"),
        "firstname": p.get("firstname"),
        "lastname": p.get("lastname"),
        "photo": p.get("photo"),
        "age": p.get("age"),
        "birth_date": birth.get("date"),
        "birth_place": birth.get("place"),
        "birth_country": birth.get("country"),
        "nationality": p.get("nationality"),
        "height": p.get("height"),
        "weight": p.get("weight"),
        "injured": bool(p.get("injured")),
        "current_team": current_team,
        "season": season,
        "stats": stats_out,
        "transfers": transfers_out[:12],
        "trophies": trophies_out[:15],
        "sidelined": sidelined_out[:8],
    }


# ─────────────────────────────────────────────────────────────────────────────
# RECHERCHE DE JOUEURS (/players/profiles?search=, cache 7 jours par terme)
# ─────────────────────────────────────────────────────────────────────────────
def search_players(query):
    """Recherche par nom (≥ 3 caractères). Renvoie une liste de profils légers."""
    q = (query or "").strip().lower()
    if len(q) < 3:
        return []
    _ensure_tables()
    conn = _connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS player_search (
            query TEXT PRIMARY KEY, raw_json TEXT,
            fetched_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    raw = _cached(conn, "player_search", {"query": q}, TTL_STATS_DAYS)
    if raw is None:
        resp = _api_get("/players/profiles", {"search": q})
        if resp is not None:
            raw = resp
            conn.execute(
                "INSERT OR REPLACE INTO player_search (query, raw_json) VALUES (?,?)",
                (q, json.dumps(raw, ensure_ascii=False)),
            )
            conn.commit()
    conn.close()
    out = []
    for item in raw or []:
        p = item.get("player", item) or {}
        birth = p.get("birth", {}) or {}
        out.append({
            "player_id": p.get("id"),
            "name": p.get("name"),
            "firstname": p.get("firstname"),
            "lastname": p.get("lastname"),
            "age": p.get("age"),
            "birth_date": birth.get("date"),
            "nationality": p.get("nationality"),
            "position": p.get("position"),
            "photo": p.get("photo"),
        })
    return [p for p in out if p["player_id"]][:25]


# ─────────────────────────────────────────────────────────────────────────────
# ANALYSE APPROFONDIE (agrégée depuis les événements des matchs de l'équipe)
# ─────────────────────────────────────────────────────────────────────────────
MINUTE_BUCKETS = [(0, 15), (16, 30), (31, 45), (46, 60), (61, 75), (76, 120)]


def get_player_deep(player_id, season, team, name=None):
    """
    Buts/passes par adversaire, domicile/extérieur, tranche de minutes.
    Construit depuis les événements des matchs de `team` sur la saison
    (table club_matches + cache club_match_details, complété via l'API
    au premier lancement — chaque match récupéré est caché à vie).
    """
    import match_details as md

    conn = _connect()
    rows = conn.execute("""
        SELECT fixture_id, home_team, away_team FROM club_matches
        WHERE season=? AND (home_team=? OR away_team=?)
        ORDER BY date ASC
    """, (season, team, team)).fetchall()
    conn.close()
    if not rows:
        return None

    by_opp = {}
    venue = {"home": 0, "away": 0}
    buckets = [0] * len(MINUTE_BUCKETS)
    goals_total = assists_total = penalties = matches_with_goal = 0
    analyzed = failed = 0

    for fid, home, away in rows:
        detail = md.get_match_detail(fid)
        if detail is None:
            failed += 1
            continue
        analyzed += 1
        team_side = "home" if home == team else "away"
        opponent = away if team_side == "home" else home
        opp = by_opp.setdefault(opponent, {"opponent": opponent, "goals": 0,
                                           "assists": 0, "matches": 0})
        opp["matches"] += 1
        scored_here = False
        for g in detail["events"]["goals"]:
            if g.get("side") != team_side:
                continue
            if g.get("player_id") == player_id and g.get("detail") != "Own Goal":
                opp["goals"] += 1
                goals_total += 1
                scored_here = True
                venue[team_side] += 1
                if g.get("detail") == "Penalty":
                    penalties += 1
                mn = g.get("minute")
                if mn is not None:
                    for i, (lo, hi) in enumerate(MINUTE_BUCKETS):
                        if lo <= mn <= hi:
                            buckets[i] += 1
                            break
            elif name and g.get("assist") and g["assist"] == name:
                opp["assists"] += 1
                assists_total += 1
        if scored_here:
            matches_with_goal += 1

    ranked = sorted(by_opp.values(), key=lambda o: (-o["goals"], -o["assists"], o["opponent"]))
    labels = ["0-15'", "16-30'", "31-45'+", "46-60'", "61-75'", "76-90'+"]
    return {
        "player_id": player_id,
        "team": team,
        "season": season,
        "analyzed_matches": analyzed,
        "missing_matches": failed,
        "goals_total": goals_total,
        "assists_total": assists_total,
        "penalties": penalties,
        "matches_with_goal": matches_with_goal,
        "venue": venue,
        "by_minute": [{"bucket": labels[i], "goals": buckets[i]} for i in range(len(labels))],
        "by_opponent": ranked,
    }
