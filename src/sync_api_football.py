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
FIXTURES_PATH = os.path.join(PROJECT_ROOT, "data/fixtures.json")

# Traduction des tours (l'API renvoie l'anglais)
ROUND_FR = {
    "Round of 32": "16es de finale",
    "Round of 16": "8es de finale",
    "Quarter-finals": "Quarts de finale",
    "Semi-finals": "Demi-finales",
    "3rd Place Final": "Match pour la 3e place",
    "Final": "Finale",
}

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
    _ensure_table()  # robustesse : fonctionne même si 'ratings' n'a jamais tourné
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


def cmd_fixtures(args):
    """
    Récupère les prochains matchs programmés de la ligue depuis l'API et
    remplit data/fixtures.json (noms traduits vers ceux du modèle).
    Remplace la saisie manuelle — à lancer 1 fois/jour (ou en cron).
    """
    from datetime import date, timedelta
    d_from = str(date.today())
    d_to = str(date.today() + timedelta(days=int(args.days)))
    resp = _get("/fixtures", {"league": args.league, "season": args.season,
                              "from": d_from, "to": d_to,
                              "timezone": args.timezone})
    if not resp:
        print("Aucun match renvoyé sur la fenêtre demandée.")
        return

    # API name → nom du modèle : via mapping puis normalisation
    mapping = _load_json(MAPPING_PATH, {})
    api_to_model = {_norm(v["api_name"]): k for k, v in mapping.items()}
    conn = sqlite3.connect(DB_PATH)
    model_names = {_norm(r[0]): r[0] for r in conn.execute("SELECT team FROM dc_team_params")}
    conn.close()

    def to_model(api_name):
        n = _norm(api_name)
        return api_to_model.get(n) or model_names.get(n)

    out, skipped = [], []
    for m in resp:
        status = (m.get("fixture", {}).get("status", {}) or {}).get("short", "")
        if status not in ("NS", "TBD"):   # uniquement les matchs pas encore joués
            continue
        h_api = m["teams"]["home"]["name"]
        a_api = m["teams"]["away"]["name"]
        h, a = to_model(h_api), to_model(a_api)
        if not h or not a:
            skipped.append(f"{h_api} vs {a_api}")
            continue
        raw_date = m["fixture"]["date"]            # ex. 2026-07-09T22:00:00+02:00
        date_str = raw_date[:16].replace("T", " ")
        rnd = (m.get("league", {}) or {}).get("round", "")
        out.append({"date": date_str, "home": h, "away": a,
                    "stage": ROUND_FR.get(rnd, rnd) or None})

    out.sort(key=lambda x: x["date"])
    doc = _load_json(FIXTURES_PATH, {})
    payload = {"_doc": doc.get("_doc", "Rempli par sync_api_football.py fixtures."),
               "fixtures": out}
    _save_json(FIXTURES_PATH, payload)
    print(f"💾 {len(out)} match(s) écrits dans {FIXTURES_PATH} (fenêtre {d_from} → {d_to}).")
    for f in out:
        print(f"   {f['date']}  {f['home']} vs {f['away']}  [{f.get('stage')}]")
    if skipped:
        print(f"⚠️  {len(skipped)} match(s) ignorés (équipes non mappées) : {', '.join(skipped[:5])}")
        print("   → complète data/team_mapping.json puis relance.")
    print("   Relance l'API du dossier : sudo systemctl restart footstats-api")


ABSENCES_PATH = os.path.join(PROJECT_ROOT, "data/absences.json")

# IDs API-Football des grands championnats (alias pratiques pour la CLI)
LEAGUE_ALIASES = {
    "pl": 39, "premierleague": 39,
    "liga": 140, "laliga": 140,
    "seriea": 135,
    "bundesliga": 78,
    "ligue1": 61,
    "cdm": 1, "worldcup": 1,
}
BIG5 = [39, 140, 135, 78, 61]
LEAGUE_NAMES = {39: "Premier League", 140: "La Liga", 135: "Serie A",
                78: "Bundesliga", 61: "Ligue 1", 1: "World Cup"}

# Statuts de match terminé (temps réglementaire, prolongation, tirs au but)
FINISHED = {"FT", "AET", "PEN"}

# Traduction légère des motifs d'absence les plus courants
REASON_FR = {
    "Suspended": "Suspendu", "Red Card": "Carton rouge",
    "Yellow Cards": "Accumulation de cartons", "Knee Injury": "Blessure au genou",
    "Ankle Injury": "Blessure à la cheville", "Muscle Injury": "Blessure musculaire",
    "Thigh Injury": "Blessure à la cuisse", "Hamstring Injury": "Ischio-jambiers",
    "Calf Injury": "Blessure au mollet", "Groin Injury": "Blessure à l'aine",
    "Illness": "Malade", "Shoulder Injury": "Blessure à l'épaule",
    "Back Injury": "Blessure au dos", "Broken ankle": "Cheville cassée",
}


def cmd_injuries(args):
    """
    Récupère blessés/suspendus pour les matchs de data/fixtures.json via
    /injuries, et écrit data/absences.json :
      - listes par équipe (format Niveau 4 → impact xG automatique)
      - "_detail" par équipe avec motifs (affichage dossier)
    Les noms API sont rapprochés de team_scorer_depth (accents/initiales)
    pour que l'impact offensif s'applique.
    """
    fx = _load_json(FIXTURES_PATH, {})
    fixtures = fx.get("fixtures", [])
    if not fixtures:
        print("⚠️  data/fixtures.json vide — lance d'abord la commande 'fixtures'.")
        return
    dates = sorted({f["date"][:10] for f in fixtures if f.get("date")})
    our_teams = {f["home"] for f in fixtures} | {f["away"] for f in fixtures}

    # API name → nom modèle
    mapping = _load_json(MAPPING_PATH, {})
    api_to_model = {_norm(v["api_name"]): k for k, v in mapping.items()}
    conn = sqlite3.connect(DB_PATH)
    model_names = {_norm(r[0]): r[0] for r in conn.execute("SELECT team FROM dc_team_params")}
    # Buteurs référencés (jointure des noms pour l'impact N4)
    depth = {}
    for team, scorer in conn.execute("SELECT team, scorer FROM team_scorer_depth"):
        depth.setdefault(team, []).append(scorer)
    conn.close()

    def to_model(api_name):
        n = _norm(api_name)
        return api_to_model.get(n) or model_names.get(n)

    def match_scorer(team, api_player):
        """Rapproche un nom API du nom exact de team_scorer_depth (nom de famille)."""
        cands = depth.get(team, [])
        n_api = _norm(api_player)
        for c in cands:
            if _norm(c) == n_api:
                return c
        last = n_api.split()[-1] if n_api.split() else ""
        hits = [c for c in cands if _norm(c).split()[-1] == last]
        return hits[0] if len(hits) == 1 else None

    absents, detail = {}, {}
    for d in dates:
        resp = _get("/injuries", {"league": args.league, "season": args.season, "date": d})
        for item in resp:
            t_model = to_model(item["team"]["name"])
            if not t_model or t_model not in our_teams:
                continue
            p_name = item["player"]["name"]
            reason = item["player"].get("reason") or ""
            typ = item["player"].get("type") or ""
            matched = match_scorer(t_model, p_name)
            store_name = matched or p_name
            if store_name not in absents.setdefault(t_model, []):
                absents[t_model].append(store_name)
                detail.setdefault(t_model, []).append({
                    "name": store_name,
                    "reason": REASON_FR.get(reason, reason),
                    "type": typ,
                    "impact_ready": bool(matched),
                })

    payload = {"_doc": "Rempli par sync_api_football.py injuries (forfaits par équipe, "
                       "format Niveau 4). _detail = motifs pour l'affichage du dossier."}
    payload.update(absents)
    payload["_detail"] = detail
    _save_json(ABSENCES_PATH, payload)
    n = sum(len(v) for v in absents.values())
    print(f"💾 {n} absent(s) écrits dans {ABSENCES_PATH} pour {len(absents)} équipe(s).")
    for t, players in absents.items():
        motifs = {p['name']: p['reason'] for p in detail.get(t, [])}
        print(f"   {t}: " + ", ".join(f"{p} ({motifs.get(p,'?')})" for p in players))
    if not absents:
        print("   (aucun forfait déclaré par l'API sur ces dates — normal si tôt dans la semaine)")


def cmd_results(args):
    """
    Importe l'historique des résultats de championnats club dans la table
    club_matches (base SQLite). C'est le corpus d'entraînement du futur
    modèle Dixon-Coles par ligue.

    Exemples :
      python src/sync_api_football.py results --leagues big5 --seasons 2021-2025
      python src/sync_api_football.py results --leagues ligue1 --seasons 2025
      python src/sync_api_football.py results --leagues 39,61 --seasons 2024,2025

    1 requête par (ligue, saison) — big5 × 5 saisons = 25 requêtes.
    Réimport sans risque : INSERT OR REPLACE par fixture_id.
    """
    # ── Parse des ligues ──
    leagues = []
    for tok in str(args.leagues).replace(" ", "").lower().split(","):
        if tok == "big5":
            leagues += BIG5
        elif tok in LEAGUE_ALIASES:
            leagues.append(LEAGUE_ALIASES[tok])
        elif tok.isdigit():
            leagues.append(int(tok))
        else:
            print(f"⚠️  Ligue inconnue : '{tok}' (alias : {', '.join(LEAGUE_ALIASES)}, big5, ou id numérique)")
    leagues = list(dict.fromkeys(leagues))
    if not leagues:
        return

    # ── Parse des saisons ("2021-2025" ou "2024,2025") ──
    seasons = []
    s = str(args.seasons).replace(" ", "")
    if "-" in s:
        a, b = s.split("-", 1)
        seasons = list(range(int(a), int(b) + 1))
    else:
        seasons = [int(x) for x in s.split(",") if x]

    # ── Table ──
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS club_matches (
            fixture_id INTEGER PRIMARY KEY,
            league_id INTEGER, league_name TEXT, season INTEGER,
            date TEXT, round TEXT,
            home_team TEXT, away_team TEXT,
            home_score INTEGER, away_score INTEGER,
            status TEXT
        )
    """)
    # Migration douce : ids d'équipes (jointure fiable malgré les renommages API)
    for col in ("home_id", "away_id"):
        try:
            conn.execute(f"ALTER TABLE club_matches ADD COLUMN {col} INTEGER")
        except sqlite3.OperationalError:
            pass

    total = 0
    for lg in leagues:
        lg_name = LEAGUE_NAMES.get(lg, str(lg))
        for season in seasons:
            # Filtre serveur des matchs terminés (doc officielle : status=FT-AET-PEN)
            resp = _get("/fixtures", {"league": lg, "season": season,
                                      "status": "-".join(sorted(FINISHED))})
            n = 0
            for m in resp:
                st = (m["fixture"].get("status", {}) or {}).get("short", "")
                if st not in FINISHED:
                    continue
                g = m.get("goals", {}) or {}
                hs, as_ = g.get("home"), g.get("away")
                if hs is None or as_ is None:
                    continue
                conn.execute("""INSERT OR REPLACE INTO club_matches
                    (fixture_id, league_id, league_name, season, date, round,
                     home_team, away_team, home_score, away_score, status,
                     home_id, away_id)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                    m["fixture"]["id"], lg, lg_name, season,
                    str(m["fixture"]["date"])[:10],
                    (m.get("league", {}) or {}).get("round", ""),
                    m["teams"]["home"]["name"], m["teams"]["away"]["name"],
                    int(hs), int(as_), st,
                    m["teams"]["home"].get("id"), m["teams"]["away"].get("id"),
                ))
                n += 1
            conn.commit()
            total += n
            print(f"   {lg_name} {season}-{str(season+1)[-2:]} : {n} matchs terminés importés")
            time.sleep(0.4)  # courtoisie quota/minute
    _harmonize_team_names(conn)
    conn.close()
    print(f"\n💾 {total} matchs dans club_matches (base {os.path.basename(DB_PATH)}).")
    print("   Vérifie : sqlite3 data/db/foot_stats.db \"SELECT league_name, season, COUNT(*) FROM club_matches GROUP BY 1,2;\"")


def _harmonize_team_names(conn):
    """
    L'API renomme parfois un club entre saisons (ex. 'Bayern Munich' →
    'Bayern München'), ce qui coupe son corpus en deux. Nom canonique
    par id d'équipe = le plus récent (tous côtés confondus), appliqué
    partout (home et away).
    """
    rows = conn.execute("""
        SELECT team_id, team FROM (
            SELECT home_id AS team_id, home_team AS team, date FROM club_matches
            WHERE home_id IS NOT NULL
            UNION ALL
            SELECT away_id, away_team, date FROM club_matches
            WHERE away_id IS NOT NULL
        ) ORDER BY date ASC
    """).fetchall()
    canonical = {}
    for tid, name in rows:  # trié par date croissante → le dernier vu gagne
        canonical[tid] = name

    fixed = 0
    for tid, name in canonical.items():
        for side in ("home", "away"):
            n = conn.execute(
                f"UPDATE club_matches SET {side}_team=? WHERE {side}_id=? AND {side}_team<>?",
                (name, tid, name)).rowcount
            if n:
                fixed += n
                print(f"   🔧 (id {tid}) → « {name} » : {n} ligne(s) {side} harmonisée(s)")
    conn.commit()
    if fixed:
        print(f"   ✅ {fixed} ligne(s) harmonisée(s) — relance l'entraînement du modèle.")


def cmd_topplayers(args):
    """
    Synchronise les classements de joueurs (buteurs + passeurs) par ligue
    et saison → table club_top_players. 2 requêtes par (ligue, saison).

      python src/sync_api_football.py topplayers --leagues big5 --seasons 2025
    """
    leagues = []
    for tok in str(args.leagues).replace(" ", "").lower().split(","):
        if tok == "big5":
            leagues += BIG5
        elif tok in LEAGUE_ALIASES:
            leagues.append(LEAGUE_ALIASES[tok])
        elif tok.isdigit():
            leagues.append(int(tok))
    leagues = list(dict.fromkeys(leagues))

    s = str(args.seasons).replace(" ", "")
    if "-" in s:
        a, b = s.split("-", 1)
        seasons = list(range(int(a), int(b) + 1))
    else:
        seasons = [int(x) for x in s.split(",") if x]

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS club_top_players (
            league_id INTEGER, season INTEGER, category TEXT, rank INTEGER,
            player_id INTEGER, player_name TEXT, team_name TEXT,
            appearances INTEGER, minutes INTEGER,
            goals INTEGER, assists INTEGER, penalties INTEGER, rating REAL,
            yellow_cards INTEGER, red_cards INTEGER,
            PRIMARY KEY (league_id, season, category, rank)
        )
    """)
    # Migration douce si la table existait sans les colonnes cartons
    for col in ("yellow_cards", "red_cards"):
        try:
            conn.execute(f"ALTER TABLE club_top_players ADD COLUMN {col} INTEGER")
        except sqlite3.OperationalError:
            pass

    endpoints = {"scorers": "/players/topscorers", "assists": "/players/topassists",
                 "yellowcards": "/players/topyellowcards", "redcards": "/players/topredcards"}
    for lg in leagues:
        lg_name = LEAGUE_NAMES.get(lg, str(lg))
        for season in seasons:
            for cat, path in endpoints.items():
                resp = _get(path, {"league": lg, "season": season})
                if not resp:
                    print(f"   {lg_name} {season} [{cat}] : aucune donnée")
                    continue
                conn.execute("DELETE FROM club_top_players WHERE league_id=? AND season=? AND category=?",
                             (lg, season, cat))
                for rank, item in enumerate(resp, 1):
                    p = item["player"]
                    st = (item.get("statistics") or [{}])[0]
                    games = st.get("games", {}) or {}
                    goals = st.get("goals", {}) or {}
                    pen = st.get("penalty", {}) or {}
                    try:
                        rating = float(games.get("rating")) if games.get("rating") else None
                    except (TypeError, ValueError):
                        rating = None
                    cards = st.get("cards", {}) or {}
                    conn.execute("""INSERT OR REPLACE INTO club_top_players
                        (league_id, season, category, rank, player_id, player_name,
                         team_name, appearances, minutes, goals, assists, penalties,
                         rating, yellow_cards, red_cards)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                        lg, season, cat, rank, p.get("id"), p.get("name"),
                        (st.get("team", {}) or {}).get("name"),
                        games.get("appearences"), games.get("minutes"),
                        goals.get("total") or 0, goals.get("assists") or 0,
                        pen.get("scored") or 0, rating,
                        cards.get("yellow") or 0, cards.get("red") or 0,
                    ))
                conn.commit()
                print(f"   {lg_name} {season} [{cat}] : {len(resp)} joueurs")
                time.sleep(0.4)
    conn.close()
    print("💾 club_top_players à jour.")


def cmd_upcoming(args):
    """
    Matchs à venir des championnats → table club_upcoming (remplacée par
    ligue à chaque exécution). 1 requête par ligue.

      python src/sync_api_football.py upcoming --leagues big5 --days 14
    """
    from datetime import date, timedelta
    leagues = []
    for tok in str(args.leagues).replace(" ", "").lower().split(","):
        if tok == "big5":
            leagues += BIG5
        elif tok in LEAGUE_ALIASES:
            leagues.append(LEAGUE_ALIASES[tok])
        elif tok.isdigit():
            leagues.append(int(tok))
    leagues = list(dict.fromkeys(leagues))

    d_from = date.today()
    d_to = date.today() + timedelta(days=int(args.days))

    # L'API exige 'season' avec league+from/to. Saison européenne déduite de
    # la date (juil-déc → année en cours, jan-juin → année précédente) ;
    # si la fenêtre chevauche deux saisons, on interroge les deux.
    def season_of(d):
        return d.year if d.month >= 7 else d.year - 1
    seasons = sorted({season_of(d_from), season_of(d_to)})

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS club_upcoming (
            fixture_id INTEGER PRIMARY KEY,
            league_id INTEGER, league_name TEXT, season INTEGER,
            date TEXT, round TEXT,
            home_team TEXT, away_team TEXT,
            home_id INTEGER, away_id INTEGER
        )
    """)
    total = 0
    for lg in leagues:
        lg_name = LEAGUE_NAMES.get(lg, str(lg))
        resp = []
        for season in seasons:
            resp += _get("/fixtures", {"league": lg, "season": season,
                                       "from": str(d_from), "to": str(d_to),
                                       "timezone": args.timezone})
        conn.execute("DELETE FROM club_upcoming WHERE league_id=?", (lg,))
        n = 0
        for m in resp:
            st = (m["fixture"].get("status", {}) or {}).get("short", "")
            if st not in ("NS", "TBD"):
                continue
            raw_date = m["fixture"]["date"]
            conn.execute("""INSERT OR REPLACE INTO club_upcoming
                VALUES (?,?,?,?,?,?,?,?,?,?)""", (
                m["fixture"]["id"], lg, lg_name,
                (m.get("league", {}) or {}).get("season"),
                raw_date[:16].replace("T", " "),
                (m.get("league", {}) or {}).get("round", ""),
                m["teams"]["home"]["name"], m["teams"]["away"]["name"],
                m["teams"]["home"].get("id"), m["teams"]["away"].get("id"),
            ))
            n += 1
        conn.commit()
        total += n
        print(f"   {lg_name} : {n} match(s) programmé(s) sur {d_from} → {d_to} "
              f"(saison{'s' if len(seasons)>1 else ''} {', '.join(map(str, seasons))})")
        time.sleep(0.3)
    conn.close()
    print(f"\n💾 {total} match(s) dans club_upcoming.")
    if total == 0:
        print("   (hors saison ? élargis la fenêtre : --days 45)")


def cmd_auto(args):
    """
    Pilote automatique d'avant-match (à mettre en cron toutes les 10 min).
    Pour chaque match de data/fixtures.json débutant dans moins de --window
    minutes : synchronise les forfaits puis tente la compo officielle à
    chaque passage jusqu'à publication. Ne consomme rien hors fenêtre.
    """
    from datetime import datetime
    from argparse import Namespace
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo(args.timezone))
    except Exception:
        now = datetime.now()

    fixtures = _load_json(FIXTURES_PATH, {}).get("fixtures", [])
    lineups = _load_json(LINEUPS_PATH, {})
    window = int(args.window)

    triggered = []
    for f in fixtures:
        try:
            dt = datetime.strptime(f["date"], "%Y-%m-%d %H:%M")
            if now.tzinfo is not None:
                dt = dt.replace(tzinfo=now.tzinfo)
        except Exception:
            continue
        delta_min = (dt - now).total_seconds() / 60
        if 0 <= delta_min <= window:
            triggered.append((f, delta_min))

    if not triggered:
        print(f"⏸  Aucun match dans les {window} prochaines minutes — rien à faire.")
        return

    print(f"🚦 {len(triggered)} match(s) imminent(s) — synchro forfaits + compos")
    cmd_injuries(Namespace(league=args.league, season=args.season))

    for f, dm in triggered:
        key = f"{f['home']} vs {f['away']}"
        entry = lineups.get(key) or {}
        if (entry.get("home") or {}).get("xi") and (entry.get("away") or {}).get("xi"):
            print(f"   ✅ {key} : compo déjà en place (H-{dm:.0f} min).")
            continue
        print(f"   📡 {key} (coup d'envoi dans {dm:.0f} min) — tentative compo...")
        cmd_lineup(Namespace(home=f["home"], away=f["away"], date=f["date"][:10],
                             fixture=None, league=args.league, season=args.season))


def cmd_club_lineup(args):
    """
    Compo officielle d'un match de club à venir (déjà dans club_upcoming,
    donc le fixture_id est connu — pas de recherche par date/nom).
    À lancer ~40 min avant le coup d'envoi (le pilote 'club_auto' s'en
    charge en cron).

      python src/sync_api_football.py club-lineup --fixture 123456
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS club_lineups (
        fixture_id INTEGER PRIMARY KEY, data_json TEXT,
        fetched_at TEXT DEFAULT CURRENT_TIMESTAMP)""")

    fid = args.fixture
    if not fid:
        row = conn.execute("""SELECT fixture_id FROM club_upcoming
            WHERE league_id=? AND home_team=? AND away_team=?""",
            (int(args.league), args.home, args.away)).fetchone()
        if not row:
            print("❌ Match introuvable dans club_upcoming (lance 'upcoming' d'abord).")
            conn.close()
            return
        fid = row[0]

    lineups = get_fixture_lineups(fid)
    if len(lineups) < 2:
        print(f"⚠️  Compositions pas encore publiées pour le match {fid}.")
        conn.close()
        return

    parsed = {}
    for side_key, lu in zip(("home", "away"), lineups):
        parsed[side_key] = {
            "team": lu["team"], "formation": lu["formation"],
            "xi": [{"id": p["id"], "name": p["name"], "pos": p["pos"]} for p in lu["xi"]],
        }
    conn.execute("INSERT OR REPLACE INTO club_lineups VALUES (?,?,CURRENT_TIMESTAMP)",
                 (fid, json.dumps(parsed, ensure_ascii=False)))
    conn.commit()
    conn.close()
    print(f"💾 Compo écrite pour le match {fid} : "
          f"{parsed['home']['team']} ({parsed['home']['formation']}) vs "
          f"{parsed['away']['team']} ({parsed['away']['formation']}).")


def cmd_club_injuries(args):
    """
    Forfaits (blessures/suspensions) des équipes ayant un match dans
    club_upcoming pour la ligue donnée, sur les --days prochains jours.
    Remplace entièrement les absences de la ligue à chaque exécution
    (les joueurs revenus de blessure disparaissent).

      python src/sync_api_football.py club-injuries --league 61 --days 3
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS club_absences (
        league_id INTEGER, team TEXT, player_name TEXT,
        reason TEXT, type TEXT, fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (league_id, team, player_name))""")

    lg = int(args.league)
    from datetime import date, timedelta
    horizon = str(date.today() + timedelta(days=int(args.days)))
    rows = conn.execute("""SELECT DISTINCT date, home_team, away_team FROM club_upcoming
        WHERE league_id=? AND date <= ?""", (lg, horizon)).fetchall()
    if not rows:
        print(f"⚠️  Aucun match à venir pour la ligue {lg} dans cette fenêtre.")
        conn.close()
        return

    teams = {t for _, h, a in rows for t in (h, a)}
    dates = sorted({d[:10] for d, _, _ in rows})

    conn.execute("DELETE FROM club_absences WHERE league_id=?", (lg,))
    n = 0
    for d in dates:
        resp = _get("/injuries", {"league": lg, "date": d})
        for item in resp:
            team = item["team"]["name"]
            if team not in teams:
                continue
            reason = item["player"].get("reason") or ""
            conn.execute("""INSERT OR REPLACE INTO club_absences VALUES
                (?,?,?,?,?,CURRENT_TIMESTAMP)""",
                (lg, team, item["player"]["name"],
                 REASON_FR.get(reason, reason), item["player"].get("type")))
            n += 1
        time.sleep(0.3)
    conn.commit()
    conn.close()
    print(f"💾 {n} absence(s) pour {len(teams)} équipe(s) (ligue {lg}, {len(dates)} date(s)).")


def cmd_club_auto(args):
    """
    Pilote automatique côté club (à mettre en cron toutes les 10-15 min) :
    pour chaque ligue entraînée présente dans club_upcoming, synchronise
    les forfaits (une fois, si un match approche sous --injuries-days) et
    tente la compo officielle de chaque match à moins de --window minutes
    du coup d'envoi (retente jusqu'à publication, ignore le reste).

      python src/sync_api_football.py club-auto --leagues big5
    """
    from datetime import datetime, date, timedelta
    from argparse import Namespace
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo(args.timezone))
    except Exception:
        now = datetime.now()

    leagues = []
    for tok in str(args.leagues).replace(" ", "").lower().split(","):
        if tok == "big5":
            leagues += BIG5
        elif tok in LEAGUE_ALIASES:
            leagues.append(LEAGUE_ALIASES[tok])
        elif tok.isdigit():
            leagues.append(int(tok))
    leagues = list(dict.fromkeys(leagues))
    window = int(args.window)
    inj_horizon = str(date.today() + timedelta(days=int(args.injuries_days)))

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS club_lineups (
        fixture_id INTEGER PRIMARY KEY, data_json TEXT,
        fetched_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    any_action = False

    for lg in leagues:
        rows = conn.execute("""SELECT fixture_id, date, home_team, away_team
            FROM club_upcoming WHERE league_id=? ORDER BY date""", (lg,)).fetchall()
        if not rows:
            continue
        if any(d <= inj_horizon for _, d, _, _ in rows):
            print(f"🩹 {LEAGUE_NAMES.get(lg, lg)} : synchro forfaits...")
            cmd_club_injuries(Namespace(league=str(lg), days=args.injuries_days))
            any_action = True

        for fid, d, h, a in rows:
            try:
                dt = datetime.strptime(d, "%Y-%m-%d %H:%M")
                if now.tzinfo is not None:
                    dt = dt.replace(tzinfo=now.tzinfo)
            except Exception:
                continue
            delta_min = (dt - now).total_seconds() / 60
            if not (0 <= delta_min <= window):
                continue
            has = conn.execute(
                "SELECT 1 FROM club_lineups WHERE fixture_id=?", (fid,)).fetchone()
            if has:
                print(f"   ✅ {h} vs {a} : compo déjà en place.")
                continue
            print(f"   📡 {h} vs {a} (H-{delta_min:.0f} min) — tentative compo...")
            cmd_club_lineup(Namespace(fixture=fid, league=str(lg), home=h, away=a))
            any_action = True
    conn.close()
    if not any_action:
        print("⏸  Rien à faire (aucun match imminent ni forfait à rafraîchir).")


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

    pf = sub.add_parser("fixtures")
    pf.add_argument("--league", default="1")
    pf.add_argument("--season", default="2026")
    pf.add_argument("--days", default="10", help="Fenêtre en jours (défaut 10)")
    pf.add_argument("--timezone", default="Europe/Paris")

    pi = sub.add_parser("injuries")
    pi.add_argument("--league", default="1")
    pi.add_argument("--season", default="2026")

    pt = sub.add_parser("topplayers")
    pt.add_argument("--leagues", default="big5")
    pt.add_argument("--seasons", default="2025")

    pa = sub.add_parser("auto")
    pa.add_argument("--league", default="1")
    pa.add_argument("--season", default="2026")
    pa.add_argument("--window", default="75", help="Fenêtre en minutes (défaut 75)")
    pa.add_argument("--timezone", default="Europe/Paris")

    pcl = sub.add_parser("club-lineup")
    pcl.add_argument("--fixture", type=int, default=None)
    pcl.add_argument("--league", default="61")
    pcl.add_argument("--home", default=None)
    pcl.add_argument("--away", default=None)

    pci = sub.add_parser("club-injuries")
    pci.add_argument("--league", required=True)
    pci.add_argument("--days", default="3")

    pca = sub.add_parser("club-auto")
    pca.add_argument("--leagues", default="big5")
    pca.add_argument("--window", default="75", help="Fenêtre compo en minutes (défaut 75)")
    pca.add_argument("--injuries-days", default="3", help="Fenêtre forfaits en jours (défaut 3)")
    pca.add_argument("--timezone", default="Europe/Paris")

    pu = sub.add_parser("upcoming")
    pu.add_argument("--leagues", default="big5")
    pu.add_argument("--days", default="14")
    pu.add_argument("--timezone", default="Europe/Paris")

    pr = sub.add_parser("results")
    pr.add_argument("--leagues", default="big5",
                    help="big5, alias (ligue1, pl, liga, seriea, bundesliga) ou ids séparés par des virgules")
    pr.add_argument("--seasons", default="2021-2025",
                    help="Plage '2021-2025' ou liste '2024,2025' (2025 = saison 2025-26)")

    pl = sub.add_parser("lineup")
    pl.add_argument("--home", required=True)
    pl.add_argument("--away", required=True)
    pl.add_argument("--date", help="YYYY-MM-DD (si pas de --fixture)")
    pl.add_argument("--fixture", help="Fixture ID direct (optionnel)")
    pl.add_argument("--league", default="1")
    pl.add_argument("--season", default="2026")

    args = parser.parse_args()
    {"map": cmd_map, "ratings": cmd_ratings, "lineup": cmd_lineup,
     "fixtures": cmd_fixtures, "injuries": cmd_injuries,
     "results": cmd_results, "topplayers": cmd_topplayers,
     "upcoming": cmd_upcoming, "auto": cmd_auto,
     "club-lineup": cmd_club_lineup, "club-injuries": cmd_club_injuries,
     "club-auto": cmd_club_auto}[args.cmd](args)


if __name__ == "__main__":
    main()
