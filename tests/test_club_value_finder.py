"""
Tests de la couche cotes/efficience : parsing de la réponse /odds vers
le schéma normalisé, et adaptation des probabilités du modèle club vers
le format attendu par value_finder.py (moteur EV/Kelly réutilisé,
jamais dupliqué).
"""
import sync_api_football as s
import club_value_finder as cvf


def test_parse_odds_response_best_price_across_bookmakers():
    resp = [{
        "bookmakers": [
            {"name": "Bet365", "bets": [
                {"name": "Match Winner", "values": [
                    {"value": "Home", "odd": "2.10"},
                    {"value": "Draw", "odd": "3.40"},
                    {"value": "Away", "odd": "3.60"}]},
            ]},
            {"name": "Unibet", "bets": [
                {"name": "Match Winner", "values": [
                    {"value": "Home", "odd": "2.15"},  # meilleure cote domicile
                    {"value": "Draw", "odd": "3.30"},
                    {"value": "Away", "odd": "3.60"}]},
            ]},
        ]
    }]
    parsed = s._parse_odds_response(resp, "Lyon", "Marseille")
    assert parsed["1N2"]["1"] == 2.15
    assert parsed["1N2"]["N"] == 3.40
    assert parsed["1N2"]["2"] == 3.60


def test_parse_odds_response_all_three_markets():
    resp = [{
        "bookmakers": [{"name": "Bet365", "bets": [
            {"name": "Match Winner", "values": [
                {"value": "Home", "odd": "2.0"}, {"value": "Draw", "odd": "3.3"}, {"value": "Away", "odd": "3.8"}]},
            {"name": "Goals Over/Under", "values": [
                {"value": "Over 2.5", "odd": "1.9"}, {"value": "Under 2.5", "odd": "1.9"}]},
            {"name": "Both Teams Score", "values": [
                {"value": "Yes", "odd": "1.75"}, {"value": "No", "odd": "2.0"}]},
        ]}]
    }]
    parsed = s._parse_odds_response(resp, "A", "B")
    assert set(parsed.keys()) == {"1N2", "Totaux", "BTTS"}


def test_parse_odds_response_ignores_unhandled_markets():
    resp = [{
        "bookmakers": [{"name": "Bet365", "bets": [
            {"name": "Corners Over/Under", "values": [{"value": "Over 9.5", "odd": "1.9"}]},
        ]}]
    }]
    parsed = s._parse_odds_response(resp, "A", "B")
    assert parsed == {}


def test_parse_odds_response_empty_when_no_odds_yet():
    assert s._parse_odds_response([], "A", "B") == {}
    assert s._parse_odds_response(None, "A", "B") == {}


def test_adapt_club_markets_converts_percent_to_fraction():
    pred = {"markets": {
        "home_win": 55.4, "draw": 23.1, "away_win": 21.5,
        "over_1_5": 83.7, "over_2_5": 62.0, "under_2_5": 38.0,
        "btts_yes": 61.2, "btts_no": 38.8,
    }}
    adapted = cvf._adapt_club_markets(pred)
    assert adapted["home"] == pred["markets"]["home_win"] / 100
    assert adapted["draw"] == 0.231
    assert 0.0 <= adapted["home"] <= 1.0
    assert abs(adapted["home"] + adapted["draw"] + adapted["away"] - 1.0) < 1e-6


def test_latest_odds_for_fixture_missing_table_returns_empty(temp_db):
    assert cvf.latest_odds_for_fixture(999) == {}


def test_scan_league_skips_fixtures_without_odds_or_model(seeded_club_matches):
    # club_upcoming absente + aucune cote -> aucune value, aucun crash
    assert cvf.scan_league(61, log=False) == []


def _seed_selections_model(db_path):
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE dc_team_params (team TEXT PRIMARY KEY, alpha REAL, beta REAL)")
    conn.execute("CREATE TABLE dc_global_params (gamma REAL, rho REAL)")
    conn.execute("INSERT INTO dc_team_params VALUES ('England', 1.55, 0.42)")
    conn.execute("INSERT INTO dc_team_params VALUES ('Argentina', 1.68, 0.35)")
    conn.execute("INSERT INTO dc_global_params VALUES (1.3, -0.12)")
    conn.execute("""CREATE TABLE club_upcoming (
        fixture_id INTEGER PRIMARY KEY, league_id INTEGER, league_name TEXT, season INTEGER,
        date TEXT, round TEXT, home_team TEXT, away_team TEXT, home_id INTEGER, away_id INTEGER)""")
    conn.execute("INSERT INTO club_upcoming VALUES (888,1,'World Cup',2026,'2026-07-15 21:00',"
                 "'Semi-finals','England','Argentina',10,25)")
    conn.execute("""CREATE TABLE club_odds_snapshots (
        fixture_id INTEGER, market TEXT, selection TEXT, odds REAL, captured_at TEXT,
        PRIMARY KEY (fixture_id, market, selection, captured_at))""")
    for m, sel, o in [("1N2", "1", 2.75), ("1N2", "N", 3.30), ("1N2", "2", 2.55),
                      ("BTTS", "Yes", 1.80), ("BTTS", "No", 1.95)]:
        conn.execute("INSERT INTO club_odds_snapshots VALUES (888,?,?,?,CURRENT_TIMESTAMP)", (m, sel, o))
    conn.commit()
    conn.close()


def test_scan_league_without_selections_flag_finds_nothing_for_untrained_cdm(temp_db):
    """League 1 (CDM) n'a jamais été entraînée côté modèle club -> rien sans --selections."""
    _seed_selections_model(temp_db)
    assert cvf.scan_league(1, min_ev=0.0, log=False, selections=False) == []


def test_scan_league_with_selections_flag_uses_selections_model(temp_db):
    """Avec selections=True, utilise service.predict() (terrain neutre) -> des values apparaissent."""
    _seed_selections_model(temp_db)
    values = cvf.scan_league(1, min_ev=0.0, log=False, selections=True)
    assert len(values) > 0
    assert all(v["match"] == "England vs Argentina" for v in values)
