"""
Fixtures partagées. Principe central : AUCUN test ne touche
data/db/foot_stats.db (la vraie base de production). Chaque test qui a
besoin d'une base SQLite reçoit une base temporaire vide, et les
modules concernés (qui lisent tous une constante DB_PATH au niveau
module) sont redirigés vers elle via monkeypatch.
"""
import os
import sys
import sqlite3
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in ("src", "src/api", "src/models"):
    sys.path.insert(0, os.path.join(PROJECT_ROOT, p))


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """
    Base SQLite vide et isolée. Redirige DB_PATH dans tous les modules
    qui en ont une copie (sync_api_football, service, club_dixon_coles)
    pour que les tests ne touchent jamais la vraie base.
    """
    db_path = str(tmp_path / "test.db")
    sqlite3.connect(db_path).close()

    import sync_api_football as sync_mod
    monkeypatch.setattr(sync_mod, "DB_PATH", db_path)
    try:
        import service as service_mod
        monkeypatch.setattr(service_mod, "DB_PATH", db_path)
    except ImportError:
        pass
    try:
        import club_dixon_coles as cdc_mod
        monkeypatch.setattr(cdc_mod, "DB_PATH", db_path)
    except ImportError:
        pass
    try:
        import club_value_finder as cvf_mod
        monkeypatch.setattr(cvf_mod, "DB_PATH", db_path)
    except ImportError:
        pass

    return db_path


@pytest.fixture
def seeded_club_matches(temp_db):
    """Quelques matchs Ligue 1 synthétiques dans club_matches, avec ids d'équipe."""
    conn = sqlite3.connect(temp_db)
    conn.execute("""
        CREATE TABLE club_matches (
            fixture_id INTEGER PRIMARY KEY, league_id INTEGER, league_name TEXT,
            season INTEGER, date TEXT, round TEXT, home_team TEXT, away_team TEXT,
            home_score INTEGER, away_score INTEGER, status TEXT,
            home_id INTEGER, away_id INTEGER
        )
    """)
    rows = [
        (1, 61, "Ligue 1", 2025, "2025-08-15", "Regular Season - 1", "Lyon", "Marseille", 2, 1, "FT", 80, 81),
        (2, 61, "Ligue 1", 2025, "2025-08-22", "Regular Season - 2", "Marseille", "Monaco", 1, 1, "FT", 81, 91),
        (3, 61, "Ligue 1", 2025, "2025-08-29", "Regular Season - 3", "Monaco", "Lyon", 0, 2, "FT", 91, 80),
        (4, 61, "Ligue 1", 2025, "2025-09-05", "Regular Season - 4", "Lyon", "Monaco", 1, 1, "FT", 80, 91),
    ]
    conn.executemany("INSERT INTO club_matches VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    return temp_db
