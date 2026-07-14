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
