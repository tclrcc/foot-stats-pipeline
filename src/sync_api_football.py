"""
Synchronisation API-Football → base + fichiers exploités par le dossier.

Pipeline (à lancer sur le VPS, où la clé et le réseau sont dispo) :

  1. python src/sync_api_football.py map     --league 1 --season 2026
        → data/team_mapping.json  (nom du modèle ↔ ID API-Football)

  2. python src/sync_api_football.py ratings --league 1 --season 2026
        → table api_player_ratings + data/team_refs.json (niveaux de référence)

  3. python src/sync_api_football.py lineup   --home Canada --away Morocco --date 2026-07-04 --league 1 --season 2026
        → écrit la compo (formation + XI + notes) dans data/lineups.json
          sous la clé "Canada vs Morocco" — le dossier la prend alors en compte.

Stratégie quota : tout est mis en cache localement. Une synchro des notes par
semaine + une compo par match suffisent → très loin des 7 500 req/jour du PRO.

Config : API_FOOTBALL_KEY dans .env.
"""

import os
import sys
import json
import time
import sqlite3
import argparse
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("API_FOOTBALL_KEY")
HEADERS = {"x-apisports-key": API_KEY}
BASE_URL = "https://v3.football.api-sports.io"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "data/db/foot_stats.db")
MAPPING_PATH = os.path.join(PROJECT_ROOT, "data/team_mapping.json")
REFS_PATH = os.path.join(PROJECT_ROOT, "data/team_refs.json")
LINEUPS_PATH = os.path.join(PROJECT_ROOT, "data/lineups.json")

# Normalisation des positions vers G/D/M/F
POS_MAP = {
    "Goalkeeper": "G", "Defender": "D", "Midfielder": "M", "Attacker": "F",
    "G": "G", "D": "D", "M": "M", "F": "F",
}
OFF_POS = {"M", "F"}
DEF_POS = {"G", "D"}


# ─────────────────────────────────────────────────────────────────────────────
# Client HTTP
# ─────────────────────────────────────────────────────────────────────────────
def _get(path, params, retries=2):
    """Appel GET robuste. Renvoie la liste 'response' ou [] en cas de souci."""
    if not API_KEY:
        print("❌ API_FOOTBALL_KEY absente du .env — impossible d'interroger l'API.")
        return []
    for attempt in range(retries + 1):
        try:
            r = requests.get(f"{BASE_URL}{path}", headers=HEADERS, params=params, timeout=25)
            data = r.json()
        except Exception as e:
            print(f"   ⚠️  Erreur réseau ({e}), tentative {attempt + 1}...")
            time.sleep(2)
            continue
        if data.get("errors"):
            print(f"   ❌ L'API a refusé la requête : {data['errors']}")
            return []
        # Quota par minute éventuel
        remaining = r.headers.get("x-ratelimit-requests-remaining")
        if remaining is not None:
            print(f"   ℹ️  Requêtes restantes aujourd'hui : {remaining}")
        return data.get("response", [])
    return []


# ─────────────────────────────────────────────────────────────────────────────
# Appels API
# ─────────────────────────────────────────────────────────────────────────────
def list_league_teams(league, season):
    resp = _get("/teams", {"league": league, "season": season})
    return [{"id": t["team"]["id"], "name": t["team"]["name"]} for t in resp]


def get_team_players(team_id, league, season, max_pages=3):
    """Stats joueurs d'une équipe (paginé). Renvoie [{id,name,pos,rating,goals}]."""
    out = []
    page = 1
    while page <= max_pages:
        resp = _get("/players", {"team": team_id, "league": league, "season": season, "page": page})
        if not resp:
            break
        for item in resp:
            pid = item["player"]["id"]
            name = item["player"]["name"]
            stats = (item.get("statistics") or [{}])[0]
            games = stats.get("games", {}) or {}
            goals = (stats.get("goals", {}) or {}).get("total") or 0
            rating = games.get("rating")
            pos = POS_MAP.get(games.get("position"), None)
            try:
                rating = float(rating) if rating is not None else None
            except (TypeError, ValueError):
                rating = None
            out.append({"id": pid, "name": name, "pos": pos, "rating": rating, "goals": goals})
        page += 1
        time.sleep(0.3)  # courtoisie quota/minute
    return out


def find_fixture_id(home, away, date, league, season):
    resp = _get("/fixtures", {"date": date, "league": league, "season": season})
    for m in resp:
        h = m["teams"]["home"]["name"]
        a = m["teams"]["away"]["name"]
        if (_norm(home) in _norm(h) or _norm(h) in _norm(home)) and \
           (_norm(away) in _norm(a) or _norm(a) in _norm(away)):
            return m["fixture"]["id"]
        # match inversé (domicile/extérieur peuvent différer du modèle)
        if (_norm(home) in _norm(a) or _norm(a) in _norm(home)) and \
           (_norm(away) in _norm(h) or _norm(h) in _norm(away)):
            return m["fixture"]["id"]
    return None


def get_fixture_lineups(fixture_id):
    """Renvoie [{team, formation, xi:[{id,name,pos}]}] pour les 2 équipes."""
    resp = _get("/fixtures/lineups", {"fixture": fixture_id})
    out = []
    for td in resp:
        xi = [{"id": p["player"].get("id"), "name": p["player"]["name"],
               "pos": POS_MAP.get(p["player"].get("pos"), p["player"].get("pos"))}
              for p in td.get("startXI", [])]
        out.append({"team": td["team"]["name"], "formation": td.get("formation"), "xi": xi})
    return out


def _norm(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return s.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Persistance
# ─────────────────────────────────────────────────────────────────────────────
def _ensure_table():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_player_ratings (
            api_id INTEGER, name TEXT, model_team TEXT, pos TEXT,
            rating REAL, goals INTEGER, season TEXT, league TEXT,
            PRIMARY KEY (api_id, season, league)
        )
    """)
    conn.commit()
    conn.close()


def _load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def _save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
# Commandes
# ─────────────────────────────────────────────────────────────────────────────
def cmd_map(args):
    """Construit data/team_mapping.json (nom modèle → id API)."""
    teams = list_league_teams(args.league, args.season)
    if not teams:
        print("Aucune équipe renvoyée. Vérifie league/season/clé.")
        return
    # Modèle = noms de la base (dc_team_params). On propose un mapping auto par nom.
    conn = sqlite3.connect(DB_PATH)
    model_names = [r[0] for r in conn.execute("SELECT team FROM dc_team_params")]
    conn.close()

    api_by_norm = {_norm(t["name"]): t for t in teams}
    mapping = _load_json(MAPPING_PATH, {})
    matched, unmatched = 0, []
    for mn in model_names:
        hit = api_by_norm.get(_norm(mn))
        if hit:
            mapping[mn] = {"api_id": hit["id"], "api_name": hit["name"]}
            matched += 1
    # équipes API non mappées (info)
    print(f"✅ {matched} équipes mappées automatiquement.")
    print(f"   {len(teams)} équipes dans la ligue {args.league}/{args.season}.")
    _save_json(MAPPING_PATH, mapping)
    print(f"💾 {MAPPING_PATH} écrit. Corrige à la main les noms qui diffèrent "
          f"(ex. 'United States' vs 'USA').")
    # Aide : liste des noms API pour correction manuelle
    print("   Noms API disponibles :", ", ".join(sorted(t["name"] for t in teams)))


def cmd_ratings(args):
    """Synchronise les notes joueurs de toutes les équipes mappées."""
    _ensure_table()
    mapping = _load_json(MAPPING_PATH, {})
    if not mapping:
        print("⚠️  Lance d'abord 'map'. Aucun mapping trouvé.")
        return
    conn = sqlite3.connect(DB_PATH)
    refs = {}
    for model_name, info in mapping.items():
        tid = info["api_id"]
        print(f"\n📡 {model_name} (API id {tid})...")
        players = get_team_players(tid, args.league, args.season)
        if not players:
            print("   (aucune stat — équipe sans matchs sur cette saison/ligue ?)")
            continue
        for p in players:
            conn.execute("""INSERT OR REPLACE INTO api_player_ratings
                VALUES (?,?,?,?,?,?,?,?)""",
                (p["id"], p["name"], model_name, p["pos"], p["rating"],
                 p["goals"], str(args.season), str(args.league)))
        refs[model_name] = _compute_refs(players)
        print(f"   ✅ {len(players)} joueurs — réf off {refs[model_name]['ref_off']}, "
              f"déf {refs[model_name]['ref_def']}")
    conn.commit()
    conn.close()
    _save_json(REFS_PATH, refs)
    print(f"\n💾 {REFS_PATH} écrit ({len(refs)} équipes).")


def _compute_refs(players):
    """Niveau de référence off/déf = moyenne des meilleures notes par ligne."""
    off = sorted([p["rating"] for p in players if p["rating"] and p["pos"] in OFF_POS], reverse=True)
    def_ = sorted([p["rating"] for p in players if p["rating"] and p["pos"] in DEF_POS], reverse=True)
    off_top = off[:6] or [6.8]
    def_top = def_[:5] or [6.8]
    return {"ref_off": round(sum(off_top) / len(off_top), 2),
            "ref_def": round(sum(def_top) / len(def_top), 2)}


def cmd_lineup(args):
    """Récupère la compo d'un match, joint les notes, écrit dans lineups.json."""
    fid = args.fixture or find_fixture_id(args.home, args.away, args.date, args.league, args.season)
    if not fid:
        print("❌ Match introuvable (compo publiée ~40 min avant, ou date/ligue erronée).")
        return
    print(f"✅ Fixture ID : {fid}")
    lineups = get_fixture_lineups(fid)
    if len(lineups) < 2:
        print("⚠️  Compositions pas encore publiées.")
        return

    # Notes par joueur (depuis la base) et refs par équipe
    conn = sqlite3.connect(DB_PATH)
    rating_by_id = dict(conn.execute(
        "SELECT api_id, rating FROM api_player_ratings WHERE season=? AND league=?",
        (str(args.season), str(args.league))))
    conn.close()
    refs = _load_json(REFS_PATH, {})

    # Associe chaque équipe API au nom du modèle (home/away fournis)
    def to_entry(api_team, model_name):
        xi = []
        for p in api_team["xi"]:
            r = rating_by_id.get(p["id"])
            entry = {"pos": p["pos"], "name": p["name"]}
            if r is not None:
                entry["rating"] = round(r, 2)
            xi.append(entry)
        team_ref = refs.get(model_name, {})
        out = {"team": model_name, "formation": api_team["formation"], "xi": xi}
        if team_ref:
            out["ref_off"] = team_ref["ref_off"]
            out["ref_def"] = team_ref["ref_def"]
        return out

    # Fait correspondre les 2 blocs API aux équipes home/away du modèle
    names = [lu["team"] for lu in lineups]
    home_api = _best_match(args.home, lineups)
    away_api = _best_match(args.away, lineups)
    if home_api is None or away_api is None or home_api is away_api:
        print(f"⚠️  Correspondance équipes ambiguë (API: {names}). Vérifie les noms.")
        return

    all_lineups = _load_json(LINEUPS_PATH, {})
    key = f"{args.home} vs {args.away}"
    all_lineups[key] = {"home": to_entry(home_api, args.home),
                        "away": to_entry(away_api, args.away)}
    _save_json(LINEUPS_PATH, all_lineups)
    n_rated_h = sum(1 for p in all_lineups[key]["home"]["xi"] if "rating" in p)
    n_rated_a = sum(1 for p in all_lineups[key]["away"]["xi"] if "rating" in p)
    print(f"💾 Compo écrite sous « {key} ».")
    print(f"   {args.home}: {all_lineups[key]['home']['formation']} "
          f"({n_rated_h}/11 notés) · {args.away}: {all_lineups[key]['away']['formation']} "
          f"({n_rated_a}/11 notés)")
    print("   Relance l'API du dossier (sudo systemctl restart footstats-api) et ouvre le match.")


def _best_match(model_name, lineups):
    for lu in lineups:
        if _norm(model_name) in _norm(lu["team"]) or _norm(lu["team"]) in _norm(model_name):
            return lu
    return None


# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Synchronisation API-Football")
    sub = parser.add_subparsers(dest="cmd", required=True)

    for name in ("map", "ratings"):
        p = sub.add_parser(name)
        p.add_argument("--league", default="1")
        p.add_argument("--season", default="2026")

    pl = sub.add_parser("lineup")
    pl.add_argument("--home", required=True)
    pl.add_argument("--away", required=True)
    pl.add_argument("--date", help="YYYY-MM-DD (si pas de --fixture)")
    pl.add_argument("--fixture", help="Fixture ID direct (optionnel)")
    pl.add_argument("--league", default="1")
    pl.add_argument("--season", default="2026")

    args = parser.parse_args()
    {"map": cmd_map, "ratings": cmd_ratings, "lineup": cmd_lineup}[args.cmd](args)


if __name__ == "__main__":
    main()
