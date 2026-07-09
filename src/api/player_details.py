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
    }
