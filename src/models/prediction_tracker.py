"""
Journal des prédictions de Pitch — pour fermer la boucle prédiction →
résultat réel → conclusions, au-delà du backtest hors-ligne.

Trois commandes :

  log --scope club --leagues big5     # snapshot des prédictions à venir
  log --scope selections              # idem pour la CDM (data/fixtures.json)
  resolve                             # remplit le score réel des matchs joués
  report [--scope club|selections|all] [--since AAAA-MM-JJ] [--league ID]

Principe : 'log' capture l'état de la prédiction à chaque exécution
(clé (scope, fixture_id) — donc écrasée jusqu'au coup d'envoi, capturant
la dernière version avant le match si lancée régulièrement en cron,
idéalement juste après 'auto'/'club-auto' pour inclure compos/absences).
'resolve' n'invente rien : club → club_matches (déjà synchronisé) ;
sélections → /fixtures?id= en direct (aucune dépendance à un CSV qui
pourrait retarder). 'report' réutilise telles quelles les fonctions de
métriques de backtest.py (Brier, log-loss, calibration) — même
définition partout dans le projet, pas une deuxième formule à maintenir.
"""
import os
import sys
import json
import sqlite3
import argparse

SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SRC_DIR)
sys.path.insert(0, os.path.join(SRC_DIR, "api"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
from sync_api_football import (
    resolve_leagues, league_display_name, find_fixture_id, _get,
    FIXTURES_PATH, _load_json,
)
from backtest import brier_multiclass, log_loss, accuracy, baseline_metrics, calibration_table
import service

PROJECT_ROOT = os.path.dirname(SRC_DIR)
DB_PATH = os.path.join(PROJECT_ROOT, "data/db/foot_stats.db")

RESOLVE_BUFFER_MIN = 150  # marge après le coup d'envoi avant de tenter la résolution


def _connect():
    return sqlite3.connect(DB_PATH)


def _ensure_table():
    conn = _connect()
    conn.execute("""CREATE TABLE IF NOT EXISTS prediction_log (
        scope TEXT, fixture_id INTEGER, league_id INTEGER,
        home_team TEXT, away_team TEXT, kickoff TEXT, stage TEXT,
        method TEXT, xg_home REAL, xg_away REAL,
        p_home REAL, p_draw REAL, p_away REAL,
        p_over_15 REAL, p_over_25 REAL, p_under_25 REAL,
        p_btts_yes REAL, p_btts_no REAL, top_score TEXT,
        logged_at TEXT DEFAULT CURRENT_TIMESTAMP,
        resolved INTEGER DEFAULT 0,
        actual_home_score INTEGER, actual_away_score INTEGER,
        resolved_at TEXT,
        PRIMARY KEY (scope, fixture_id))""")
    conn.commit()
    return conn


def _row_from_prediction(scope, fixture_id, league_id, home, away, kickoff, stage, pred):
    m = pred["markets"]
    top_score = pred["top_scorelines"][0]["score"] if pred.get("top_scorelines") else None
    return (scope, fixture_id, league_id, home, away, kickoff, stage, pred["method"],
            pred["xg_home"], pred["xg_away"],
            m["home_win"] / 100, m["draw"] / 100, m["away_win"] / 100,
            m["over_1_5"] / 100, m["over_2_5"] / 100, m["under_2_5"] / 100,
            m["btts_yes"] / 100, m["btts_no"] / 100, top_score)


# ─────────────────────────────────────────────────────────────────────────────
# LOG
# ─────────────────────────────────────────────────────────────────────────────
def log_club(leagues_spec):
    conn = _ensure_table()
    n = 0
    for lg in resolve_leagues(leagues_spec):
        rows = conn.execute("""SELECT fixture_id, home_team, away_team, date, round
            FROM club_upcoming WHERE league_id=?""", (lg,)).fetchall()
        for fid, home, away, kickoff, rnd in rows:
            pred = service.club_predict(lg, home, away)
            if pred is None:
                continue
            conn.execute("""INSERT OR REPLACE INTO prediction_log
                (scope, fixture_id, league_id, home_team, away_team, kickoff, stage,
                 method, xg_home, xg_away, p_home, p_draw, p_away,
                 p_over_15, p_over_25, p_under_25, p_btts_yes, p_btts_no, top_score)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                _row_from_prediction("club", fid, lg, home, away, kickoff, rnd, pred))
            n += 1
    conn.commit()
    conn.close()
    print(f"💾 {n} prédiction(s) club journalisée(s).")


def log_selections(league=1, season=2026):
    conn = _ensure_table()
    fixtures = _load_json(FIXTURES_PATH, {}).get("fixtures", [])
    n = 0
    for f in fixtures:
        home, away, kickoff, stage = f["home"], f["away"], f["date"], f.get("stage")
        pred = service.predict(home, away, neutral=True)
        if pred is None:
            continue
        fid = find_fixture_id(home, away, kickoff[:10], league, season)
        if fid is None:
            print(f"   ⚠️  {home} vs {away} : fixture_id introuvable, ignoré.")
            continue
        conn.execute("""INSERT OR REPLACE INTO prediction_log
            (scope, fixture_id, league_id, home_team, away_team, kickoff, stage,
             method, xg_home, xg_away, p_home, p_draw, p_away,
             p_over_15, p_over_25, p_under_25, p_btts_yes, p_btts_no, top_score)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            _row_from_prediction("selections", fid, league, home, away, kickoff, stage, pred))
        n += 1
    conn.commit()
    conn.close()
    print(f"💾 {n} prédiction(s) sélections journalisée(s).")


# ─────────────────────────────────────────────────────────────────────────────
# RESOLVE
# ─────────────────────────────────────────────────────────────────────────────
def resolve():
    from datetime import datetime, timedelta
    conn = _ensure_table()
    pending = conn.execute("""SELECT scope, fixture_id, league_id, home_team, away_team, kickoff
        FROM prediction_log WHERE resolved=0""").fetchall()

    now = datetime.now()
    n_resolved, n_pending = 0, 0
    for scope, fid, lg, home, away, kickoff in pending:
        try:
            ko = datetime.strptime(kickoff[:16], "%Y-%m-%d %H:%M")
        except Exception:
            continue
        if now < ko + timedelta(minutes=RESOLVE_BUFFER_MIN):
            n_pending += 1
            continue

        hs, as_ = None, None
        if scope == "club":
            row = conn.execute("""SELECT home_score, away_score FROM club_matches
                WHERE fixture_id=? AND status IN ('FT','AET','PEN')""", (fid,)).fetchone()
            if row:
                hs, as_ = row

        if hs is None:  # pas trouvé en base (ou scope selections) → vérifie en direct
            resp = _get("/fixtures", {"id": fid})
            if resp:
                m = resp[0]
                status = (m.get("fixture", {}).get("status", {}) or {}).get("short", "")
                if status in ("FT", "AET", "PEN"):
                    g = m.get("goals", {}) or {}
                    hs, as_ = g.get("home"), g.get("away")

        if hs is None or as_ is None:
            n_pending += 1
            continue

        conn.execute("""UPDATE prediction_log SET resolved=1, actual_home_score=?,
            actual_away_score=?, resolved_at=CURRENT_TIMESTAMP
            WHERE scope=? AND fixture_id=?""", (hs, as_, scope, fid))
        n_resolved += 1
        print(f"   ✅ {home} {hs}-{as_} {away}")

    conn.commit()
    conn.close()
    print(f"\n💾 {n_resolved} match(s) résolu(s), {n_pending} en attente (pas encore joués "
          f"ou trop récents — marge de {RESOLVE_BUFFER_MIN} min après coup d'envoi).")


# ─────────────────────────────────────────────────────────────────────────────
# REPORT
# ─────────────────────────────────────────────────────────────────────────────
def _binary_brier(p, y):
    return float(np.mean((np.asarray(p) - np.asarray(y)) ** 2))


def build_report(scope=None, since=None, league=None):
    conn = _connect()
    try:
        q = "SELECT * FROM prediction_log WHERE resolved=1"
        params = []
        if scope and scope != "all":
            q += " AND scope=?"; params.append(scope)
        if since:
            q += " AND kickoff>=?"; params.append(since)
        if league:
            q += " AND league_id=?"; params.append(league)
        df = pd.read_sql_query(q, conn, params=params)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    if df.empty:
        return None

    df["outcome"] = np.select(
        [df.actual_home_score > df.actual_away_score, df.actual_home_score == df.actual_away_score],
        [0, 1], default=2)
    dc_df = df.rename(columns={"p_home": "p_home", "p_draw": "p_draw", "p_away": "p_away"})

    total_goals = df.actual_home_score + df.actual_away_score
    over_25_actual = (total_goals > 2.5).astype(float)
    btts_actual = ((df.actual_home_score > 0) & (df.actual_away_score > 0)).astype(float)

    _, base_brier, base_ll = baseline_metrics(dc_df)
    cal = calibration_table(dc_df)
    ece = float(np.average(np.abs(cal["proba_moy"] - cal["freq_reelle"]), weights=cal["n"])) \
        if not cal.empty else None

    return {
        "n": len(df),
        "accuracy": accuracy(dc_df),
        "brier": brier_multiclass(dc_df),
        "brier_baseline": base_brier,
        "log_loss": log_loss(dc_df),
        "ece": ece,
        "over_25_brier": _binary_brier(df.p_over_25, over_25_actual),
        "over_25_hit_rate": float((over_25_actual == (df.p_over_25 > 0.5)).mean()),
        "btts_brier": _binary_brier(df.p_btts_yes, btts_actual),
        "btts_hit_rate": float((btts_actual == (df.p_btts_yes > 0.5)).mean()),
        "by_method": df.groupby("method").size().to_dict(),
    }


def print_report(rep, title):
    if rep is None:
        print(f"\n{title} : aucun match résolu sur cette sélection.")
        return
    gain = (rep["brier_baseline"] - rep["brier"]) / rep["brier_baseline"] * 100 \
        if rep["brier_baseline"] is not None and rep["brier_baseline"] > 0 else None
    gain_str = f"gain {gain:+.1f}%" if gain is not None else "gain n/d (échantillon trop petit)"
    print(f"\n{'=' * 70}\n{title} — {rep['n']} match(s) résolu(s)\n{'=' * 70}")
    print(f"   1N2      précision {rep['accuracy']*100:.1f}% · Brier {rep['brier']:.4f} "
          f"(naïf {rep['brier_baseline']:.4f}, {gain_str}) · log-loss {rep['log_loss']:.4f}"
          + (f" · ECE {rep['ece']*100:.2f}%" if rep["ece"] is not None else ""))
    print(f"   +2.5 buts  Brier {rep['over_25_brier']:.4f} · taux de bon appel "
          f"{rep['over_25_hit_rate']*100:.1f}%")
    print(f"   BTTS       Brier {rep['btts_brier']:.4f} · taux de bon appel "
          f"{rep['btts_hit_rate']*100:.1f}%")
    if len(rep["by_method"]) > 1:
        print(f"   Répartition par méthode : {rep['by_method']}")


# ─────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("log")
    pl.add_argument("--scope", choices=["club", "selections"], required=True)
    pl.add_argument("--leagues", default="big5", help="Pour --scope club uniquement")
    pl.add_argument("--league", default=1, type=int, help="Pour --scope selections (défaut CDM=1)")
    pl.add_argument("--season", default=2026, type=int)

    sub.add_parser("resolve")

    pr = sub.add_parser("report")
    pr.add_argument("--scope", choices=["club", "selections", "all"], default="all")
    pr.add_argument("--since", default=None, help="AAAA-MM-JJ")
    pr.add_argument("--league", default=None, type=int)

    args = ap.parse_args()
    if args.cmd == "log":
        if args.scope == "club":
            log_club(args.leagues)
        else:
            log_selections(args.league, args.season)
    elif args.cmd == "resolve":
        resolve()
    else:
        rep = build_report(args.scope, args.since, args.league)
        print_report(rep, f"RAPPORT — scope={args.scope}"
                          + (f" · depuis {args.since}" if args.since else "")
                          + (f" · ligue {args.league}" if args.league else ""))


if __name__ == "__main__":
    main()
