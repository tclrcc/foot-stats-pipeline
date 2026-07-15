"""
Contrôle de santé complet de Pitch — une seule commande à lancer avant
de couper l'ordinateur pour la nuit, ou le matin en arrivant.

  python src/health_check.py

Ne modifie rien (lecture seule partout), safe à lancer n'importe quand.
Sections : dépôt git, services systemd, fraîcheur des données,
championnats entraînés vs enregistrés, backtests, cotes/digest,
journal des prédictions, suite de tests.
"""
import os
import sys
import sqlite3
import subprocess
from datetime import datetime, timedelta

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SRC_DIR)
sys.path.insert(0, os.path.join(SRC_DIR, "models"))
sys.path.insert(0, os.path.join(SRC_DIR, "api"))

from sync_api_football import BIG5, is_cup_competition, league_display_name, _load_extra_leagues

PROJECT_ROOT = os.path.dirname(SRC_DIR)
DB_PATH = os.path.join(PROJECT_ROOT, "data/db/foot_stats.db")

OK, WARN, FAIL = "✅", "⚠️ ", "❌"


def _connect():
    return sqlite3.connect(DB_PATH)


def _run(cmd):
    try:
        r = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=15)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


def section(title):
    print(f"\n{'─' * 60}\n{title}\n{'─' * 60}")


# ─────────────────────────────────────────────────────────────────────────────
def check_git():
    section("DÉPÔT GIT")
    code, out, err = _run(["git", "status", "--porcelain"])
    if out:
        print(f"{WARN} Modifications locales non commitées :")
        print("   " + "\n   ".join(out.splitlines()[:10]))
    else:
        print(f"{OK} Aucune modification locale en attente.")

    _run(["git", "fetch", "origin", "-q"])
    code, ahead_behind, _ = _run(["git", "rev-list", "--left-right", "--count", "HEAD...origin/main"])
    if ahead_behind:
        ahead, behind = ahead_behind.split()
        if ahead == "0" and behind == "0":
            print(f"{OK} À jour avec origin/main.")
        else:
            if ahead != "0":
                print(f"{WARN} {ahead} commit(s) local/locaux non poussé(s) — pense à 'git push'.")
            if behind != "0":
                print(f"{WARN} {behind} commit(s) sur origin/main non récupéré(s) — 'git pull'.")


def check_services():
    section("SERVICES")
    for svc in ("footstats-api", "footstats-web", "nginx"):
        code, out, _ = _run(["systemctl", "is-active", svc])
        print(f"{OK if out == 'active' else FAIL} {svc} : {out or 'introuvable'}")


def check_data_freshness():
    section("FRAÎCHEUR DES DONNÉES")
    fixtures_path = os.path.join(PROJECT_ROOT, "data/fixtures.json")
    if os.path.exists(fixtures_path):
        age_h = (datetime.now().timestamp() - os.path.getmtime(fixtures_path)) / 3600
        flag = OK if age_h < 24 else WARN
        print(f"{flag} data/fixtures.json (CDM) modifié il y a {age_h:.0f}h")
    else:
        print(f"{WARN} data/fixtures.json absent.")

    conn = _connect()
    try:
        n_up = conn.execute("SELECT COUNT(*) FROM club_upcoming").fetchone()[0]
        soonest = conn.execute("SELECT MIN(date) FROM club_upcoming").fetchone()[0]
        print(f"{OK if n_up else WARN} club_upcoming : {n_up} match(s)"
              + (f", le plus proche le {soonest}" if soonest else ""))
    except sqlite3.OperationalError:
        print(f"{WARN} Table club_upcoming absente — lance 'sync_api_football.py upcoming'.")

    try:
        last_odds = conn.execute("SELECT MAX(captured_at) FROM club_odds_snapshots").fetchone()[0]
        if last_odds:
            age_h = (datetime.now() - datetime.strptime(last_odds[:19], "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600
            flag = OK if age_h < 24 else WARN
            print(f"{flag} Dernière capture de cotes il y a {age_h:.0f}h")
        else:
            print(f"{WARN} Aucune cote capturée pour l'instant.")
    except sqlite3.OperationalError:
        print(f"{WARN} Table club_odds_snapshots absente — 'club-odds' jamais lancé.")
    conn.close()


def check_leagues_trained():
    section("CHAMPIONNATS : ENREGISTRÉS vs ENTRAÎNÉS vs BACKTESTÉS")
    registry = _load_extra_leagues()
    all_leagues = {lid: league_display_name(lid) for lid in BIG5}
    for alias, v in registry.items():
        if v.get("id") and v.get("type") != "cup":
            all_leagues[v["id"]] = v.get("name", alias)

    conn = _connect()
    try:
        trained = dict(conn.execute("SELECT league_id, trained_at FROM club_dc_global").fetchall())
    except sqlite3.OperationalError:
        trained = {}
    try:
        backtested = dict(conn.execute(
            "SELECT league_id, MAX(run_date) FROM club_backtest GROUP BY league_id").fetchall())
    except sqlite3.OperationalError:
        backtested = {}
    conn.close()

    for lid, name in sorted(all_leagues.items(), key=lambda x: x[1]):
        if lid not in trained:
            print(f"{WARN} {name} : enregistrée mais JAMAIS entraînée — "
                  f"'club_dixon_coles.py train --league {lid}'")
        elif lid not in backtested:
            print(f"{WARN} {name} : entraînée ({trained[lid][:10]}) mais jamais backtestée — "
                  f"'club_dixon_coles.py backtest --league {lid} --season <dernière saison finie>'")
        else:
            print(f"{OK} {name} : entraînée {trained[lid][:10]}, backtestée {backtested[lid]}")


def check_prediction_tracker():
    section("JOURNAL DES PRÉDICTIONS")
    conn = _connect()
    try:
        total = conn.execute("SELECT COUNT(*) FROM prediction_log").fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM prediction_log WHERE resolved=0").fetchone()[0]
        overdue = conn.execute("""SELECT COUNT(*) FROM prediction_log
            WHERE resolved=0 AND kickoff < datetime('now', '-6 hours')""").fetchone()[0]
        print(f"{OK} {total} prédiction(s) journalisée(s), {pending} en attente de résultat.")
        if overdue:
            print(f"{WARN} {overdue} match(s) terminés depuis >6h jamais résolus — lance 'resolve'.")
    except sqlite3.OperationalError:
        print(f"{WARN} Table prediction_log absente — 'prediction_tracker.py log' jamais lancé.")
    conn.close()


def check_cron():
    section("CRON")
    code, out, _ = _run(["crontab", "-l"])
    if not out:
        print(f"{WARN} Aucune tâche cron configurée (ou crontab illisible).")
        return
    expected = ["upcoming", "auto", "club-auto", "club-odds", "digest",
               "results", "train", "prediction_tracker"]
    for kw in expected:
        found = kw in out
        print(f"{OK if found else WARN} Tâche mentionnant '{kw}' {'trouvée' if found else 'absente du crontab'}")


def check_tests():
    section("SUITE DE TESTS")
    code, out, err = _run([sys.executable, "-m", "pytest", "tests/"])
    tail = (out or err).strip().splitlines()
    summary = tail[-1] if tail else "(pas de sortie)"
    print(f"{OK if code == 0 else FAIL} {summary}")
    if code != 0:
        print("   " + "\n   ".join(tail[-15:]))


def main():
    print("🩺 CONTRÔLE DE SANTÉ PITCH —", datetime.now().strftime("%d/%m/%Y %H:%M"))
    check_git()
    check_services()
    check_data_freshness()
    check_leagues_trained()
    check_prediction_tracker()
    check_cron()
    check_tests()
    print("\n" + "═" * 60)
    print("Terminé. Les ⚠️  ne sont pas forcément des problèmes (ex. hors")
    print("saison) — regarde ce qui te concerne ce soir.")


if __name__ == "__main__":
    main()
