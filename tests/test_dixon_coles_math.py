"""
Tests du moteur Dixon-Coles (dixon_coles.py) : invariants probabilistes
et convergence sur un petit corpus synthétique. Ne valide pas la
qualité prédictive (ça, c'est le rôle du backtest walk-forward sur
données réelles) — vérifie que les maths ne sont pas cassées.
"""
import numpy as np
import pandas as pd
import pytest
import dixon_coles as dc


def test_market_probabilities_sum_to_one():
    probs = dc.market_probabilities(lam=1.4, mu=1.1, rho=-0.1)
    total = probs["home"] + probs["draw"] + probs["away"]
    assert total == pytest.approx(1.0, abs=1e-6)
    assert probs["over_2_5"] + probs["under_2_5"] == pytest.approx(1.0, abs=1e-6)
    assert probs["btts_yes"] + probs["btts_no"] == pytest.approx(1.0, abs=1e-6)


def test_market_probabilities_all_between_0_and_1():
    probs = dc.market_probabilities(lam=2.0, mu=0.5, rho=-0.05)
    for key, val in probs.items():
        assert 0.0 <= val <= 1.0, f"{key}={val} hors de [0,1]"


def test_score_matrix_sums_to_one():
    mat = dc.score_matrix(lam=1.3, mu=1.0, rho=-0.08, max_goals=10)
    assert mat.sum() == pytest.approx(1.0, abs=1e-6)
    assert (mat >= 0).all(), "Une matrice de probabilités ne doit jamais être négative"


def test_higher_lambda_means_more_home_wins():
    """Une attaque nettement supérieure doit se traduire par plus de victoires."""
    strong_home = dc.market_probabilities(lam=2.5, mu=0.7, rho=-0.05)
    balanced = dc.market_probabilities(lam=1.3, mu=1.3, rho=-0.05)
    assert strong_home["home"] > balanced["home"]


def _synthetic_corpus(n_teams=6, n_rounds=6, seed=42):
    """Round-robin synthétique : suffisant pour tester la convergence, pas la qualité."""
    rng = np.random.default_rng(seed)
    teams = [f"Team{i}" for i in range(n_teams)]
    rows = []
    date = pd.Timestamp("2025-01-01")
    for r in range(n_rounds):
        shuffled = list(teams)
        rng.shuffle(shuffled)
        for i in range(0, len(shuffled) - 1, 2):
            h, a = shuffled[i], shuffled[i + 1]
            rows.append({
                "date": date, "home_team": h, "away_team": a,
                "home_score": int(rng.poisson(1.4)), "away_score": int(rng.poisson(1.0)),
                "neutral": 0,
            })
        date += pd.Timedelta(days=7)
    return pd.DataFrame(rows)


def test_fit_converges_on_synthetic_corpus():
    df = _synthetic_corpus()
    team_params, gamma, rho, nll = dc.fit(df, verbose=False)

    assert len(team_params) == 6
    assert {"team", "alpha", "beta"} <= set(team_params.columns)
    assert np.isfinite(nll)
    assert 0.5 < gamma < 3.0, f"γ={gamma} hors d'une plage plausible d'avantage du terrain"
    assert -0.5 < rho < 0.5, f"ρ={rho} hors des bornes attendues du modèle"


def test_predict_lambdas_returns_positive_values():
    df = _synthetic_corpus()
    team_params, gamma, rho, _ = dc.fit(df, verbose=False)
    lam, mu = dc.predict_lambdas("Team0", "Team1", False, team_params.set_index("team"), gamma)
    assert lam > 0 and mu > 0


def test_predict_lambdas_unknown_team_returns_none():
    df = _synthetic_corpus()
    team_params, gamma, rho, _ = dc.fit(df, verbose=False)
    result = dc.predict_lambdas("EquipeInconnue", "Team1", False, team_params.set_index("team"), gamma)
    assert result == (None, None) or result[0] is None
