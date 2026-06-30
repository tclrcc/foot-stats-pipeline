import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from scipy.stats import poisson
from dashboard import get_performance_dashboard

def calculate_value_bet(team_A: str, team_B: str, bookmaker_odds: list):
    """
    bookmaker_odds = [Cote_Team_A, Cote_Nul, Cote_Team_B]
    """
    dash = get_performance_dashboard()
    
    if team_A not in dash.index or team_B not in dash.index:
        print("❌ Une des équipes est introuvable dans la base de données.")
        return
        
    # L'algorithme de Poisson de base :
    # La force offensive de A affronte la faiblesse défensive de B
    lambda_A = (dash.loc[team_A, 'avg_scored'] + dash.loc[team_B, 'avg_conceded']) / 2
    lambda_B = (dash.loc[team_B, 'avg_scored'] + dash.loc[team_A, 'avg_conceded']) / 2
    
    # Matrice des scores (de 0 à 5 buts)
    max_goals = 6
    probs_A = poisson.pmf(np.arange(max_goals), lambda_A)
    probs_B = poisson.pmf(np.arange(max_goals), lambda_B)
    score_matrix = np.outer(probs_A, probs_B)
    
    prob_A_win = np.sum(np.tril(score_matrix, -1))
    prob_draw = np.sum(np.diag(score_matrix))
    prob_B_win = np.sum(np.triu(score_matrix, 1))
    
    fair_odds = [1/prob_A_win, 1/prob_draw, 1/prob_B_win]
    probs = [prob_A_win, prob_draw, prob_B_win]
    labels = [f"Victoire {team_A}", "Match Nul", f"Victoire {team_B}"]
    
    print(f"\n🔮 PRÉDICTION POISSON : {team_A} vs {team_B}")
    print(f"Buts attendus (xG simulés) -> {team_A}: {lambda_A:.2f} | {team_B}: {lambda_B:.2f}")
    print("-" * 75)
    
    for i in range(3):
        ev = (probs[i] * bookmaker_odds[i]) - 1
        status = "🟢 VALUE BET" if ev > 0.05 else ("🟡 Jouable" if ev > 0 else "🔴 À éviter")
        print(f"{labels[i]:<20} | Prob: {probs[i]*100:>4.1f}% | Cote Juste: {fair_odds[i]:>4.2f} | Bookmaker: {bookmaker_odds[i]:>4.2f} | EV: {ev*100:>5.1f}% | {status}")

if __name__ == "__main__":
    # Teste avec le match de ton choix et les vraies cotes de Betclic/Unibet
    calculate_value_bet("France", "Brazil", bookmaker_odds=[2.60, 3.10, 2.80])
