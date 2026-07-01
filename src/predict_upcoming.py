import sqlite3
import pandas as pd
import numpy as np
from scipy.stats import poisson
import datetime
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "data/db/foot_stats.db")

# Permet d'importer le module Dixon-Coles
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from models.dixon_coles import load_params as load_dc_params, predict_lambdas as dc_predict
from models.squad_impact import (
    load_scorer_depth, load_absences, compute_attack_adjustment,
)
from models.value_finder import find_values_for_match, print_values
from models.context_cdm2026 import match_context
from models.lineup_strength import match_lineup_adjustment
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "extractor"))
from odds_extractor import load_odds

# ─────────────────────────────────────────────────────────────────────────────
# MOTEUR DE STATISTIQUES AVANCÉES & LISSAGE
# ─────────────────────────────────────────────────────────────────────────────

def get_advanced_stats(conn):
    # FIX BUG #3 : is_finished est stocké comme INTEGER (1) dans SQLite, pas 'TRUE'
    df_curr = pd.read_sql_query("SELECT * FROM cdm_2026 WHERE is_finished = 1", conn)
    dash = pd.DataFrame(columns=['avg_scored', 'avg_conceded', 'games_played'])

    if not df_curr.empty:
        df_curr['home_goals'] = pd.to_numeric(df_curr['home_goals'], errors='coerce').fillna(0)
        df_curr['away_goals'] = pd.to_numeric(df_curr['away_goals'], errors='coerce').fillna(0)

        home = df_curr[['home_team', 'home_goals', 'away_goals']].rename(
            columns={'home_team': 'team', 'home_goals': 'goals_scored', 'away_goals': 'goals_conceded'})
        away = df_curr[['away_team', 'away_goals', 'home_goals']].rename(
            columns={'away_team': 'team', 'away_goals': 'goals_scored', 'home_goals': 'goals_conceded'})
        all_curr = pd.concat([home, away])

        dash = all_curr.groupby('team').agg(
            avg_scored=('goals_scored', 'mean'),
            avg_conceded=('goals_conceded', 'mean'),
            games_played=('goals_scored', 'count')
        )

    try:
        hist_avg_df = pd.read_sql_query(
            "SELECT AVG(home_score) as h_avg, AVG(away_score) as a_avg FROM historical_matches", conn)
        hist_global_avg = (hist_avg_df['h_avg'].iloc[0] + hist_avg_df['a_avg'].iloc[0]) / 2
    except:
        hist_global_avg = 1.35

    try:
        elo_df = pd.read_sql_query("SELECT * FROM team_elo", conn).set_index('team')
    except:
        elo_df = pd.DataFrame(columns=['elo_rating'])

    return dash, hist_global_avg, elo_df


def get_historical_power(conn, team, hist_global_avg):
    query_recent = """
        SELECT home_score, away_score, CASE WHEN home_team = ? THEN 'H' ELSE 'A' END as side
        FROM historical_matches WHERE (home_team = ? OR away_team = ?) AND tournament != 'Friendly'
        ORDER BY date DESC LIMIT 40;
    """
    recent_df = pd.read_sql_query(query_recent, conn, params=(team, team, team))

    query_wc = """
        SELECT home_score, away_score, CASE WHEN home_team = ? THEN 'H' ELSE 'A' END as side
        FROM historical_matches WHERE (home_team = ? OR away_team = ?) AND tournament = 'FIFA World Cup';
    """
    wc_df = pd.read_sql_query(query_wc, conn, params=(team, team, team))

    def calc_ratios(df):
        if df.empty:
            return 1.0, 1.0
        scored = np.where(df['side'] == 'H', df['home_score'], df['away_score']).mean()
        conceded = np.where(df['side'] == 'H', df['away_score'], df['home_score']).mean()
        return (max(0.5, scored) / hist_global_avg), (max(0.5, conceded) / hist_global_avg)

    r_rec_att, r_rec_def = calc_ratios(recent_df)
    r_wc_att, r_wc_def = calc_ratios(wc_df)

    if len(wc_df) < 3:
        return r_rec_att, r_rec_def

    final_attack  = (r_rec_att * 0.70) + (r_wc_att * 0.30)
    final_defense = (r_rec_def * 0.70) + (r_wc_def * 0.30)
    return final_attack, final_defense


def get_h2h_modifier(conn, team_H, team_A):
    query = """
        SELECT home_team, home_score, away_score FROM historical_matches
        WHERE (home_team = ? AND away_team = ?) OR (home_team = ? AND away_team = ?);
    """
    h2h_df = pd.read_sql_query(query, conn, params=(team_H, team_A, team_A, team_H))
    if len(h2h_df) < 2:
        return 1.0, 1.0
    h_goals = np.where(h2h_df['home_team'] == team_H, h2h_df['home_score'], h2h_df['away_score']).sum()
    a_goals = np.where(h2h_df['home_team'] == team_H, h2h_df['away_score'], h2h_df['home_score']).sum()
    total = h_goals + a_goals
    if total == 0:
        return 1.0, 1.0
    h_bias = 1 + max(-0.15, min(0.15, (h_goals - a_goals) / (total * 2)))
    a_bias = 1 + max(-0.15, min(0.15, (a_goals - h_goals) / (total * 2)))
    return h_bias, a_bias


def dixon_coles_adjustment(score_matrix, lambda_H, lambda_A, rho=-0.06):
    """Applique la correction Dixon-Coles τ aux cellules (0,0), (1,0), (0,1), (1,1)."""
    if score_matrix.shape[0] > 2 and score_matrix.shape[1] > 2:
        score_matrix[0, 0] *= (1 - lambda_H * lambda_A * rho)
        score_matrix[1, 0] *= (1 + lambda_A * rho)
        score_matrix[0, 1] *= (1 + lambda_H * rho)
        score_matrix[1, 1] *= (1 - rho)
    return score_matrix


# ─────────────────────────────────────────────────────────────────────────────
# CALCUL DES LAMBDAS — Dixon-Coles si dispo, sinon fallback heuristique
# ─────────────────────────────────────────────────────────────────────────────
def compute_lambdas(team_H, team_A, conn, dash, hist_global_avg, elo_df,
                    dc_team_params, dc_global, neutral=True,
                    attack_adj_H=1.0, attack_adj_A=1.0):
    """
    Retourne (lambda_H, lambda_A, rho_to_use, method) où method ∈ {'DC', 'heuristic'}.

    attack_adj_H, attack_adj_A : multiplicateurs sur l'attaque, calculés par
    le module squad_impact en fonction des forfaits déclarés.
    """
    # 1) Tentative Dixon-Coles
    if dc_team_params is not None and dc_global is not None:
        gamma = dc_global.get("gamma", 1.3)
        rho_dc = dc_global.get("rho", -0.06)
        lam, mu = dc_predict(team_H, team_A, neutral, dc_team_params, gamma)
        if lam is not None:
            # Application des ajustements d'attaque
            lam *= attack_adj_H
            mu  *= attack_adj_A
            lam = max(0.15, min(lam, 5.0))
            mu  = max(0.15, min(mu,  5.0))
            return lam, mu, rho_dc, "DC"

    # 2) Fallback : ancienne heuristique ELO + current form + H2H
    hist_H_att, hist_H_def = get_historical_power(conn, team_H, hist_global_avg)
    hist_A_att, hist_A_def = get_historical_power(conn, team_A, hist_global_avg)
    h2h_bias_H, h2h_bias_A = get_h2h_modifier(conn, team_H, team_A)

    h_played = dash.loc[team_H, 'games_played'] if team_H in dash.index else 0
    a_played = dash.loc[team_A, 'games_played'] if team_A in dash.index else 0

    curr_H_att = max(0.4, (dash.loc[team_H, 'avg_scored']   / hist_global_avg)) if h_played > 0 else 1.0
    curr_H_def = max(0.4, (dash.loc[team_H, 'avg_conceded'] / hist_global_avg)) if h_played > 0 else 1.0
    curr_A_att = max(0.4, (dash.loc[team_A, 'avg_scored']   / hist_global_avg)) if a_played > 0 else 1.0
    curr_A_def = max(0.4, (dash.loc[team_A, 'avg_conceded'] / hist_global_avg)) if a_played > 0 else 1.0

    w_H = min(1.0, h_played / 5.0)
    w_A = min(1.0, a_played / 5.0)

    final_H_att = (curr_H_att * w_H) + (hist_H_att * (1 - w_H))
    final_H_def = (curr_H_def * w_H) + (hist_H_def * (1 - w_H))
    final_A_att = (curr_A_att * w_A) + (hist_A_att * (1 - w_A))
    final_A_def = (curr_A_def * w_A) + (hist_A_def * (1 - w_A))

    elo_H = elo_df.loc[team_H, 'elo_rating'] if team_H in elo_df.index else 1500
    elo_A = elo_df.loc[team_A, 'elo_rating'] if team_A in elo_df.index else 1500
    elo_diff   = (elo_H - elo_A) / 400
    elo_H_mult = 1 + (elo_diff * 0.4)
    elo_A_mult = 1 - (elo_diff * 0.4)

    home_mult = 1.0 if neutral else 1.05

    lam = hist_global_avg * final_H_att * final_A_def * elo_H_mult * h2h_bias_H * home_mult
    mu  = hist_global_avg * final_A_att * final_H_def * elo_A_mult * h2h_bias_A

    # Ajustement absences
    lam *= attack_adj_H
    mu  *= attack_adj_A

    lam = max(0.4, min(lam, 3.5))
    mu  = max(0.4, min(mu,  3.5))
    return lam, mu, -0.06, "heuristic"


# ─────────────────────────────────────────────────────────────────────────────
# MOTEUR DE PRÉDICTION MULTI-MARCHÉS
# ─────────────────────────────────────────────────────────────────────────────

def run_prediction_markets(team_H, team_A, conn, dash, hist_global_avg, elo_df,
                           dc_team_params, dc_global,
                           attack_adj_H=1.0, attack_adj_A=1.0):
    lambda_H, lambda_A, rho_used, method = compute_lambdas(
        team_H, team_A, conn, dash, hist_global_avg, elo_df,
        dc_team_params, dc_global, neutral=True,
        attack_adj_H=attack_adj_H, attack_adj_A=attack_adj_A,
    )

    max_goals = 6
    probs_H = poisson.pmf(np.arange(max_goals), lambda_H)
    probs_A = poisson.pmf(np.arange(max_goals), lambda_A)
    score_matrix = np.outer(probs_H, probs_A)
    score_matrix = dixon_coles_adjustment(score_matrix, lambda_H, lambda_A, rho=rho_used)
    score_matrix /= score_matrix.sum()

    p_H_win = np.sum(np.tril(score_matrix, -1))
    p_draw   = np.sum(np.diag(score_matrix))
    p_A_win  = np.sum(np.triu(score_matrix, 1))

    p_over_1_5  = sum(score_matrix[i, j] for i in range(max_goals) for j in range(max_goals) if i + j > 1.5)
    p_over_2_5  = sum(score_matrix[i, j] for i in range(max_goals) for j in range(max_goals) if i + j > 2.5)
    p_under_2_5 = sum(score_matrix[i, j] for i in range(max_goals) for j in range(max_goals) if i + j < 2.5)
    p_btts_yes  = sum(score_matrix[i, j] for i in range(1, max_goals) for j in range(1, max_goals))

    markets = {
        "1N2": {
            "1": p_H_win * 100,
            "N": p_draw  * 100,
            "2": p_A_win * 100
        },
        "Double Chance": {
            f"1N ({team_H} ou Nul)":  (p_H_win + p_draw) * 100,
            f"N2 (Nul ou {team_A})":  (p_A_win + p_draw) * 100,
            "12":                      (p_H_win + p_A_win) * 100
        },
        "Buts Totaux": {
            "Plus de 1.5":  p_over_1_5  * 100,
            "Plus de 2.5":  p_over_2_5  * 100,
            "Moins de 2.5": p_under_2_5 * 100
        },
        "Les deux marquent": {
            "Oui": p_btts_yes          * 100,
            "Non": (1 - p_btts_yes)    * 100
        }
    }

    scores_list = [(f"{i}-{j}", score_matrix[i, j] * 100) for i in range(max_goals) for j in range(max_goals)]
    top_scores  = sorted(scores_list, key=lambda x: x[1], reverse=True)[:3]

    return markets, top_scores, [lambda_H, lambda_A], method


def predict_today_matches():
    target_date = datetime.date.today().strftime("%Y-%m-%d")

    conn = sqlite3.connect(DB_PATH)
    # FIX BUG #3 : is_finished = 0 (INTEGER), pas 'FALSE'
    query = f"SELECT date, home_team, away_team FROM cdm_2026 WHERE date LIKE '{target_date}%' AND is_finished = 0"
    upcoming_matches = pd.read_sql_query(query, conn)

    if upcoming_matches.empty:
        print(f"📅 Aucun match non joué programmé pour aujourd'hui ({target_date}).")
        conn.close()
        return

    dash, hist_global_avg, elo_df = get_advanced_stats(conn)

    # Chargement des paramètres Dixon-Coles (peut échouer si jamais le module n'a
    # pas encore tourné — on tombe alors en heuristique pure).
    try:
        dc_team_params, dc_global = load_dc_params()
        print(f"\n🧠 Dixon-Coles chargé : {len(dc_team_params)} équipes, "
              f"γ={dc_global['gamma']:.3f}, ρ={dc_global['rho']:+.3f}, "
              f"ajusté depuis {int(dc_global['history_window_days'])} jours d'historique")
    except Exception as e:
        print(f"\n⚠️  Dixon-Coles indisponible ({e}). Fallback heuristique.")
        dc_team_params, dc_global = None, None

    # Chargement des absences déclarées (data/absences.json)
    try:
        absences = load_absences()
        depth_df = load_scorer_depth()
        if absences:
            print(f"📋 Absences déclarées pour {len(absences)} équipe(s) : "
                  f"{list(absences.keys())}")
    except Exception as e:
        print(f"⚠️  Module squad_impact indisponible ({e}).")
        absences, depth_df = {}, None

    # Chargement des cotes (data/odds.json + API optionnelle)
    try:
        match_odds_all = load_odds()
        if match_odds_all:
            print(f"💰 Cotes chargées pour {len(match_odds_all)} match(s).")
    except Exception as e:
        print(f"⚠️  Cotes indisponibles ({e}).")
        match_odds_all = {}

    # Chargement des compositions (data/lineups.json — manuel ou rempli par l'API)
    lineups_all = {}
    lineups_path = os.path.join(PROJECT_ROOT, "data/lineups.json")
    try:
        if os.path.exists(lineups_path):
            import json
            with open(lineups_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            lineups_all = {k: v for k, v in raw.items() if not k.startswith("_")}
            if lineups_all:
                print(f"👥 Compositions chargées pour {len(lineups_all)} match(s).")
    except Exception as e:
        print(f"⚠️  Compositions indisponibles ({e}).")
        lineups_all = {}

    all_values = []   # accumulateur de value bets

    print("\n" + "=" * 95)
    print(f"📊 REPORTING DIXON-COLES MLE — {target_date}".center(95))
    print("=" * 95)

    tous_les_pronos = []

    for _, match in upcoming_matches.iterrows():
        team_H = match['home_team']
        team_A = match['away_team']
        match_date = match['date']

        # Calcul des ajustements d'attaque pour ce match
        adj_H = compute_attack_adjustment(team_H, absences.get(team_H, []), depth_df) \
                if depth_df is not None else {"multiplier": 1.0, "matched_absents": [], "unmatched_absents": [], "total_impact": 0.0}
        adj_A = compute_attack_adjustment(team_A, absences.get(team_A, []), depth_df) \
                if depth_df is not None else {"multiplier": 1.0, "matched_absents": [], "unmatched_absents": [], "total_impact": 0.0}

        # Ajustements contextuels CDM 2026 (hôte, élimination directe, altitude)
        ctx = match_context(team_H, team_A, match_date, city=None)

        # Multiplicateurs combinés : absences × contexte
        combined_adj_H = adj_H["multiplier"] * ctx["lam_mult"]
        combined_adj_A = adj_A["multiplier"] * ctx["mu_mult"]

        # Ajustement force de composition (si compo dispo pour ce match)
        match_key0 = f"{team_H} vs {team_A}"
        lineup_notes = []
        if match_key0 in lineups_all:
            ld = lineups_all[match_key0]
            try:
                lin = match_lineup_adjustment(ld["home"], ld["away"])
                combined_adj_H *= lin["lam_mult"]
                combined_adj_A *= lin["mu_mult"]
                lineup_notes = lin["notes"]
            except Exception as e:
                lineup_notes = [f"compo ignorée (format invalide : {e})"]

        markets, top_scores, lambdas, method = run_prediction_markets(
            team_H, team_A, conn, dash, hist_global_avg, elo_df,
            dc_team_params, dc_global,
            attack_adj_H=combined_adj_H, attack_adj_A=combined_adj_A)

        method_tag = "[DC]" if method == "DC" else "[heur.]"
        if adj_H["matched_absents"] or adj_A["matched_absents"]:
            method_tag = method_tag.replace("]", "+abs]")
        if ctx["notes"]:
            method_tag = method_tag.replace("]", "+ctx]")
        if lineup_notes:
            method_tag = method_tag.replace("]", "+XI]")

        print(f"\n⚔️  MATCH : {team_H} vs {team_A}  {method_tag}")
        print(f"   ↳ xG Projetés → {team_H}: {lambdas[0]:.2f} | {team_A}: {lambdas[1]:.2f}")

        # Détail du contexte appliqué
        for note in ctx["notes"]:
            print(f"   ↳ 🌍 {note}")
        # Détail de la composition
        for note in lineup_notes:
            print(f"   ↳ 👥 {note}")

        # Détail des absences appliquées
        for side, team_name, adj in [("H", team_H, adj_H), ("A", team_A, adj_A)]:
            if adj["matched_absents"]:
                imp_pct = adj["total_impact"] * 100
                names = ", ".join(adj["matched_absents"])
                print(f"   ↳ Forfaits {team_name} : {names}  →  α × {adj['multiplier']:.2f} (-{imp_pct:.1f}%)")
            if adj["unmatched_absents"]:
                print(f"   ⚠️  Forfaits non reconnus {team_name} : {adj['unmatched_absents']} (ignorés)")
        print("   " + "-" * 85)
        print(f"   | 1N2            | 1: {markets['1N2']['1']:>5.1f}%  N: {markets['1N2']['N']:>5.1f}%  2: {markets['1N2']['2']:>5.1f}% |")

        dc = list(markets['Double Chance'].items())
        print(f"   | Double Chance  | {dc[0][0]:<30}: {dc[0][1]:>5.1f}% | {dc[1][0]:<30}: {dc[1][1]:>5.1f}% |")
        print(f"   | Buts Totaux    | +1.5: {markets['Buts Totaux']['Plus de 1.5']:>5.1f}%  +2.5: {markets['Buts Totaux']['Plus de 2.5']:>5.1f}%  -2.5: {markets['Buts Totaux']['Moins de 2.5']:>5.1f}% |")
        print(f"   | BTTS           | Oui: {markets['Les deux marquent']['Oui']:>5.1f}%  Non: {markets['Les deux marquent']['Non']:>5.1f}% |")
        scores_str = "  ".join([f"[{s[0]}: {s[1]:.1f}%]" for s in top_scores])
        print(f"   | TOP 3 Scores   | {scores_str}")
        print("   " + "-" * 85)

        # ── Détection de value bets pour ce match (si cotes dispo) ──
        match_key = f"{team_H} vs {team_A}"
        match_odds = match_odds_all.get(match_key)
        if match_odds:
            model_probs = {
                "home":      markets['1N2']['1'] / 100,
                "draw":      markets['1N2']['N'] / 100,
                "away":      markets['1N2']['2'] / 100,
                "over_1_5":  markets['Buts Totaux']['Plus de 1.5'] / 100,
                "over_2_5":  markets['Buts Totaux']['Plus de 2.5'] / 100,
                "under_2_5": markets['Buts Totaux']['Moins de 2.5'] / 100,
                "btts_yes":  markets['Les deux marquent']['Oui'] / 100,
                "btts_no":   markets['Les deux marquent']['Non'] / 100,
            }
            match_values = find_values_for_match(match_key, model_probs, match_odds)
            all_values.extend(match_values)
            if match_values:
                print(f"   💎 {len(match_values)} value(s) détectée(s) sur ce match")

        tous_les_pronos.append({"match": f"{team_H} vs {team_A}", "market": dc[0][0], "prob": dc[0][1]})
        tous_les_pronos.append({"match": f"{team_H} vs {team_A}", "market": dc[1][0], "prob": dc[1][1]})
        tous_les_pronos.append({"match": f"{team_H} vs {team_A}", "market": "Plus de 1.5 Buts", "prob": markets['Buts Totaux']['Plus de 1.5']})
        if markets['1N2']['1'] > 50:
            tous_les_pronos.append({"match": f"{team_H} vs {team_A}", "market": f"Victoire {team_H}", "prob": markets['1N2']['1']})
        if markets['1N2']['2'] > 50:
            tous_les_pronos.append({"match": f"{team_H} vs {team_A}", "market": f"Victoire {team_A}", "prob": markets['1N2']['2']})

    # ── Récapitulatif des value bets de la journée ──
    if match_odds_all:
        print_values(all_values)

    if tous_les_pronos:
        bons_pronos = [p for p in tous_les_pronos if p['prob'] > 60]
        bons_pronos.sort(key=lambda x: x['prob'], reverse=True)
        golden = bons_pronos[0] if bons_pronos else max(tous_les_pronos, key=lambda x: x['prob'])

        print("\n" + "⭐" * 55)
        print("👑  LE PRONOSTIC EN OR DE LA JOURNÉE  👑".center(55))
        print("⭐" * 55)
        print(f"   🎯 MATCH      : {golden['match']}")
        print(f"   🔮 SÉLECTION  : {golden['market']}")
        print(f"   🔥 CERTITUDE  : {golden['prob']:.1f}%")
        print("⭐" * 55 + "\n")

    conn.close()


if __name__ == "__main__":
    predict_today_matches()
