"""
Écart modèle/marché pour les matchs de club — couche privée, CLI
uniquement (jamais d'endpoint API, jamais de page web, jamais de lien
dans la nav). Réutilise le moteur EV/Kelly existant (value_finder.py,
jusque-là orphelin) plutôt que d'en construire un second : mêmes seuils,
même méthode de retrait de marge, même format de sortie que côté
sélections.

  python src/models/club_value_finder.py scan --leagues big5

Prérequis : le modèle de la ligue doit être entraîné (club_dixon_coles.py
train) et les cotes capturées (sync_api_football.py club-odds) — cette
dernière étape ne peut pas être rattrapée après coup (rétention API de
7 jours, cf. sync_api_football.py).
"""
import os
import sys
import sqlite3
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import value_finder as vf

SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SRC_DIR)
sys.path.insert(0, os.path.join(SRC_DIR, "api"))
from sync_api_football import resolve_leagues, league_display_name
import service

PROJECT_ROOT = os.path.dirname(SRC_DIR)
DB_PATH = os.path.join(PROJECT_ROOT, "data/db/foot_stats.db")


def _connect():
    return sqlite3.connect(DB_PATH)


def _adapt_club_markets(pred):
    """
    club_predict() renvoie des pourcentages sous des clés propres au
    club (home_win/away_win) ; value_finder attend des fractions [0,1]
    sous les clés qu'il partage avec le moteur sélections (home/away).
    """
    m = pred["markets"]
    return {
        "home": m["home_win"] / 100, "draw": m["draw"] / 100, "away": m["away_win"] / 100,
        "over_1_5": m["over_1_5"] / 100, "over_2_5": m["over_2_5"] / 100,
        "under_2_5": m["under_2_5"] / 100,
        "btts_yes": m["btts_yes"] / 100, "btts_no": m["btts_no"] / 100,
    }


def latest_odds_for_fixture(fixture_id):
    """
    Dernière capture par (marché, sélection) — pas tout l'historique.
    {"1N2": {"1": 2.1, ...}, ...} ou {} si rien capturé.
    """
    conn = _connect()
    try:
        rows = conn.execute("""
            SELECT market, selection, odds FROM club_odds_snapshots o
            WHERE fixture_id=? AND captured_at = (
                SELECT MAX(captured_at) FROM club_odds_snapshots
                WHERE fixture_id=o.fixture_id AND market=o.market AND selection=o.selection
            )""", (fixture_id,)).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return {}
    conn.close()
    out = {}
    for market, sel, odds in rows:
        out.setdefault(market, {})[sel] = odds
    return out


def _ensure_log_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS club_value_log (
        fixture_id INTEGER, league_id INTEGER, match TEXT, market TEXT,
        selection TEXT, odds REAL, p_model REAL, p_fair REAL,
        edge REAL, ev REAL, kelly_stake_pct REAL,
        detected_at TEXT DEFAULT CURRENT_TIMESTAMP)""")


def scan_league(league_id, min_ev=None, log=True):
    """
    Renvoie la liste des values détectées pour tous les matchs à venir
    de la ligue ayant à la fois une prédiction (modèle entraîné) et des
    cotes capturées. Persiste dans club_value_log si log=True.
    """
    if min_ev is not None:
        vf.EV_MIN = min_ev

    conn = _connect()
    try:
        rows = conn.execute("""SELECT fixture_id, home_team, away_team
            FROM club_upcoming WHERE league_id=? ORDER BY date""", (league_id,)).fetchall()
    except sqlite3.OperationalError:
        rows = []
    conn.close()

    all_values = []
    for fid, home, away in rows:
        odds = latest_odds_for_fixture(fid)
        if not odds:
            continue
        pred = service.club_predict(league_id, home, away)
        if pred is None:
            continue
        model_probs = _adapt_club_markets(pred)
        match_name = f"{home} vs {away}"
        values = vf.find_values_for_match(match_name, model_probs, odds)
        for v in values:
            v["fixture_id"] = fid
            v["league_id"] = league_id
        all_values += values

    if log and all_values:
        conn = _connect()
        _ensure_log_table(conn)
        for v in all_values:
            conn.execute("""INSERT INTO club_value_log
                (fixture_id, league_id, match, market, selection, odds,
                 p_model, p_fair, edge, ev, kelly_stake_pct)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (
                v["fixture_id"], v["league_id"], v["match"], v["market"],
                v["selection"], v["odds"], v["p_model"], v["p_fair"],
                v["edge"], v["ev"], v["kelly_stake_pct"]))
        conn.commit()
        conn.close()

    return all_values


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    ps = sub.add_parser("scan")
    ps.add_argument("--leagues", default="big5")
    ps.add_argument("--min-ev", type=float, default=None,
                    help="Seuil EV en fraction (0.05 = 5%%), défaut = celui de value_finder.py")
    ps.add_argument("--bankroll", type=float, default=None)
    ps.add_argument("--no-log", action="store_true")
    args = ap.parse_args()

    leagues = resolve_leagues(args.leagues)
    all_values = []
    for lg in leagues:
        print(f"\n════ {league_display_name(lg)} ════")
        vals = scan_league(lg, min_ev=args.min_ev, log=not args.no_log)
        if not vals:
            print("   Aucune cote capturée, aucun modèle entraîné, ou aucune value au-dessus du seuil.")
        all_values += vals

    if all_values:
        vf.print_values(all_values, bankroll=args.bankroll)


if __name__ == "__main__":
    main()
