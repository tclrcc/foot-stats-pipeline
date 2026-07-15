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


def test_parse_odds_response_excludes_half_variants():
    """
    Regression directe du bug reel : 'Both Teams to Score 1st Half' (cotes
    ~6-10, marche rare) etait confondu avec le BTTS plein match classique
    (cotes ~1.5-2.3), produisant des EV a +400% qui n'etaient pas de
    vraies values mais un marche mal identifie.
    """
    resp = [{"bookmakers": [{"name": "Bet365", "bets": [
        {"name": "Both Teams to Score", "values": [
            {"value": "Yes", "odd": "1.85"}, {"value": "No", "odd": "1.95"}]},
        {"name": "Both Teams to Score 1st Half", "values": [
            {"value": "Yes", "odd": "9.90"}, {"value": "No", "odd": "1.05"}]},
        {"name": "Goals Over/Under", "values": [
            {"value": "Over 2.5", "odd": "1.90"}]},
        {"name": "Goals Over/Under 1st Half", "values": [
            {"value": "Over 0.5", "odd": "1.40"}]},
    ]}]}]
    parsed = s._parse_odds_response(resp, "A", "B")
    assert parsed["BTTS"]["Yes"] == 1.85
    assert len(parsed["Totaux"]) == 1  # la variante 1ère mi-temps n'a pas pollué


def test_value_finder_sanity_ceiling_rejects_absurd_ev():
    """
    Garde-fou de defense en profondeur : meme si une cote aberrante
    passe malgre le filtre en amont, aucune EV extreme ne doit jamais
    etre presentee comme une vraie value.
    """
    import value_finder as vf
    model_probs = {"home": 0.514, "draw": 0.25, "away": 0.236,
                   "over_1_5": 0.8, "over_2_5": 0.5, "under_2_5": 0.5,
                   "btts_yes": 0.514, "btts_no": 0.486}
    odds = {"BTTS": {"Yes": 9.90, "No": 2.25}}
    vals = vf.find_values_for_match("A vs B", model_probs, odds)
    assert not any(v["market"] == "BTTS" and v["selection"] == "Yes" for v in vals)
