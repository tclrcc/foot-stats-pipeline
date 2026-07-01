"""
Backtest walk-forward + calibration du modèle Dixon-Coles.

Principe (aucune fuite de données) :
    Pour chaque mois M de la fenêtre de test :
        1. On ré-estime Dixon-Coles UNIQUEMENT sur les matchs < début de M
        2. On prédit le 1N2 de chaque match de M
        3. On compare aux résultats réels

Métriques produites :
    - Brier score multi-classe (0 = parfait, plus bas = mieux)
    - Log-loss (idem)
    - Accuracy (issue la plus probable = issue réelle)
    - Table de calibration (proba prédite vs fréquence observée)
    - Comparaison à un baseline naïf (fréquences de base 1/N/2)

La calibration est LE prérequis du value betting : si le modèle dit 60%
mais que ça n'arrive que 45% du temps, les "values" détectées sont fausses.
"""

import os
import sys
import sqlite3
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dixon_coles as dc

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(PROJECT_ROOT, "data/db/foot_stats.db")

# Fenêtre de test (mois) et compétitions évaluées
TEST_MONTHS = 12
EVAL_COMPETITIONS = dc.RELEVANT_COMPETITIONS


# ─────────────────────────────────────────────────────────────────────────────
# Chargement des matchs de test
# ─────────────────────────────────────────────────────────────────────────────
def load_test_matches(months=TEST_MONTHS):
    conn = sqlite3.connect(DB_PATH)
    cutoff = (pd.Timestamp.now() - pd.Timedelta(days=months * 30)).strftime("%Y-%m-%d")
    placeholders = ",".join(["?"] * len(EVAL_COMPETITIONS))
    df = pd.read_sql_query(f"""
        SELECT date, home_team, away_team, home_score, away_score, neutral
        FROM historical_matches
        WHERE date >= ?
          AND home_score IS NOT NULL AND away_score IS NOT NULL
          AND tournament IN ({placeholders})
        ORDER BY date ASC
    """, conn, params=[cutoff] + EVAL_COMPETITIONS)
    conn.close()

    df["date"]       = pd.to_datetime(df["date"])
    df["home_score"] = df["home_score"].astype(int)
    df["away_score"] = df["away_score"].astype(int)
    df["neutral"]    = df["neutral"].astype(bool)
    # Issue réelle : 0=home, 1=draw, 2=away
    df["outcome"] = np.select(
        [df["home_score"] > df["away_score"],
         df["home_score"] == df["away_score"]],
        [0, 1], default=2
    )
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Walk-forward
# ─────────────────────────────────────────────────────────────────────────────
def run_walk_forward(months=TEST_MONTHS, verbose=True):
    test_df = load_test_matches(months)
    if test_df.empty:
        print("⚠️  Aucun match de test disponible.")
        return None

    # Regroupe par mois calendaire
    test_df["period"] = test_df["date"].dt.to_period("M")
    periods = sorted(test_df["period"].unique())

    records = []   # une ligne par match prédit
    skipped = 0

    print(f"\n🔁 Walk-forward sur {len(periods)} mois "
          f"({test_df['date'].min().date()} → {test_df['date'].max().date()})")
    print("   " + "─" * 60)

    for period in periods:
        month_start = period.to_timestamp()
        month_matches = test_df[test_df["period"] == period]

        # Ré-estimation sur tout ce qui précède le mois
        corpus = dc.load_training_corpus(as_of=month_start)
        corpus = dc.filter_teams(corpus, min_matches=dc.MIN_MATCHES_PER_TEAM)
        if len(corpus) < 200:
            skipped += len(month_matches)
            continue

        team_params, gamma, rho, _ = fit_silent(corpus, month_start)
        tp_indexed = team_params.set_index("team")
        known = set(tp_indexed.index)

        n_pred = 0
        for row in month_matches.itertuples(index=False):
            if row.home_team not in known or row.away_team not in known:
                skipped += 1
                continue
            lam, mu = dc.predict_lambdas(row.home_team, row.away_team, row.neutral, tp_indexed, gamma)
            probs = dc.market_probabilities(lam, mu, rho)
            p = np.array([probs["home"], probs["draw"], probs["away"]])
            p = p / p.sum()
            records.append({
                "date": row.date, "home": row.home_team, "away": row.away_team,
                "p_home": p[0], "p_draw": p[1], "p_away": p[2],
                "outcome": row.outcome,
            })
            n_pred += 1

        if verbose:
            print(f"   {period}  : {n_pred:>3} matchs prédits (corpus {len(corpus):,})")

    print(f"   " + "─" * 60)
    print(f"   Total : {len(records)} matchs évalués, {skipped} ignorés (équipe hors corpus)")
    return pd.DataFrame(records)


def fit_silent(corpus, month_start):
    """Wrapper silencieux autour de dc.fit pour le walk-forward."""
    return dc.fit(corpus, as_of=month_start, verbose=False)


# ─────────────────────────────────────────────────────────────────────────────
# MÉTRIQUES
# ─────────────────────────────────────────────────────────────────────────────
def brier_multiclass(pred_df):
    """Brier multi-classe moyen (0 parfait). One-hot vs proba sur 3 issues."""
    P = pred_df[["p_home", "p_draw", "p_away"]].values
    Y = np.zeros_like(P)
    Y[np.arange(len(P)), pred_df["outcome"].values] = 1
    return float(np.mean(np.sum((P - Y) ** 2, axis=1)))


def log_loss(pred_df, eps=1e-15):
    P = pred_df[["p_home", "p_draw", "p_away"]].values
    idx = pred_df["outcome"].values
    p_true = np.clip(P[np.arange(len(P)), idx], eps, 1)
    return float(-np.mean(np.log(p_true)))


def accuracy(pred_df):
    P = pred_df[["p_home", "p_draw", "p_away"]].values
    pred_class = P.argmax(axis=1)
    return float((pred_class == pred_df["outcome"].values).mean())


def baseline_metrics(pred_df):
    """Baseline naïf : fréquences de base observées 1/N/2 pour tous les matchs."""
    freq = np.bincount(pred_df["outcome"].values, minlength=3) / len(pred_df)
    P = np.tile(freq, (len(pred_df), 1))
    Y = np.zeros_like(P)
    Y[np.arange(len(P)), pred_df["outcome"].values] = 1
    brier = float(np.mean(np.sum((P - Y) ** 2, axis=1)))
    p_true = np.clip(P[np.arange(len(P)), pred_df["outcome"].values], 1e-15, 1)
    ll = float(-np.mean(np.log(p_true)))
    return freq, brier, ll


def calibration_table(pred_df, n_bins=10):
    """
    Table de calibration : on empile toutes les prédictions (home, draw, away)
    et on compare proba prédite moyenne vs fréquence réelle par tranche.
    """
    probs, hits = [], []
    for col, out in [("p_home", 0), ("p_draw", 1), ("p_away", 2)]:
        probs.append(pred_df[col].values)
        hits.append((pred_df["outcome"].values == out).astype(float))
    probs = np.concatenate(probs)
    hits  = np.concatenate(hits)

    bins = np.linspace(0, 1, n_bins + 1)
    rows = []
    for i in range(n_bins):
        mask = (probs >= bins[i]) & (probs < bins[i + 1])
        if mask.sum() == 0:
            continue
        rows.append({
            "tranche": f"{bins[i]*100:.0f}-{bins[i+1]*100:.0f}%",
            "n": int(mask.sum()),
            "proba_moy": float(probs[mask].mean()),
            "freq_reelle": float(hits[mask].mean()),
        })
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# RAPPORT
# ─────────────────────────────────────────────────────────────────────────────
def report(pred_df):
    if pred_df is None or pred_df.empty:
        print("Aucune prédiction à évaluer.")
        return

    brier = brier_multiclass(pred_df)
    ll    = log_loss(pred_df)
    acc   = accuracy(pred_df)
    freq, base_brier, base_ll = baseline_metrics(pred_df)

    print("\n" + "=" * 62)
    print("📈 RÉSULTATS DU BACKTEST".center(62))
    print("=" * 62)
    print(f"   Matchs évalués      : {len(pred_df)}")
    print(f"   Fréquences réelles  : Dom {freq[0]*100:.1f}%  Nul {freq[1]*100:.1f}%  Ext {freq[2]*100:.1f}%")
    print()
    print(f"   {'Métrique':<20} {'Modèle':>10} {'Baseline':>10} {'Gain':>8}")
    print("   " + "─" * 50)
    print(f"   {'Brier (↓)':<20} {brier:>10.4f} {base_brier:>10.4f} {(base_brier-brier)/base_brier*100:>7.1f}%")
    print(f"   {'Log-loss (↓)':<20} {ll:>10.4f} {base_ll:>10.4f} {(base_ll-ll)/base_ll*100:>7.1f}%")
    print(f"   {'Accuracy (↑)':<20} {acc*100:>9.1f}% {'—':>10} {'':>8}")

    print("\n📊 TABLE DE CALIBRATION (proba prédite vs réalité)")
    print("   " + "─" * 50)
    ct = calibration_table(pred_df)
    print(f"   {'Tranche':<12} {'N':>6} {'Prédit':>10} {'Réel':>10} {'Écart':>8}")
    print("   " + "─" * 50)
    for _, r in ct.iterrows():
        ecart = r["freq_reelle"] - r["proba_moy"]
        flag = "  ✅" if abs(ecart) < 0.05 else ("  ⚠️" if abs(ecart) < 0.10 else "  ❌")
        print(f"   {r['tranche']:<12} {r['n']:>6} {r['proba_moy']*100:>9.1f}% "
              f"{r['freq_reelle']*100:>9.1f}% {ecart*100:>+7.1f}%{flag}")

    # Score de calibration global (ECE — Expected Calibration Error)
    ece = float(np.average(np.abs(ct["freq_reelle"] - ct["proba_moy"]), weights=ct["n"]))
    print("   " + "─" * 50)
    print(f"   ECE (erreur de calibration moyenne) : {ece*100:.2f}%")
    if ece < 0.03:
        print("   → Calibration EXCELLENTE : le value betting est fiable.")
    elif ece < 0.05:
        print("   → Calibration correcte : value betting utilisable avec prudence.")
    else:
        print("   → Calibration à améliorer : values à prendre avec réserve.")

    return {"brier": brier, "log_loss": ll, "accuracy": acc, "ece": ece}


def save_backtest(metrics):
    if not metrics:
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS backtest_log (
            run_date  TEXT PRIMARY KEY,
            brier     REAL, log_loss REAL, accuracy REAL, ece REAL
        )
    """)
    cur.execute("INSERT OR REPLACE INTO backtest_log VALUES (?, ?, ?, ?, ?)", (
        pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
        metrics["brier"], metrics["log_loss"], metrics["accuracy"], metrics["ece"],
    ))
    conn.commit()
    conn.close()


def run(months=TEST_MONTHS):
    print("\n🔬 BACKTEST DIXON-COLES (walk-forward)")
    print("=" * 62)
    pred_df = run_walk_forward(months)
    metrics = report(pred_df)
    save_backtest(metrics)
    print("\n✅ Backtest terminé.\n")
    return metrics


if __name__ == "__main__":
    run()
