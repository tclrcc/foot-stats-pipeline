import sqlite3
import pandas as pd
import os
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(PROJECT_ROOT, "data/db/foot_stats.db")

def build_player_impact_table():
    print("⚙️ Génération du Moteur de Dépendance des Joueurs...")
    conn = sqlite3.connect(DB_PATH)
    
    # 1. Lecture directe avec Pandas pour mieux gérer les dates
    df_scorers = pd.read_sql_query("SELECT * FROM historical_goalscorers", conn)
    
    # Conversion forcée en datetime
    df_scorers['date'] = pd.to_datetime(df_scorers['date'], errors='coerce')
    
    # Filtrage manuel (plus sûr)
    five_years_ago = pd.Timestamp.now() - pd.DateOffset(years=5)
    df_recent = df_scorers[(df_scorers['date'] >= five_years_ago) & (df_scorers['own_goal'] == 0)]
    
    print(f"DEBUG: {len(df_recent)} buts trouvés après filtrage (5 dernières années).")
    
    if df_recent.empty:
        print("❌ Aucune donnée de buteur récente trouvée après filtrage.")
        # Debug : Affiche la date la plus récente en base
        print(f"DEBUG: Date la plus récente en base : {df_scorers['date'].max()}")
        return
        
    # Calcul du total des buts par équipe
    team_totals = df_recent.groupby('team')['scorer'].count().reset_index()
    team_totals = team_totals.rename(columns={'scorer': 'total_team_goals'})
    
    # Calcul des buts par joueur
    df_player_goals = df_recent.groupby(['team', 'scorer']).size().reset_index(name='goals')
    
    # Fusion
    df_merged = pd.merge(df_player_goals, team_totals, on='team')
    df_merged['dependency_pct'] = (df_merged['goals'] / df_merged['total_team_goals']) * 100
    
    # Filtrage des équipes avec assez de buts (10+)
    df_filtered = df_merged[df_merged['total_team_goals'] >= 10]
    
    # Top 1 par équipe
    df_stars = df_filtered.sort_values(['team', 'dependency_pct'], ascending=[True, False])
    df_stars = df_stars.drop_duplicates(subset=['team'], keep='first')
    
    df_final = df_stars.round(1)
    df_final.to_sql("team_dependencies", conn, if_exists="replace", index=False)
    
    print(f"✅ Table 'team_dependencies' créée avec succès.")
    conn.close()

if __name__ == "__main__":
    build_player_impact_table()
