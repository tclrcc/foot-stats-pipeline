"""
Dixon-Coles par championnat de clubs.

Réutilise le moteur mathématique de dixon_coles.py (MLE, correction ρ,
décroissance temporelle) mais entraîné sur club_matches, ligue par ligue,
avec l'avantage du terrain réel (γ estimé par championnat — plus de
terrain neutre permanent comme en Coupe du monde).

CLI :
  python src/models/club_dixon_coles.py train    --league 61        # ou big5
  python src/models/club_dixon_coles.py backtest --league 61 --season 2025

Tables : club_dc_params(league_id, team, alpha, beta)
         club_dc_global(league_id, gamma, rho, nll, n_matches, trained_at)
         club_backtest(league_id, test_season, run_date, n_matches,
                       accuracy, brier, brier_baseline, log_loss,
                       log_loss_baseline, ece, calibration_json)
"""

import os
import sys
import json
import sqlite3
import argparse

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dixon_coles as dc
from backtest import brier_multiclass, log_loss, accuracy, baseline_metrics, calibration_table

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sync_api_football import is_cup_competition, resolve_leagues, league_display_name

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(PROJECT_ROOT, "data/db/foot_stats.db")

MIN_MATCHES_PER_TEAM = 10
REFIT_DAYS = 30

# Paires division haute <-> division basse dont les DEUX niveaux sont
# enregistrés dans le registre (data/leagues.json ou big5) : un promu
# fraîchement monté n'a souvent que quelques matchs dans sa nouvelle
# division, insuffisant pour l'estimer (MIN_MATCHES_PER_TEAM). Plutôt
# que de l'exclure entièrement du modèle jusqu'à accumuler 10 matchs,
# on emprunte ses paramètres à l'autre division tant qu'ils manquent
# — c'est une ESTIMATION explicitement marquée (colonne source_league_id
# dans club_dc_params), jamais confondue avec un ajustement complet.
TIER_LINKS = {61: 62, 62: 61, 39: 40, 40: 39, 140: 141, 141: 140}


def _connect():
    return sqlite3.connect(DB_PATH)


# ─────────────────────────────────────────────────────────────────────────────
# CORPUS
# ─────────────────────────────────────────────────────────────────────────────
def load_club_corpus(league_id, before=None):
    """Matchs terminés de la ligue (toutes saisons importées), neutral=False."""
    conn = _connect()
    df = pd.read_sql_query("""
        SELECT date, home_team, away_team, home_score, away_score
        FROM club_matches
        WHERE league_id = ?
        ORDER BY date ASC
    """, conn, params=(league_id,))
    conn.close()
    if before is not None:
        df = df[df["date"] < str(before)]
    df["date"] = pd.to_datetime(df["date"])
    df["neutral"] = 0
    return df


# ─────────────────────────────────────────────────────────────────────────────
# ENTRAÎNEMENT
# ─────────────────────────────────────────────────────────────────────────────
def train_league(league_id, as_of=None, save=True, verbose=True):
    if is_cup_competition(league_id):
        print(f"❌ Ligue {league_id} : compétition à phases mixtes (groupes + "
              f"élimination directe, écarts de niveau, peu de matchs/équipe). "
              f"Le classement recalculé et le Dixon-Coles n'ont pas de sens "
              f"pour ce format — entraînement refusé. results/topplayers "
              f"restent utilisables normalement.")
        return None
    df = load_club_corpus(league_id)
    if df.empty:
        print(f"❌ Aucun match pour la ligue {league_id} — lance d'abord "
              f"'python src/sync_api_football.py results'.")
        return None

    # Équipes qui seront exclues par filter_teams (< MIN_MATCHES_PER_TEAM
    # dans CETTE ligue) — calculé avant filtrage pour tenter un emprunt
    # inter-division sur celles-ci.
    appearances = pd.concat([df["home_team"], df["away_team"]])
    counts = appearances.value_counts()
    under_threshold = set(counts[counts < MIN_MATCHES_PER_TEAM].index)

    df = dc.filter_teams(df, min_matches=MIN_MATCHES_PER_TEAM)
    if verbose:
        print(f"📚 Corpus ligue {league_id} : {len(df)} matchs, "
              f"{len(set(df['home_team']) | set(df['away_team']))} équipes")
    team_params, gamma, rho, nll = dc.fit(df, as_of=as_of, verbose=verbose)
    team_params["source_league_id"] = None  # ajustées dans CETTE ligue

    borrowed = _borrow_cross_tier(league_id, under_threshold, team_params, verbose=verbose)
    if not borrowed.empty:
        team_params = pd.concat([team_params, borrowed], ignore_index=True)

    if save:
        _save_league(league_id, team_params, gamma, rho, nll, len(df))
        if verbose:
            top = team_params.sort_values("alpha", ascending=False).head(3)
            print(f"✅ γ (avantage terrain) = {gamma:.3f} · ρ = {rho:.3f}")
            print("   Top attaques :", ", ".join(f"{r.team} (α={r.alpha:.2f})" for r in top.itertuples()))
    return team_params, gamma, rho


def _borrow_cross_tier(league_id, under_threshold, target_params, verbose=True):
    """
    Pour les équipes sous le seuil dans league_id, emprunte leurs
    paramètres depuis la division liée (TIER_LINKS) si elle a déjà été
    entraînée. Les valeurs sont RESCALÉES sur le niveau moyen de la
    ligue cible (pas une copie brute) : une division inférieure a un
    niveau moyen différent, copier tel quel sur-estimerait ou
    sous-estimerait systématiquement le promu selon le sens de
    l'emprunt. On préserve son rang relatif dans sa division d'origine,
    projeté sur l'échelle de la division cible — pas un facteur de
    performance des promus inventé, une simple mise à niveau d'échelle.
    Renvoie un DataFrame vide si aucune ligue liée ou aucune correspondance.
    """
    linked = TIER_LINKS.get(league_id)
    empty = pd.DataFrame(columns=["team", "alpha", "beta", "source_league_id"])
    if not under_threshold or linked is None or target_params.empty:
        return empty

    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT team, alpha, beta FROM club_dc_params WHERE league_id=?",
            (linked,)).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return empty
    conn.close()
    if not rows:
        return empty

    source_avg_alpha = float(np.mean([r[1] for r in rows]))
    source_avg_beta = float(np.mean([r[2] for r in rows]))
    target_avg_alpha = float(target_params["alpha"].mean())
    target_avg_beta = float(target_params["beta"].mean())
    if source_avg_alpha <= 0 or source_avg_beta <= 0:
        return empty
    scale_alpha = target_avg_alpha / source_avg_alpha
    scale_beta = target_avg_beta / source_avg_beta

    by_team = {t: (a, b) for t, a, b in rows}
    matched = []
    for team in sorted(under_threshold):
        if team in by_team:
            a, b = by_team[team]
            matched.append({"team": team, "alpha": a * scale_alpha, "beta": b * scale_beta,
                            "source_league_id": linked})
    if matched and verbose:
        names = ", ".join(m["team"] for m in matched)
        print(f"   🔗 {len(matched)} équipe(s) sous le seuil complétée(s) par estimation "
              f"depuis {league_display_name(linked)} (rescalée) : {names}")
    return pd.DataFrame(matched)


def _save_league(league_id, team_params, gamma, rho, nll, n_matches):
    conn = _connect()
    conn.execute("""CREATE TABLE IF NOT EXISTS club_dc_params (
        league_id INTEGER, team TEXT, alpha REAL, beta REAL,
        PRIMARY KEY (league_id, team))""")
    try:
        conn.execute("ALTER TABLE club_dc_params ADD COLUMN source_league_id INTEGER")
    except sqlite3.OperationalError:
        pass
    conn.execute("""CREATE TABLE IF NOT EXISTS club_dc_global (
        league_id INTEGER PRIMARY KEY, gamma REAL, rho REAL, nll REAL,
        n_matches INTEGER, trained_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("DELETE FROM club_dc_params WHERE league_id=?", (league_id,))
    for r in team_params.itertuples():
        src = getattr(r, "source_league_id", None)
        src = None if pd.isna(src) else int(src)
        conn.execute("INSERT INTO club_dc_params VALUES (?,?,?,?,?)",
                     (league_id, r.team, float(r.alpha), float(r.beta), src))
    conn.execute("""INSERT OR REPLACE INTO club_dc_global
        (league_id, gamma, rho, nll, n_matches, trained_at)
        VALUES (?,?,?,?,?,CURRENT_TIMESTAMP)""",
        (league_id, float(gamma), float(rho), float(nll), n_matches))
    conn.commit()
    conn.close()


def load_league_params(league_id):
    """(team_params_df indexé par team, {gamma, rho, n_matches, trained_at}) ou None."""
    conn = _connect()
    try:
        glob = conn.execute(
            "SELECT gamma, rho, n_matches, trained_at FROM club_dc_global WHERE league_id=?",
            (league_id,)).fetchone()
        if not glob:
            conn.close()
            return None
        try:
            tp = pd.read_sql_query(
                "SELECT team, alpha, beta, source_league_id FROM club_dc_params WHERE league_id=?",
                conn, params=(league_id,)).set_index("team")
        except Exception:
            tp = pd.read_sql_query(
                "SELECT team, alpha, beta FROM club_dc_params WHERE league_id=?",
                conn, params=(league_id,)).set_index("team")
            tp["source_league_id"] = None
    except Exception:
        conn.close()
        return None
    conn.close()
    return tp, {"gamma": glob[0], "rho": glob[1],
                "n_matches": glob[2], "trained_at": glob[3]}


# ─────────────────────────────────────────────────────────────────────────────
# BACKTEST WALK-FORWARD (une saison de test, refit périodique)
# ─────────────────────────────────────────────────────────────────────────────
def backtest_league(league_id, test_season, refit_days=REFIT_DAYS, verbose=True):
    if is_cup_competition(league_id):
        print(f"❌ Ligue {league_id} : compétition à phases mixtes — backtest non pertinent "
              f"(voir 'train' pour le détail).")
        return None
    conn = _connect()
    test = pd.read_sql_query("""
        SELECT date, home_team, away_team, home_score, away_score
        FROM club_matches WHERE league_id=? AND season=? ORDER BY date ASC
    """, conn, params=(league_id, test_season))
    conn.close()
    if test.empty:
        print(f"❌ Aucun match de test (ligue {league_id}, saison {test_season}).")
        return None

    rows = []
    params = None
    next_refit = None
    for m in test.itertuples():
        d = pd.Timestamp(m.date)
        if params is None or d >= next_refit:
            corpus = load_club_corpus(league_id, before=m.date)
            corpus = dc.filter_teams(corpus, min_matches=MIN_MATCHES_PER_TEAM)
            if len(corpus) < 100:
                continue  # pas assez d'historique en tout début de fenêtre
            tp, gamma, rho, _ = dc.fit(corpus, as_of=m.date, verbose=False)
            params = (tp.set_index("team"), gamma, rho)
            next_refit = d + pd.Timedelta(days=refit_days)
            if verbose:
                print(f"   🔄 refit au {m.date} ({len(corpus)} matchs)")
        tp, gamma, rho = params
        lam, mu = dc.predict_lambdas(m.home_team, m.away_team, False, tp, gamma)
        if lam is None:
            continue  # promu encore inconnu du corpus à cette date
        probs = dc.market_probabilities(lam, mu, rho)
        outcome = 0 if m.home_score > m.away_score else (1 if m.home_score == m.away_score else 2)
        rows.append({"p_home": probs["home"], "p_draw": probs["draw"],
                     "p_away": probs["away"], "outcome": outcome})

    if not rows:
        print("❌ Aucune prédiction évaluable.")
        return None
    pred = pd.DataFrame(rows)
    acc = accuracy(pred)
    brier = brier_multiclass(pred)
    ll = log_loss(pred)
    _, brier_base, ll_base = baseline_metrics(pred)
    cal = calibration_table(pred)
    ece = float(np.average(np.abs(cal["proba_moy"] - cal["freq_reelle"]),
                           weights=cal["n"])) if not cal.empty else None

    conn = _connect()
    conn.execute("""CREATE TABLE IF NOT EXISTS club_backtest (
        league_id INTEGER, test_season INTEGER, run_date TEXT,
        n_matches INTEGER, accuracy REAL, brier REAL, brier_baseline REAL,
        log_loss REAL, log_loss_baseline REAL, ece REAL, calibration_json TEXT,
        PRIMARY KEY (league_id, test_season))""")
    conn.execute("""INSERT OR REPLACE INTO club_backtest VALUES
        (?,?,date('now'),?,?,?,?,?,?,?,?)""",
        (league_id, test_season, len(pred), acc, brier, brier_base,
         ll, ll_base, ece, cal.to_json(orient="records")))
    conn.commit()
    conn.close()

    if verbose:
        gain = (brier_base - brier) / brier_base * 100
        print(f"\n📊 BACKTEST ligue {league_id} · saison {test_season}-{str(test_season+1)[-2:]}")
        print(f"   {len(pred)} matchs · précision {acc*100:.1f}% · Brier {brier:.4f} "
              f"(naïf {brier_base:.4f}, gain {gain:+.1f}%) · ECE {ece*100:.2f}%")
    return {"n": len(pred), "accuracy": acc, "brier": brier,
            "brier_baseline": brier_base, "ece": ece}


# ─────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    pt = sub.add_parser("train")
    pt.add_argument("--league", default="big5")
    pb = sub.add_parser("backtest")
    pb.add_argument("--league", required=True)
    pb.add_argument("--season", type=int, default=2025)
    args = ap.parse_args()

    leagues = resolve_leagues(args.league)
    if not leagues:
        print("Aucune ligue résolue — vérifie l'alias ou l'id fourni.")
        return
    if args.cmd == "train":
        for lg in leagues:
            print(f"\n════ {league_display_name(lg)} ════")
            train_league(lg)
    else:
        backtest_league(leagues[0], args.season)


if __name__ == "__main__":
    main()
