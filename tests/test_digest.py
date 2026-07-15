"""
Tests du digest quotidien : fenêtre temporelle, formatage, envoi email
(SMTP toujours mocké — aucun test ne touche un vrai serveur mail).
"""
import sqlite3
from unittest.mock import patch, MagicMock
from email import message_from_string
import club_value_finder as cvf


def _seed_digest_scenario(db_path):
    from datetime import datetime, timedelta
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE club_upcoming (
        fixture_id INTEGER PRIMARY KEY, league_id INTEGER, league_name TEXT, season INTEGER,
        date TEXT, round TEXT, home_team TEXT, away_team TEXT, home_id INTEGER, away_id INTEGER)""")
    soon = (datetime.now() + timedelta(hours=10)).strftime("%Y-%m-%d %H:%M")
    far = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d %H:%M")
    conn.execute("INSERT INTO club_upcoming VALUES (1,61,'Ligue 1',2026,?,'J1','Lyon','Marseille',80,81)", (soon,))
    conn.execute("INSERT INTO club_upcoming VALUES (2,61,'Ligue 1',2026,?,'J2','PSG','Nice',1,2)", (far,))
    conn.execute("CREATE TABLE club_dc_params (league_id INTEGER, team TEXT, alpha REAL, beta REAL,"
                 " PRIMARY KEY(league_id,team))")
    conn.execute("CREATE TABLE club_dc_global (league_id INTEGER PRIMARY KEY, gamma REAL, rho REAL,"
                 " nll REAL, n_matches INTEGER, trained_at TEXT)")
    conn.execute("INSERT INTO club_dc_params VALUES (61,'Lyon',1.5,0.4)")
    conn.execute("INSERT INTO club_dc_params VALUES (61,'Marseille',1.2,0.5)")
    conn.execute("INSERT INTO club_dc_global VALUES (61,1.3,-0.1,50.0,100,'2026-07-01')")
    conn.execute("CREATE TABLE club_odds_snapshots (fixture_id INTEGER, market TEXT, selection TEXT,"
                 " odds REAL, captured_at TEXT, PRIMARY KEY(fixture_id,market,selection,captured_at))")
    conn.execute("INSERT INTO club_odds_snapshots VALUES (1,'1N2','1',2.9,CURRENT_TIMESTAMP)")
    conn.execute("INSERT INTO club_odds_snapshots VALUES (1,'1N2','N',3.4,CURRENT_TIMESTAMP)")
    conn.execute("INSERT INTO club_odds_snapshots VALUES (1,'1N2','2',2.6,CURRENT_TIMESTAMP)")
    conn.commit()
    conn.close()


def test_build_digest_excludes_matches_outside_window(temp_db):
    _seed_digest_scenario(temp_db)
    values, any_matches = cvf.build_digest(within_hours=48, min_ev=0.0)
    assert any_matches is True
    assert all("PSG" not in v["match"] for v in values)  # hors fenêtre 48h
    assert any("Lyon" in v["match"] for v in values)


def test_build_digest_no_matches_in_window(temp_db):
    conn = sqlite3.connect(temp_db)
    conn.execute("""CREATE TABLE club_upcoming (
        fixture_id INTEGER PRIMARY KEY, league_id INTEGER, league_name TEXT, season INTEGER,
        date TEXT, round TEXT, home_team TEXT, away_team TEXT, home_id INTEGER, away_id INTEGER)""")
    conn.commit()
    conn.close()
    values, any_matches = cvf.build_digest(within_hours=48)
    assert values == [] and any_matches is False


def test_digest_text_format_empty_vs_populated():
    empty = cvf._format_digest_text([], "16/07/2026")
    assert "Aucune value" in empty
    populated = cvf._format_digest_text(
        [{"match": "Lyon vs Marseille", "market": "1N2", "selection": "1", "odds": 2.9,
          "p_model": 45.0, "ev": 30.5, "kelly_stake_pct": 4.0}], "16/07/2026")
    assert "Lyon vs Marseille" in populated and "+30.5%" in populated


def test_send_email_fails_cleanly_without_credentials(monkeypatch):
    monkeypatch.delenv("EMAIL_ADDRESS", raising=False)
    monkeypatch.delenv("EMAIL_APP_PASSWORD", raising=False)
    ok = cvf.send_email("sujet", "texte", "<p>html</p>", "dest@test.com")
    assert ok is False


def test_send_email_builds_correct_mime_message(monkeypatch):
    monkeypatch.setenv("EMAIL_ADDRESS", "tony@test.com")
    monkeypatch.setenv("EMAIL_APP_PASSWORD", "fake_app_password")
    with patch("smtplib.SMTP") as mock_smtp:
        instance = MagicMock()
        mock_smtp.return_value.__enter__.return_value = instance
        ok = cvf.send_email("Pitch digest", "corps texte", "<p>corps html</p>", "tonycoloricchio01@gmail.com")

    assert ok is True
    instance.starttls.assert_called_once()
    instance.login.assert_called_once_with("tony@test.com", "fake_app_password")
    raw = instance.sendmail.call_args[0][2]
    msg = message_from_string(raw)
    assert msg["Subject"] == "Pitch digest"
    assert msg["To"] == "tonycoloricchio01@gmail.com"
    parts = {p.get_content_type(): p.get_payload(decode=True).decode()
            for p in msg.walk() if p.get_content_type() in ("text/plain", "text/html")}
    assert "corps texte" in parts["text/plain"]
    assert "corps html" in parts["text/html"]


def test_digest_never_sends_when_no_matches(temp_db, monkeypatch, capsys):
    """cmd_digest doit s'arreter avant tout envoi si aucun match dans la fenetre."""
    conn = sqlite3.connect(temp_db)
    conn.execute("""CREATE TABLE club_upcoming (
        fixture_id INTEGER PRIMARY KEY, league_id INTEGER, league_name TEXT, season INTEGER,
        date TEXT, round TEXT, home_team TEXT, away_team TEXT, home_id INTEGER, away_id INTEGER)""")
    conn.commit()
    conn.close()

    with patch("smtplib.SMTP") as mock_smtp:
        import types
        args = types.SimpleNamespace(to="dest@test.com", hours="48", min_ev=None, dry_run=False)
        cvf.cmd_digest(args)
        mock_smtp.assert_not_called()
    assert "non envoyé" in capsys.readouterr().out
