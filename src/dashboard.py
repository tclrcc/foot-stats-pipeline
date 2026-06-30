import sqlite3
import pandas as pd

def get_performance_dashboard():
    conn = sqlite3.connect("data/db/foot_stats.db")
    df = pd.read_sql_query("SELECT * FROM cdm_2026", conn)
    conn.close()
    
    # On sépare les stats Domicile et Extérieur, puis on les empile (concat)
    home_stats = df[['home_team', 'home_goals', 'away_goals']].rename(
        columns={'home_team': 'team', 'home_goals': 'goals_scored', 'away_goals': 'goals_conceded'})
        
    away_stats = df[['away_team', 'away_goals', 'home_goals']].rename(
        columns={'away_team': 'team', 'away_goals': 'goals_scored', 'home_goals': 'goals_conceded'})
    
    all_stats = pd.concat([home_stats, away_stats])
    
    # Calcul des moyennes par équipe
    dashboard = all_stats.groupby('team').agg(
        games_played=('goals_scored', 'count'),
        avg_scored=('goals_scored', 'mean'),
        avg_conceded=('goals_conceded', 'mean')
    ).round(2)
    
    return dashboard.sort_values(by='avg_scored', ascending=False)

if __name__ == "__main__":
    dash = get_performance_dashboard()
    print("\n📊 DASHBOARD CDM 2026 - PUISSANCE DES ÉQUIPES")
    print("-" * 60)
    print(dash.head(15).to_string())
