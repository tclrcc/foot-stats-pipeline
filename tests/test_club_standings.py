"""
Tests du classement recalculé depuis club_matches (service.club_standings).
Vérifie les points (3/1/0), la différence de buts, le départage et le
garde-fou sur les compétitions cup.
"""
import service


def test_standings_points_and_ranking(seeded_club_matches):
    # Lyon : V(Marseille) + V(Monaco) + N(Monaco) = 3+3+1 = 7 pts, 3 MJ
    # Marseille : D(Lyon) + N(Monaco) = 0+1 = 1 pt, 2 MJ
    # Monaco : N(Marseille) + D(Lyon) + N(Lyon) = 1+0+1 = 2 pts, 3 MJ
    table = service.club_standings(61, 2025)
    by_team = {r["team"]: r for r in table}

    assert by_team["Lyon"]["points"] == 7
    assert by_team["Lyon"]["played"] == 3
    assert by_team["Lyon"]["won"] == 2
    assert by_team["Lyon"]["drawn"] == 1
    assert by_team["Marseille"]["points"] == 1
    assert by_team["Monaco"]["points"] == 2

    # Classement trié par points décroissants
    assert [r["team"] for r in table] == ["Lyon", "Monaco", "Marseille"]
    assert table[0]["rank"] == 1


def test_standings_goal_difference(seeded_club_matches):
    table = service.club_standings(61, 2025)
    lyon = next(r for r in table if r["team"] == "Lyon")
    # Buts marqués : 2(vs OM)+2(@Monaco)+1(vs Monaco)=5 ; encaissés : 1+0+1=2
    assert lyon["gf"] == 5
    assert lyon["ga"] == 2
    assert lyon["gd"] == 3


def test_standings_form_last_5(seeded_club_matches):
    table = service.club_standings(61, 2025)
    lyon = next(r for r in table if r["team"] == "Lyon")
    assert lyon["form"] == ["V", "V", "N"]  # dans l'ordre chronologique


def test_standings_none_when_no_data(temp_db):
    conn = __import__("sqlite3").connect(temp_db)
    conn.execute("""CREATE TABLE club_matches (
        fixture_id INTEGER PRIMARY KEY, league_id INTEGER, league_name TEXT,
        season INTEGER, date TEXT, round TEXT, home_team TEXT, away_team TEXT,
        home_score INTEGER, away_score INTEGER, status TEXT)""")
    conn.commit()
    conn.close()
    assert service.club_standings(61, 2025) is None


def test_standings_table_absent_returns_none(temp_db):
    # Aucune table club_matches du tout (avant le premier 'results')
    assert service.club_standings(61, 2025) is None


def test_club_dossier_skips_standings_for_cup(seeded_club_matches, tmp_path, monkeypatch):
    """
    Garde-fou trouvé en revue : le classement recalculé n'a pas de sens
    pour une compétition à phases mixtes. club_dossier() doit renvoyer
    standings=None + une note, jamais un tableau agrégé trompeur.
    """
    import sqlite3
    registry = tmp_path / "leagues.json"
    registry.write_text('{"europa": {"id": 61, "name": "Europa League", "type": "cup"}}',
                        encoding="utf-8")
    import sync_api_football as s
    monkeypatch.setattr(s, "EXTRA_LEAGUES_PATH", str(registry))

    d = service.club_dossier(61, "Lyon", "Marseille")
    assert d["standings"]["home"] is None
    assert d["standings"]["away"] is None
    assert d["standings_note"] is not None
    assert "phases mixtes" in d["standings_note"]
    # La forme et le H2H, eux, restent pertinents et calculés
    assert len(d["form"]["home"]) > 0
