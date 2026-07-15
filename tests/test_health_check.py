"""
Tests du script de contrôle de santé (health_check.py). Diagnostic
manuel, pas partie du pipeline critique — on vérifie surtout qu'il ne
plante jamais, base vide ou remplie (les sections systemctl/crontab
sont environnement-dépendantes, non testées ici).
"""
import sqlite3
import health_check as hc


def test_check_leagues_trained_empty_db_no_crash(temp_db, capsys):
    hc.check_leagues_trained()
    out = capsys.readouterr().out
    assert "JAMAIS entraînée" in out


def test_check_leagues_trained_reports_ok_when_trained_and_backtested(temp_db, capsys):
    conn = sqlite3.connect(temp_db)
    conn.execute("CREATE TABLE club_dc_global (league_id INTEGER PRIMARY KEY, gamma REAL, rho REAL,"
                 " nll REAL, n_matches INTEGER, trained_at TEXT)")
    conn.execute("INSERT INTO club_dc_global VALUES (61,1.2,-0.1,50,1700,'2026-07-15 10:00:00')")
    conn.execute("CREATE TABLE club_backtest (league_id INTEGER, test_season INTEGER, run_date TEXT,"
                 " n_matches INTEGER, accuracy REAL, brier REAL, brier_baseline REAL, log_loss REAL,"
                 " log_loss_baseline REAL, ece REAL, calibration_json TEXT)")
    conn.execute("INSERT INTO club_backtest VALUES (61,2025,'2026-07-15',295,.52,.6,.65,.7,.75,.02,'{}')")
    conn.commit()
    conn.close()
    hc.check_leagues_trained()
    out = capsys.readouterr().out
    assert "Ligue 1 : entraînée" in out and "backtestée" in out


def test_check_data_freshness_no_crash_on_missing_tables(temp_db, capsys):
    hc.check_data_freshness()
    out = capsys.readouterr().out
    assert "club_upcoming absente" in out


def test_check_prediction_tracker_flags_overdue(temp_db, capsys):
    from datetime import datetime, timedelta
    conn = sqlite3.connect(temp_db)
    conn.execute("""CREATE TABLE prediction_log (scope TEXT, fixture_id INTEGER, league_id INTEGER,
        home_team TEXT, away_team TEXT, kickoff TEXT, stage TEXT, method TEXT, xg_home REAL,
        xg_away REAL, p_home REAL, p_draw REAL, p_away REAL, p_over_15 REAL, p_over_25 REAL,
        p_under_25 REAL, p_btts_yes REAL, p_btts_no REAL, top_score TEXT, logged_at TEXT,
        resolved INTEGER DEFAULT 0, actual_home_score INTEGER, actual_away_score INTEGER,
        resolved_at TEXT, PRIMARY KEY(scope,fixture_id))""")
    overdue = (datetime.now() - timedelta(hours=10)).strftime("%Y-%m-%d %H:%M")
    conn.execute("""INSERT INTO prediction_log (scope,fixture_id,league_id,home_team,away_team,
        kickoff,method,resolved) VALUES ('club',1,61,'A','B',?,'dixon_coles_club',0)""", (overdue,))
    conn.commit()
    conn.close()
    hc.check_prediction_tracker()
    out = capsys.readouterr().out
    assert "jamais résolus" in out
