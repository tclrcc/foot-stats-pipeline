"""
Tests de l'harmonisation des noms d'équipe (_harmonize_team_names).
Reproduit le bug réel constaté en production : l'API renomme un club
entre saisons ('Bayern Munich' -> 'Bayern München'), ce qui coupait son
corpus en deux et faussait ses paramètres Dixon-Coles.
"""
import sqlite3
import sync_api_football as s


def _make_club_matches_with_ids(temp_db):
    conn = sqlite3.connect(temp_db)
    conn.execute("""CREATE TABLE club_matches (
        fixture_id INTEGER PRIMARY KEY, league_id INTEGER, league_name TEXT,
        season INTEGER, date TEXT, round TEXT, home_team TEXT, away_team TEXT,
        home_score INTEGER, away_score INTEGER, status TEXT,
        home_id INTEGER, away_id INTEGER)""")
    conn.commit()
    return conn


def test_harmonize_reunifies_renamed_team(temp_db):
    conn = _make_club_matches_with_ids(temp_db)
    rows = [
        (1, 78, "Bundesliga", 2022, "2022-09-01", "R1", "Bayern Munich", "Dortmund", 3, 1, "FT", 157, 165),
        (2, 78, "Bundesliga", 2023, "2023-09-01", "R1", "Dortmund", "Bayern Munich", 0, 2, "FT", 165, 157),
        (3, 78, "Bundesliga", 2025, "2025-09-01", "R1", "Bayern München", "Dortmund", 4, 0, "FT", 157, 165),
    ]
    conn.executemany("INSERT INTO club_matches VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()

    s._harmonize_team_names(conn)

    names = {r[0] for r in conn.execute(
        "SELECT home_team FROM club_matches WHERE home_id=157")}
    assert names == {"Bayern München"}, "Le nom le plus récent doit s'appliquer partout"

    # Le corpus de l'id 157 est maintenant unifié sous un seul nom
    n_matches_id157 = conn.execute(
        "SELECT COUNT(*) FROM club_matches WHERE home_id=157 OR away_id=157"
    ).fetchone()[0]
    assert n_matches_id157 == 3
    conn.close()


def test_harmonize_no_op_when_names_already_consistent(temp_db):
    conn = _make_club_matches_with_ids(temp_db)
    rows = [
        (1, 61, "Ligue 1", 2025, "2025-09-01", "R1", "Lyon", "Marseille", 2, 1, "FT", 80, 81),
    ]
    conn.executemany("INSERT INTO club_matches VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()

    s._harmonize_team_names(conn)  # ne doit rien casser ni rien modifier

    row = conn.execute("SELECT home_team, away_team FROM club_matches").fetchone()
    assert row == ("Lyon", "Marseille")
    conn.close()


def test_norm_handles_accents_and_case():
    assert s._norm("Côte d'Ivoire") == "cote d'ivoire"
    assert s._norm("  Bayern MÜNCHEN ") == "bayern munchen"
