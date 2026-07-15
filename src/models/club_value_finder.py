"""
Écart modèle/marché pour les matchs de club — couche privée, CLI
uniquement (jamais d'endpoint API, jamais de page web, jamais de lien
dans la nav). Réutilise le moteur EV/Kelly existant (value_finder.py,
jusque-là orphelin) plutôt que d'en construire un second : mêmes seuils,
même méthode de retrait de marge, même format de sortie que côté
sélections.

  python src/models/club_value_finder.py scan --leagues big5

Prérequis : le modèle de la ligue doit être entraîné (club_dixon_coles.py
train) et les cotes capturées (sync_api_football.py club-odds) — cette
dernière étape ne peut pas être rattrapée après coup (rétention API de
7 jours, cf. sync_api_football.py).
"""
import os
import sys
import sqlite3
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import value_finder as vf

SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SRC_DIR)
sys.path.insert(0, os.path.join(SRC_DIR, "api"))
from sync_api_football import resolve_leagues, league_display_name
import service

PROJECT_ROOT = os.path.dirname(SRC_DIR)
DB_PATH = os.path.join(PROJECT_ROOT, "data/db/foot_stats.db")


def _connect():
    return sqlite3.connect(DB_PATH)


def _adapt_club_markets(pred):
    """
    club_predict() renvoie des pourcentages sous des clés propres au
    club (home_win/away_win) ; value_finder attend des fractions [0,1]
    sous les clés qu'il partage avec le moteur sélections (home/away).
    """
    m = pred["markets"]
    return {
        "home": m["home_win"] / 100, "draw": m["draw"] / 100, "away": m["away_win"] / 100,
        "over_1_5": m["over_1_5"] / 100, "over_2_5": m["over_2_5"] / 100,
        "under_2_5": m["under_2_5"] / 100,
        "btts_yes": m["btts_yes"] / 100, "btts_no": m["btts_no"] / 100,
    }


def latest_odds_for_fixture(fixture_id):
    """
    Dernière capture par (marché, sélection) — pas tout l'historique.
    {"1N2": {"1": 2.1, ...}, ...} ou {} si rien capturé.
    """
    conn = _connect()
    try:
        rows = conn.execute("""
            SELECT market, selection, odds FROM club_odds_snapshots o
            WHERE fixture_id=? AND captured_at = (
                SELECT MAX(captured_at) FROM club_odds_snapshots
                WHERE fixture_id=o.fixture_id AND market=o.market AND selection=o.selection
            )""", (fixture_id,)).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return {}
    conn.close()
    out = {}
    for market, sel, odds in rows:
        out.setdefault(market, {})[sel] = odds
    return out


def _ensure_log_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS club_value_log (
        fixture_id INTEGER, league_id INTEGER, match TEXT, market TEXT,
        selection TEXT, odds REAL, p_model REAL, p_fair REAL,
        edge REAL, ev REAL, kelly_stake_pct REAL,
        detected_at TEXT DEFAULT CURRENT_TIMESTAMP)""")


def scan_league(league_id, min_ev=None, log=True, selections=False, within_hours=None):
    """
    Renvoie la liste des values détectées pour tous les matchs à venir
    de la ligue ayant à la fois une prédiction et des cotes capturées.
    Persiste dans club_value_log si log=True.

    selections=True : utilise le modèle sélections (service.predict,
    terrain neutre) au lieu du modèle club par championnat — pour les
    matchs internationaux (CDM), stockés sous league_id=1 dans
    club_upcoming comme n'importe quelle autre "ligue".

    within_hours : ne considère que les matchs dont le coup d'envoi est
    dans les N prochaines heures (digest quotidien).
    """
    if min_ev is not None:
        vf.EV_MIN = min_ev

    conn = _connect()
    try:
        if within_hours is not None:
            from datetime import datetime, timedelta
            horizon = (datetime.now() + timedelta(hours=within_hours)).strftime("%Y-%m-%d %H:%M")
            rows = conn.execute("""SELECT fixture_id, home_team, away_team
                FROM club_upcoming WHERE league_id=? AND date <= ? ORDER BY date""",
                (league_id, horizon)).fetchall()
        else:
            rows = conn.execute("""SELECT fixture_id, home_team, away_team
                FROM club_upcoming WHERE league_id=? ORDER BY date""", (league_id,)).fetchall()
    except sqlite3.OperationalError:
        rows = []
    conn.close()

    all_values = []
    for fid, home, away in rows:
        odds = latest_odds_for_fixture(fid)
        if not odds:
            continue
        if selections:
            pred = service.predict(home, away, neutral=True)
        else:
            pred = service.club_predict(league_id, home, away)
        if pred is None:
            continue
        model_probs = _adapt_club_markets(pred)
        match_name = f"{home} vs {away}"
        values = vf.find_values_for_match(match_name, model_probs, odds)
        for v in values:
            v["fixture_id"] = fid
            v["league_id"] = league_id
        all_values += values

    if log and all_values:
        conn = _connect()
        _ensure_log_table(conn)
        for v in all_values:
            conn.execute("""INSERT INTO club_value_log
                (fixture_id, league_id, match, market, selection, odds,
                 p_model, p_fair, edge, ev, kelly_stake_pct)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (
                v["fixture_id"], v["league_id"], v["match"], v["market"],
                v["selection"], v["odds"], v["p_model"], v["p_fair"],
                v["edge"], v["ev"], v["kelly_stake_pct"]))
        conn.commit()
        conn.close()

    return all_values


# ─────────────────────────────────────────────────────────────────────────────
# DIGEST QUOTIDIEN PAR EMAIL
# ─────────────────────────────────────────────────────────────────────────────
def _all_trained_league_ids():
    conn = _connect()
    try:
        rows = conn.execute("SELECT DISTINCT league_id FROM club_dc_global").fetchall()
    except sqlite3.OperationalError:
        rows = []
    conn.close()
    return [r[0] for r in rows]


def build_digest(within_hours=48, min_ev=None):
    """
    Scanne toutes les ligues club entraînées + les sélections (CDM,
    league_id=1) sur la fenêtre donnée. Renvoie (values, any_matches) —
    any_matches indique s'il y avait au moins un match à examiner (même
    sans value trouvée), pour décider d'envoyer ou non le digest.
    """
    leagues = _all_trained_league_ids()
    if 1 not in leagues:
        leagues.append(1)  # CDM : toujours tenté, même sans entraînement club

    all_values, any_matches = [], False
    for lg in leagues:
        conn = _connect()
        try:
            n = conn.execute("""SELECT COUNT(*) FROM club_upcoming
                WHERE league_id=? AND date <= datetime('now', ?)""",
                (lg, f"+{within_hours} hours")).fetchone()[0]
        except sqlite3.OperationalError:
            n = 0
        conn.close()
        if n == 0:
            continue
        any_matches = True
        vals = scan_league(lg, min_ev=min_ev, log=True, selections=(lg == 1),
                           within_hours=within_hours)
        all_values += vals
    return all_values, any_matches


def _format_digest_text(values, date_str):
    if not values:
        return f"Digest Pitch — {date_str}\n\nAucune value détectée sur les matchs du jour."
    lines = [f"Digest Pitch — {date_str}", f"{len(values)} value(s) détectée(s)\n"]
    for v in sorted(values, key=lambda x: -x["ev"]):
        lines.append(f"{v['match']} — {v['market']} {v['selection']} @ {v['odds']:.2f} "
                    f"| modèle {v['p_model']:.1f}% | EV {v['ev']:+.1f}% | Kelly {v['kelly_stake_pct']:.2f}%")
    lines.append("\nOutil d'aide à la décision personnel — vérifie toujours avant de jouer.")
    return "\n".join(lines)


def _format_digest_html(values, date_str):
    if not values:
        return (f"<h2>Digest Pitch — {date_str}</h2>"
               f"<p>Aucune value détectée sur les matchs du jour.</p>")
    rows_html = ""
    for v in sorted(values, key=lambda x: -x["ev"]):
        rows_html += f"""<tr>
            <td style="padding:6px 10px;border-bottom:1px solid #333;">{v['match']}</td>
            <td style="padding:6px 10px;border-bottom:1px solid #333;">{v['market']} {v['selection']}</td>
            <td style="padding:6px 10px;border-bottom:1px solid #333;text-align:right;">{v['odds']:.2f}</td>
            <td style="padding:6px 10px;border-bottom:1px solid #333;text-align:right;">{v['p_model']:.1f}%</td>
            <td style="padding:6px 10px;border-bottom:1px solid #333;text-align:right;color:#22C77E;">{v['ev']:+.1f}%</td>
            <td style="padding:6px 10px;border-bottom:1px solid #333;text-align:right;">{v['kelly_stake_pct']:.2f}%</td>
        </tr>"""
    return f"""
    <div style="font-family:sans-serif;max-width:700px;">
      <h2>Digest Pitch — {date_str}</h2>
      <p>{len(values)} value(s) détectée(s) — triées par espérance décroissante.</p>
      <table style="border-collapse:collapse;width:100%;font-size:14px;">
        <tr style="background:#111;color:#aaa;">
          <th style="padding:6px 10px;text-align:left;">Match</th>
          <th style="padding:6px 10px;text-align:left;">Sélection</th>
          <th style="padding:6px 10px;text-align:right;">Cote</th>
          <th style="padding:6px 10px;text-align:right;">Modèle</th>
          <th style="padding:6px 10px;text-align:right;">EV</th>
          <th style="padding:6px 10px;text-align:right;">Kelly</th>
        </tr>
        {rows_html}
      </table>
      <p style="color:#888;font-size:12px;margin-top:16px;">
        Outil d'aide à la décision personnel — vérifie toujours avant de jouer.
      </p>
    </div>"""


def send_email(subject, text_body, html_body, to_addr):
    """
    Envoi via SMTP (Gmail par défaut). Identifiants dans .env :
    EMAIL_ADDRESS (expéditeur) + EMAIL_APP_PASSWORD (mot de passe
    d'application Google — pas le mot de passe du compte).
    """
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    sender = os.environ.get("EMAIL_ADDRESS")
    password = os.environ.get("EMAIL_APP_PASSWORD")
    if not sender or not password:
        print("❌ EMAIL_ADDRESS / EMAIL_APP_PASSWORD absents du .env — envoi impossible.")
        return False

    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_addr
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, [to_addr], msg.as_string())
    return True


def cmd_digest(args):
    from datetime import date
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    values, any_matches = build_digest(within_hours=int(args.hours), min_ev=args.min_ev)
    date_str = date.today().strftime("%d/%m/%Y")

    if not any_matches:
        print(f"⏸  Aucun match dans les {args.hours}h — digest non envoyé.")
        return

    text_body = _format_digest_text(values, date_str)
    html_body = _format_digest_html(values, date_str)
    subject = f"Pitch — {len(values)} value(s) le {date_str}" if values else f"Pitch — rien à signaler le {date_str}"

    if args.dry_run:
        print(text_body)
        print(f"\n[dry-run] Email non envoyé (aurait été envoyé à {args.to}).")
        return

    ok = send_email(subject, text_body, html_body, args.to)
    if ok:
        print(f"✅ Digest envoyé à {args.to} ({len(values)} value(s)).")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    ps = sub.add_parser("scan")
    ps.add_argument("--leagues", default="big5")
    ps.add_argument("--min-ev", type=float, default=None,
                    help="Seuil EV en fraction (0.05 = 5%%), défaut = celui de value_finder.py")
    ps.add_argument("--bankroll", type=float, default=None)
    ps.add_argument("--no-log", action="store_true")
    ps.add_argument("--selections", action="store_true",
                    help="Modèle sélections (terrain neutre) au lieu du modèle club — pour CDM/international")

    pd = sub.add_parser("digest")
    pd.add_argument("--to", required=True, help="Adresse email destinataire")
    pd.add_argument("--hours", default="48", help="Fenêtre en heures (défaut 48)")
    pd.add_argument("--min-ev", type=float, default=None)
    pd.add_argument("--dry-run", action="store_true", help="Affiche sans envoyer")

    args = ap.parse_args()

    if args.cmd == "digest":
        cmd_digest(args)
        return

    leagues = resolve_leagues(args.leagues)
    all_values = []
    for lg in leagues:
        print(f"\n════ {league_display_name(lg)} ════")
        vals = scan_league(lg, min_ev=args.min_ev, log=not args.no_log, selections=args.selections)
        if not vals:
            print("   Aucune cote capturée, aucun modèle entraîné, ou aucune value au-dessus du seuil.")
        all_values += vals

    if all_values:
        vf.print_values(all_values, bankroll=args.bankroll)


if __name__ == "__main__":
    main()
