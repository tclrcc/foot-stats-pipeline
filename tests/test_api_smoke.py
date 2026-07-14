"""
Tests de fumée de l'API : vérifie que les endpoints répondent sans
planter et respectent les contrats d'erreur de base (404/422 aux
bons endroits). Ne teste pas l'exactitude des prédictions — le
backtest walk-forward sur données réelles s'en charge déjà.
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(temp_db):
    import main
    return TestClient(main.app)


def test_clubs_leagues_empty_db_returns_empty_list(client):
    r = client.get("/clubs/leagues")
    assert r.status_code == 200
    assert r.json() == []


def test_clubs_standings_unknown_league_404(client):
    r = client.get("/clubs/standings", params={"league": 61, "season": 2025})
    assert r.status_code == 404


def test_clubs_standings_cup_competition_422(client, tmp_path, monkeypatch):
    import sync_api_football as s
    registry = tmp_path / "leagues.json"
    registry.write_text('{"europa": {"id": 3, "name": "Europa League", "type": "cup"}}',
                        encoding="utf-8")
    monkeypatch.setattr(s, "EXTRA_LEAGUES_PATH", str(registry))

    r = client.get("/clubs/standings", params={"league": 3, "season": 2025})
    assert r.status_code == 422


def test_clubs_predict_untrained_league_404(client):
    r = client.get("/clubs/predict", params={"league": 61, "home": "Lyon", "away": "Marseille"})
    assert r.status_code == 404


def test_clubs_results_missing_table_404(client):
    r = client.get("/clubs/results", params={"league": 61, "season": 2025})
    assert r.status_code == 404


def test_model_performance_unavailable_when_no_backtest(client):
    r = client.get("/model/performance")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is False


def test_clubs_players_search_rejects_short_query(client):
    r = client.get("/clubs/players/search", params={"q": "ab"})
    assert r.status_code == 422  # min_length=3
