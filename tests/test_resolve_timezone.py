"""
Garde-fou sur le fuseau horaire dans resolve() — bug reel signale :
'0 resolu' alors qu'un match Suede etait deja termine. Cause possible :
la comparaison naive de resolve() peut etre decalee si le fuseau du
serveur differe de celui utilise par l'API (?timezone=Europe/Paris,
demande par 'upcoming'). Corrige avec un equivalent UTC calcule des la
capture (club_upcoming.date_utc -> prediction_log.kickoff_utc), avec
repli sur l'ancien comportement pour les lignes journalisees avant ce
correctif (kickoff_utc NULL).
"""
import sqlite3
from datetime import datetime, timedelta, timezone
import sync_api_football as s
import prediction_tracker as pt


def test_upcoming_computes_utc_equivalent(temp_db):
    def fake_get(path, params, retries=2):
        return [{"fixture": {"id": 1, "date": "2026-07-20T19:00:00+02:00", "status": {"short": "NS"}},
                 "league": {"round": "J13", "season": 2026},
                 "teams": {"home": {"name": "Kalmar FF", "id": 1}, "away": {"name": "Malmo FF", "id": 2}}}]
    import types
    orig_get = s._get
    s._get = fake_get
    try:
        s.cmd_upcoming(types.SimpleNamespace(leagues="113", days="7", timezone="Europe/Paris"))
    finally:
        s._get = orig_get

    conn = sqlite3.connect(temp_db)
    row = conn.execute("SELECT date, date_utc FROM club_upcoming WHERE fixture_id=1").fetchone()
    conn.close()
    assert row == ("2026-07-20 19:00", "2026-07-20 17:00")


def test_resolve_uses_utc_kickoff_when_available(temp_db):
    pt._ensure_table()
    conn = sqlite3.connect(temp_db)
    conn.execute("CREATE TABLE club_matches (fixture_id INTEGER PRIMARY KEY, league_id INTEGER,"
                 " league_name TEXT, season INTEGER, date TEXT, round TEXT, home_team TEXT,"
                 " away_team TEXT, home_score INTEGER, away_score INTEGER, status TEXT,"
                 " home_id INTEGER, away_id INTEGER)")
    now_utc = datetime.now(timezone.utc)
    # Coup d'envoi reel il y a 105 min (< marge 150) -> ne doit pas resoudre
    ko1_utc = (now_utc - timedelta(minutes=105)).strftime("%Y-%m-%d %H:%M")
    # Coup d'envoi reel il y a 155 min (> marge 150) -> doit resoudre
    ko2_utc = (now_utc - timedelta(minutes=155)).strftime("%Y-%m-%d %H:%M")

    for fid, ko_utc, resolvable in [(1, ko1_utc, False), (2, ko2_utc, True)]:
        conn.execute("""INSERT INTO prediction_log
            (scope,fixture_id,league_id,home_team,away_team,kickoff,kickoff_utc,method,
             xg_home,xg_away,p_home,p_draw,p_away,p_over_15,p_over_25,p_under_25,
             p_btts_yes,p_btts_no,resolved)
            VALUES ('club',?,113,'A','B',?,?,'dixon_coles_club',1,1,.4,.3,.3,.7,.5,.5,.5,.5,0)""",
            (fid, ko_utc, ko_utc))
    conn.execute("INSERT INTO club_matches VALUES (2,113,'Allsvenskan',2026,?,'J13','A','B',"
                 "2,2,'FT',1,2)", (ko2_utc[:10],))
    conn.commit()
    conn.close()

    pt.resolve()

    conn = sqlite3.connect(temp_db)
    r1 = conn.execute("SELECT resolved FROM prediction_log WHERE fixture_id=1").fetchone()[0]
    r2 = conn.execute("SELECT resolved, actual_home_score, actual_away_score "
                      "FROM prediction_log WHERE fixture_id=2").fetchone()
    conn.close()
    assert r1 == 0, "150 min pas encore ecoulees en UTC reel -> ne doit pas resoudre"
    assert r2 == (1, 2, 2), "150 min ecoulees en UTC reel -> doit resoudre"


def test_resolve_falls_back_to_naive_comparison_for_legacy_rows(temp_db):
    """Lignes journalisees avant ce correctif (kickoff_utc NULL) : comportement inchange."""
    pt._ensure_table()
    conn = sqlite3.connect(temp_db)
    conn.execute("CREATE TABLE club_matches (fixture_id INTEGER PRIMARY KEY, league_id INTEGER,"
                 " league_name TEXT, season INTEGER, date TEXT, round TEXT, home_team TEXT,"
                 " away_team TEXT, home_score INTEGER, away_score INTEGER, status TEXT,"
                 " home_id INTEGER, away_id INTEGER)")
    old_kickoff = (datetime.now() - timedelta(minutes=200)).strftime("%Y-%m-%d %H:%M")
    conn.execute("""INSERT INTO prediction_log
        (scope,fixture_id,league_id,home_team,away_team,kickoff,kickoff_utc,method,
         xg_home,xg_away,p_home,p_draw,p_away,p_over_15,p_over_25,p_under_25,
         p_btts_yes,p_btts_no,resolved)
        VALUES ('club',3,113,'C','D',?,NULL,'dixon_coles_club',1,1,.4,.3,.3,.7,.5,.5,.5,.5,0)""",
        (old_kickoff,))
    conn.execute("INSERT INTO club_matches VALUES (3,113,'Allsvenskan',2026,?,'J1','C','D',"
                 "1,0,'FT',5,6)", (old_kickoff[:10],))
    conn.commit()
    conn.close()

    pt.resolve()

    conn = sqlite3.connect(temp_db)
    r = conn.execute("SELECT resolved FROM prediction_log WHERE fixture_id=3").fetchone()[0]
    conn.close()
    assert r == 1
