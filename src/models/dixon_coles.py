"""
Estimateur Dixon-Coles (1997) avec décroissance temporelle exponentielle.

Référence :
    Dixon & Coles, "Modelling Association Football Scores and Inefficiencies
    in the Football Betting Market", JRSS-C 46(2), 1997.

Modèle :
    λ_home = α_home × β_away × γ        (γ : avantage du terrain)
    μ_away = α_away × β_home
    P(score=(i,j)) = Poisson(i|λ) × Poisson(j|μ) × τ(i,j,λ,μ,ρ)

    τ corrige la sous-estimation des scores faibles (Poisson pur sous-estime
    les nuls 0-0, 1-1). ρ < 0 augmente la masse sur les nuls.

Estimation :
    - MLE par L-BFGS-B (scipy)
    - Pondération exponentielle : poids_k = exp(-ξ × âge_jours)
    - ξ = 0.0019/jour (Hvattum & Arntzen 2010, foot international)
    - Régularisation L2 douce sur log(α), log(β) pour résoudre la dégénérescence
      multiplicative (α → c·α, β → β/c laissent λ, μ inchangés).

Doit être lancé après `elo_engine.py` (utilisé en fallback pour les rares
équipes avec trop peu de données — pas le cas ici, mais c'est défensif).
"""

import os
import sqlite3
import numpy as np
import pandas as pd
from scipy.optimize import minimize

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(PROJECT_ROOT, "data/db/foot_stats.db")

# ─────────────────────────────────────────────────────────────────────────────
# HYPERPARAMÈTRES
# ─────────────────────────────────────────────────────────────────────────────
HISTORY_WINDOW_DAYS = 4 * 365   # fenêtre d'historique
XI_DAY              = 0.0019    # décroissance temporelle par jour
MIN_MATCHES_PER_TEAM = 8         # équipes en-dessous → fallback ELO
L2_REG              = 0.05      # régularisation log(α), log(β)

# Compétitions retenues pour l'estimation (foot international sérieux)
RELEVANT_COMPETITIONS = [
    'Friendly',
    'FIFA World Cup', 'FIFA World Cup qualification',
    'UEFA Euro', 'UEFA Euro qualification',
    'UEFA Nations League',
    'African Cup of Nations', 'African Cup of Nations qualification',
    'AFC Asian Cup', 'AFC Asian Cup qualification',
    'Copa América',
    'Gold Cup', 'Gold Cup qualification',
    'CONCACAF Nations League', 'CONCACAF Nations League qualification',
    'Confederations Cup',
    'FIFA Series',
]


# ─────────────────────────────────────────────────────────────────────────────
# CHARGEMENT DU CORPUS
# ─────────────────────────────────────────────────────────────────────────────
def load_training_corpus():
    conn = sqlite3.connect(DB_PATH)
    cutoff = (pd.Timestamp.now() - pd.Timedelta(days=HISTORY_WINDOW_DAYS)).strftime("%Y-%m-%d")
    placeholders = ",".join(["?"] * len(RELEVANT_COMPETITIONS))

    df = pd.read_sql_query(f"""
        SELECT date, home_team, away_team, home_score, away_score, neutral
        FROM historical_matches
        WHERE date >= ?
          AND home_score IS NOT NULL AND away_score IS NOT NULL
          AND tournament IN ({placeholders})
        ORDER BY date ASC
    """, conn, params=[cutoff] + RELEVANT_COMPETITIONS)
    conn.close()

    df["date"]       = pd.to_datetime(df["date"])
    df["home_score"] = df["home_score"].astype(int)
    df["away_score"] = df["away_score"].astype(int)
    df["neutral"]    = df["neutral"].astype(bool)
    return df


def filter_teams(df, min_matches=MIN_MATCHES_PER_TEAM):
    """Retire les équipes avec trop peu de matchs (estimation peu fiable)."""
    appearances = pd.concat([df["home_team"], df["away_team"]])
    counts = appearances.value_counts()
    keep = set(counts[counts >= min_matches].index)
    dropped = set(counts[counts < min_matches].index)
    if dropped:
        print(f"   ℹ️  {len(dropped)} équipes avec <{min_matches} matchs écartées : {sorted(dropped)[:10]}...")
    return df[df["home_team"].isin(keep) & df["away_team"].isin(keep)].reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# NÉGATIVE LOG-VRAISEMBLANCE (vectorisée)
# ─────────────────────────────────────────────────────────────────────────────
def _tau_correction(h_score, a_score, lam, mu, rho):
    """
    Correction Dixon-Coles τ(i, j, λ, μ, ρ) — vectorisée sur tous les matchs.
    Renvoie 1 sauf pour les scores (0,0), (1,0), (0,1), (1,1).
    """
    tau = np.ones_like(lam)
    m00 = (h_score == 0) & (a_score == 0)
    m10 = (h_score == 1) & (a_score == 0)
    m01 = (h_score == 0) & (a_score == 1)
    m11 = (h_score == 1) & (a_score == 1)

    tau = np.where(m00, 1.0 - lam * mu * rho, tau)
    tau = np.where(m10, 1.0 + mu * rho,        tau)
    tau = np.where(m01, 1.0 + lam * rho,       tau)
    tau = np.where(m11, 1.0 - rho,             tau)
    return tau


def _neg_log_likelihood(params, h_idx, a_idx, h_score, a_score, is_neutral, weights, n_teams):
    """
    Layout de params :
        [0 : n_teams]                : log_alpha
        [n_teams : 2*n_teams]        : log_beta
        [2*n_teams]                  : log_gamma   (avantage terrain)
        [2*n_teams + 1]              : rho         (correction DC)
    """
    log_alpha = params[:n_teams]
    log_beta  = params[n_teams:2 * n_teams]
    log_gamma = params[2 * n_teams]
    rho       = params[2 * n_teams + 1]

    alpha = np.exp(log_alpha)
    beta  = np.exp(log_beta)
    gamma = np.exp(log_gamma)

    # Avantage terrain neutralisé sur match neutre
    eff_gamma = np.where(is_neutral, 1.0, gamma)

    lam = eff_gamma * alpha[h_idx] * beta[a_idx]
    mu  = alpha[a_idx] * beta[h_idx]

    lam = np.clip(lam, 1e-6, None)
    mu  = np.clip(mu,  1e-6, None)

    # Log-vraisemblance Poisson (constantes log(i!) omises, n'affectent pas l'optim)
    log_lik = (-lam + h_score * np.log(lam)) + (-mu + a_score * np.log(mu))

    # Correction Dixon-Coles
    tau = _tau_correction(h_score, a_score, lam, mu, rho)
    tau = np.clip(tau, 1e-10, None)
    log_lik = log_lik + np.log(tau)

    # NLL pondérée par décroissance temporelle
    nll = -np.sum(weights * log_lik)

    # Régularisation L2 (centre log(α), log(β) sur 0 → α≈1, β≈1)
    reg = L2_REG * (np.sum(log_alpha ** 2) + np.sum(log_beta ** 2))

    return nll + reg


# ─────────────────────────────────────────────────────────────────────────────
# FIT
# ─────────────────────────────────────────────────────────────────────────────
def fit(df):
    teams = sorted(set(df["home_team"]) | set(df["away_team"]))
    team_idx = {t: i for i, t in enumerate(teams)}
    n_teams = len(teams)

    h_idx       = df["home_team"].map(team_idx).values.astype(int)
    a_idx       = df["away_team"].map(team_idx).values.astype(int)
    h_score     = df["home_score"].values.astype(int)
    a_score     = df["away_score"].values.astype(int)
    is_neutral  = df["neutral"].values

    # Poids de décroissance temporelle
    today    = pd.Timestamp.now().normalize()
    age_days = (today - df["date"]).dt.days.values.astype(float)
    weights  = np.exp(-XI_DAY * age_days)

    print(f"   📊 {len(df):,} matchs × {n_teams} équipes")
    print(f"   ⏳ Poids effectif (= matchs équivalents pleins) : {weights.sum():.0f}")

    # Initialisation : α=β=1, γ=1.3, ρ=-0.05
    x0 = np.zeros(2 * n_teams + 2)
    x0[2 * n_teams] = np.log(1.3)
    x0[2 * n_teams + 1] = -0.05

    bounds = [(-2.0, 2.0)] * (2 * n_teams) + [(0.0, 0.7), (-0.4, 0.2)]

    print(f"   ⚙️  Optimisation MLE (L-BFGS-B)...")
    result = minimize(
        _neg_log_likelihood,
        x0,
        args=(h_idx, a_idx, h_score, a_score, is_neutral, weights, n_teams),
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": 2000, "maxfun": 100000, "ftol": 1e-9, "gtol": 1e-7},
    )

    if result.success:
        print(f"   ✅ Convergence atteinte (NLL={result.fun:.1f}, itérations={result.nit})")
    else:
        print(f"   ⚠️  Convergence partielle : {result.message}")
        print(f"      NLL={result.fun:.1f}, itérations={result.nit}")

    # Extraction
    log_alpha = result.x[:n_teams]
    log_beta  = result.x[n_teams:2 * n_teams]
    gamma     = float(np.exp(result.x[2 * n_teams]))
    rho       = float(result.x[2 * n_teams + 1])

    # ─── Normalisation : ramener mean(log α) = 0 pour interprétabilité.
    # Transformation invariante sur λ, μ :  α_i → α_i / c, β_i → β_i × c
    # avec c = exp(mean(log α)). γ inchangé.
    c = np.exp(log_alpha.mean())
    alpha = np.exp(log_alpha) / c
    beta  = np.exp(log_beta)  * c

    team_params = pd.DataFrame({
        "team":  teams,
        "alpha": alpha,
        "beta":  beta,
    })

    return team_params, gamma, rho, result.fun


# ─────────────────────────────────────────────────────────────────────────────
# DIAGNOSTICS
# ─────────────────────────────────────────────────────────────────────────────
def print_diagnostics(team_params, gamma, rho):
    print(f"\n📐 PARAMÈTRES GLOBAUX")
    print(f"   γ (avantage terrain)  : {gamma:.3f}    (foot intl typique : 1.25 - 1.45)")
    print(f"   ρ (correction DC)     : {rho:+.3f}   (foot typique : -0.15 à +0.05)")
    print(f"   ξ (décroissance/jour) : {XI_DAY}   (demi-vie : {np.log(2)/XI_DAY:.0f} jours)")

    print(f"\n⚔️  TOP 15 — ATTAQUE (α)")
    top_att = team_params.sort_values("alpha", ascending=False).head(15)
    for _, r in top_att.iterrows():
        print(f"   {r['team']:<30} α = {r['alpha']:.3f}")

    print(f"\n🛡️  TOP 15 — DÉFENSE (β plus faible = meilleure défense)")
    top_def = team_params.sort_values("beta").head(15)
    for _, r in top_def.iterrows():
        print(f"   {r['team']:<30} β = {r['beta']:.3f}")


# ─────────────────────────────────────────────────────────────────────────────
# PERSISTANCE EN BASE
# ─────────────────────────────────────────────────────────────────────────────
def save_to_db(team_params, gamma, rho, nll):
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS dc_team_params;")
    cur.execute("""
        CREATE TABLE dc_team_params (
            team   TEXT PRIMARY KEY,
            alpha  REAL,
            beta   REAL
        )
    """)
    cur.executemany(
        "INSERT INTO dc_team_params VALUES (?, ?, ?)",
        [(r["team"], float(r["alpha"]), float(r["beta"])) for _, r in team_params.iterrows()]
    )

    cur.execute("DROP TABLE IF EXISTS dc_global_params;")
    cur.execute("""
        CREATE TABLE dc_global_params (
            name   TEXT PRIMARY KEY,
            value  REAL
        )
    """)
    cur.executemany("INSERT INTO dc_global_params VALUES (?, ?)", [
        ("gamma",                gamma),
        ("rho",                  rho),
        ("xi_per_day",           XI_DAY),
        ("history_window_days",  HISTORY_WINDOW_DAYS),
        ("nll",                  nll),
    ])

    cur.execute("""
        CREATE TABLE IF NOT EXISTS dc_fit_log (
            fit_date  TEXT PRIMARY KEY,
            n_teams   INTEGER,
            n_matches INTEGER,
            gamma     REAL,
            rho       REAL,
            nll       REAL
        )
    """)
    cur.execute("INSERT OR REPLACE INTO dc_fit_log VALUES (?, ?, ?, ?, ?, ?)", (
        pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
        len(team_params), 0, gamma, rho, nll,
    ))

    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# LECTURE DEPUIS LA BASE (utilisé par predict_upcoming)
# ─────────────────────────────────────────────────────────────────────────────
def load_params():
    """Charge les paramètres ajustés depuis la base."""
    conn = sqlite3.connect(DB_PATH)
    teams = pd.read_sql_query("SELECT * FROM dc_team_params", conn).set_index("team")
    glob  = dict(pd.read_sql_query("SELECT * FROM dc_global_params", conn).values)
    conn.close()
    return teams, glob


def predict_lambdas(home, away, neutral, team_params, gamma):
    """
    Renvoie (λ_home, μ_away) si les deux équipes sont connues.
    Sinon (None, None) — l'appelant gère le fallback.
    """
    if home not in team_params.index or away not in team_params.index:
        return None, None

    a_h = team_params.loc[home, "alpha"]
    b_h = team_params.loc[home, "beta"]
    a_a = team_params.loc[away, "alpha"]
    b_a = team_params.loc[away, "beta"]

    eff_gamma = 1.0 if neutral else gamma
    lam = eff_gamma * a_h * b_a
    mu  = a_a * b_h
    return float(lam), float(mu)


# ─────────────────────────────────────────────────────────────────────────────
# ORCHESTRATION
# ─────────────────────────────────────────────────────────────────────────────
def run():
    print("\n🔄 Estimation Dixon-Coles MLE")
    print("=" * 60)

    df = load_training_corpus()
    print(f"   📥 Corpus brut : {len(df):,} matchs depuis {df['date'].min().date()}")

    df = filter_teams(df)

    team_params, gamma, rho, nll = fit(df)
    print_diagnostics(team_params, gamma, rho)

    save_to_db(team_params, gamma, rho, nll)
    print(f"\n💾 Paramètres sauvegardés : dc_team_params ({len(team_params)} équipes), dc_global_params")
    print("✅ Modèle Dixon-Coles prêt.\n")


if __name__ == "__main__":
    run()
