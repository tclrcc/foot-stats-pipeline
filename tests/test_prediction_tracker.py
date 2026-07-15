"""
Tests du journal des prédictions : journalisation, résolution (via
club_matches ET via appel API direct), et calcul du rapport — avec le
garde-fou explicite du bug rencontré en sandbox (baseline nulle avec un
petit échantillon ne doit jamais faire planter le rapport).
"""
import sqlite3
import prediction_tracker as pt


def _seed_selections_model(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE dc_team_params (team TEXT PRIMARY KEY, alpha REAL, beta REAL)")
    conn.execute("CREATE TABLE dc_global_params (gamma REAL, rho REAL)")
    conn.execute("INSERT INTO dc_team_params VALUES ('England', 1.55, 0.42)")
    conn.execute("INSERT INTO dc_team_params VALUES ('Argentina', 1.68, 0.35)")
    conn.execute("INSERT INTO dc_global_params VALUES (1.3, -0.12)")
    conn.commit()
    conn.close()


def test_log_selections_and_resolve_via_api(temp_db, tmp_path, monkeypatch):
    _seed_selections_model(temp_db)
    fixtures_path = tmp_path / "fixtures.json"
    fixtures_path.write_text(
        '{"fixtures": [{"date": "2020-01-01 21:00", "home": "England", '
        '"away": "Argentina", "stage": "Semi-finals"}]}', encoding="utf-8")
    monkeypatch.setattr(pt, "FIXTURES_PATH", str(fixtures_path))

    calls = []
    def fake_get(path, params, retries=2):
        calls.append((path, params))
        if "date" in params:
            return [{"fixture": {"id": 777},
                     "teams": {"home": {"name": "England"}, "away": {"name": "Argentina"}}}]
        if "id" in params:
            return [{"fixture": {"id": 777, "status": {"short": "FT"}},
                     "goals": {"home": 1, "away": 2}}]
        return []
    # find_fixture_id() appelle _get depuis SON module (sync_api_football),
    # pas la référence importée dans prediction_tracker — les deux doivent
    # être patchées, sinon seul resolve() (qui appelle _get directement
    # dans prediction_tracker) verrait le mock.
    import sync_api_football as sync_mod
    monkeypatch.setattr(sync_mod, "_get", fake_get)
    monkeypatch.setattr(pt, "_get", fake_get)

    pt.log_selections(league=1, season=2026)
    pt.resolve()

    conn = sqlite3.connect(temp_db)
    row = conn.execute("SELECT resolved, actual_home_score, actual_away_score "
                       "FROM prediction_log WHERE fixture_id=777").fetchone()
    conn.close()
    assert row == (1, 1, 2)


def test_resolve_club_uses_club_matches_no_api_call(temp_db, monkeypatch):
    conn = sqlite3.connect(temp_db)
    conn.execute("""CREATE TABLE club_upcoming (
        fixture_id INTEGER PRIMARY KEY, league_id INTEGER, league_name TEXT, season INTEGER,
        date TEXT, round TEXT, home_team TEXT, away_team TEXT, home_id INTEGER, away_id INTEGER)""")
    conn.execute("INSERT INTO club_upcoming VALUES (900,61,'Ligue 1',2025,"
                 "'2020-01-01 21:00','J1','Lyon','Marseille',80,81)")
    conn.execute("""CREATE TABLE club_matches (
        fixture_id INTEGER PRIMARY KEY, league_id INTEGER, league_name TEXT, season INTEGER,
        date TEXT, round TEXT, home_team TEXT, away_team TEXT,
        home_score INTEGER, away_score INTEGER, status TEXT, home_id INTEGER, away_id INTEGER)""")
    conn.execute("INSERT INTO club_matches VALUES (900,61,'Ligue 1',2025,'2020-01-01',"
                 "'J1','Lyon','Marseille',3,1,'FT',80,81)")
    conn.execute("CREATE TABLE club_dc_params (league_id INTEGER, team TEXT, alpha REAL, beta REAL,"
                 " PRIMARY KEY(league_id,team))")
    conn.execute("CREATE TABLE club_dc_global (league_id INTEGER PRIMARY KEY, gamma REAL, rho REAL,"
                 " nll REAL, n_matches INTEGER, trained_at TEXT)")
    conn.execute("INSERT INTO club_dc_params VALUES (61,'Lyon',1.5,0.4)")
    conn.execute("INSERT INTO club_dc_params VALUES (61,'Marseille',1.2,0.5)")
    conn.execute("INSERT INTO club_dc_global VALUES (61,1.3,-0.1,50.0,100,'2026-07-01')")
    conn.commit()
    conn.close()

    def forbidden_get(path, params, retries=2):
        raise AssertionError("résolution club ne doit jamais appeler l'API")
    monkeypatch.setattr(pt, "_get", forbidden_get)

    pt.log_club("61")
    pt.resolve()  # ne doit pas lever d'exception

    conn = sqlite3.connect(temp_db)
    row = conn.execute("SELECT resolved, actual_home_score, actual_away_score "
                       "FROM prediction_log WHERE fixture_id=900").fetchone()
    conn.close()
    assert row == (1, 3, 1)


def test_resolve_skips_matches_not_yet_past_buffer(temp_db, monkeypatch):
    from datetime import datetime, timedelta
    conn = sqlite3.connect(temp_db)
    conn.execute("""CREATE TABLE prediction_log (
        scope TEXT, fixture_id INTEGER, league_id INTEGER,
        home_team TEXT, away_team TEXT, kickoff TEXT, stage TEXT,
        method TEXT, xg_home REAL, xg_away REAL,
        p_home REAL, p_draw REAL, p_away REAL,
        p_over_15 REAL, p_over_25 REAL, p_under_25 REAL,
        p_btts_yes REAL, p_btts_no REAL, top_score TEXT,
        logged_at TEXT, resolved INTEGER DEFAULT 0,
        actual_home_score INTEGER, actual_away_score INTEGER, resolved_at TEXT,
        PRIMARY KEY (scope, fixture_id))""")
    soon = (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M")
    conn.execute("""INSERT INTO prediction_log
        (scope, fixture_id, league_id, home_team, away_team, kickoff, method,
         xg_home, xg_away, p_home, p_draw, p_away, p_over_15, p_over_25,
         p_under_25, p_btts_yes, p_btts_no)
        VALUES ('club',1,61,'A','B',?,'dixon_coles_club',1,1,.4,.3,.3,.7,.5,.5,.5,.5)""", (soon,))
    conn.commit()
    conn.close()

    monkeypatch.setattr(pt, "_get", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("ne doit pas etre appele avant la marge")))
    pt.resolve()  # match dans 10 min < marge de 150 min -> doit être ignoré, pas planter

    conn = sqlite3.connect(temp_db)
    resolved = conn.execute("SELECT resolved FROM prediction_log").fetchone()[0]
    conn.close()
    assert resolved == 0


def test_report_does_not_crash_on_zero_baseline_small_sample(temp_db):
    """
    Regression directe du bug trouve en sandbox : avec un tres petit
    echantillon, la baseline naive peut valoir exactement 0 (elle
    'devine' parfaitement l'unique issue observee) — le calcul du gain
    ne doit pas planter sur cette valeur falsy-mais-valide.
    """
    conn = sqlite3.connect(temp_db)
    conn.execute("""CREATE TABLE prediction_log (
        scope TEXT, fixture_id INTEGER, league_id INTEGER,
        home_team TEXT, away_team TEXT, kickoff TEXT, stage TEXT,
        method TEXT, xg_home REAL, xg_away REAL,
        p_home REAL, p_draw REAL, p_away REAL,
        p_over_15 REAL, p_over_25 REAL, p_under_25 REAL,
        p_btts_yes REAL, p_btts_no REAL, top_score TEXT,
        logged_at TEXT, resolved INTEGER DEFAULT 0,
        actual_home_score INTEGER, actual_away_score INTEGER, resolved_at TEXT,
        PRIMARY KEY (scope, fixture_id))""")
    conn.execute("""INSERT INTO prediction_log
        (scope, fixture_id, league_id, home_team, away_team, kickoff, method,
         xg_home, xg_away, p_home, p_draw, p_away, p_over_15, p_over_25,
         p_under_25, p_btts_yes, p_btts_no, resolved, actual_home_score, actual_away_score)
        VALUES ('selections',777,1,'England','Argentina','2026-07-15 21:00','dixon_coles',
                0.9,1.6,0.183,0.372,0.445,0.799,0.276,0.724,0.276,0.724,1,1,2)""")
    conn.commit()
    conn.close()

    rep = pt.build_report(scope="selections")
    assert rep["n"] == 1
    assert rep["accuracy"] == 1.0  # away (0.445) était le plus probable, away a gagné
    # Ne doit pas lever d'exception à l'impression, gain=None géré proprement
    pt.print_report(rep, "test")


def test_build_report_returns_none_without_resolved_matches(temp_db):
    assert pt.build_report(scope="club") is None
