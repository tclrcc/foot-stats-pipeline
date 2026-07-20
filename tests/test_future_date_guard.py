"""
Garde-fou contre les matchs 'terminés' datés dans le futur — bug réel
observé (une confrontation directe du 24 août 2026 affichée comme déjà
jouée, alors qu'on n'était qu'en juillet). Aucun match ne devrait jamais
apparaître comme joué avant sa date réelle : garde-fou à la source
(import) ET en défense dans les trois consommateurs de club_matches
(H2H, forme récente, classement).
"""
import sqlite3
import sync_api_football as s
import service


def _seed_with_future_match(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE club_matches (fixture_id INTEGER PRIMARY KEY, league_id INTEGER,
        league_name TEXT, season INTEGER, date TEXT, round TEXT, home_team TEXT, away_team TEXT,
        home_score INTEGER, away_score INTEGER, status TEXT, home_id INTEGER, away_id INTEGER)""")
    conn.executemany("INSERT INTO club_matches VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", [
        (1, 113, "Allsvenskan", 2026, "2026-07-05", "J1", "Kalmar FF", "Malmo FF", 2, 2, "FT", 1, 2),
        (2, 113, "Allsvenskan", 2026, "2026-08-24", "J2", "Kalmar FF", "Malmo FF", 2, 3, "FT", 1, 2),
    ])
    conn.commit()
    conn.close()


def test_cmd_results_rejects_finished_match_with_future_date(temp_db, monkeypatch):
    def fake_get(path, params, retries=2):
        return [
            {"fixture": {"id": 1, "date": "2026-07-05T18:00:00+02:00", "status": {"short": "FT"}},
             "league": {"round": "J1"},
             "teams": {"home": {"name": "Kalmar FF", "id": 1}, "away": {"name": "Malmo FF", "id": 2}},
             "goals": {"home": 2, "away": 2}},
            {"fixture": {"id": 2, "date": "2026-08-24T18:00:00+02:00", "status": {"short": "FT"}},
             "league": {"round": "J2"},
             "teams": {"home": {"name": "Kalmar FF", "id": 1}, "away": {"name": "Malmo FF", "id": 2}},
             "goals": {"home": 2, "away": 3}},
        ]
    monkeypatch.setattr(s, "_get", fake_get)
    import types
    s.cmd_results(types.SimpleNamespace(leagues="113", seasons="2026"))

    conn = sqlite3.connect(temp_db)
    rows = conn.execute("SELECT fixture_id, date FROM club_matches").fetchall()
    conn.close()
    assert rows == [(1, "2026-07-05")]


def test_h2h_excludes_future_dated_match(temp_db):
    _seed_with_future_match(temp_db)
    d = service.club_dossier(113, "Kalmar FF", "Malmo FF")
    assert all(m["date"] <= "2026-07-21" for m in d["h2h"])
    assert len(d["h2h"]) == 1


def test_form_excludes_future_dated_match(temp_db):
    _seed_with_future_match(temp_db)
    d = service.club_dossier(113, "Kalmar FF", "Malmo FF")
    assert len(d["form"]["home"]) == 1


def test_standings_excludes_future_dated_match(temp_db):
    _seed_with_future_match(temp_db)
    table = service.club_standings(113, 2026)
    kalmar = next(r for r in table if r["team"] == "Kalmar FF")
    assert kalmar["played"] == 1
