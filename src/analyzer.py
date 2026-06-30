import sqlite3
import pandas as pd
import os

# Chemin vers ta base de données
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "../data/db/foot_stats.db")

def check_recent_matches(limit=5):
    """
    Se connecte à SQLite et récupère les derniers matchs.
    """
    if not os.path.exists(DB_PATH):
        print("❌ La base de données est introuvable.")
        return

    conn = sqlite3.connect(DB_PATH)
    
    # Requête SQL simple pour récupérer les matchs triés par date
    query = f"SELECT date, opponent_name, team_goals, opponent_goals, team_xG, team_xGA, xG_diff FROM matches ORDER BY date DESC LIMIT {limit}"
    
    # Pandas exécute la requête et transforme le résultat directement en DataFrame
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if df.empty:
        print("⚠️ La base de données est vide.")
        return
        
    print(f"✅ Voici les {limit} derniers matchs enregistrés :")
    print(df.to_string(index=False))
    
    # --- DÉBUT DE L'ANALYSE POUR LES PARIS ---
    print("\n📈 Analyse de la forme (sur ces matchs) :")
    xg_moyen = df['team_xG'].mean()
    xga_moyen = df['team_xGA'].mean()
    
    print(f"Attaque : {xg_moyen:.2f} xG créés / match")
    print(f"Défense : {xga_moyen:.2f} xG concédés / match")
    
    if xg_moyen > 1.5 and xga_moyen < 1.0:
        print("💡 Verdict : Équipe en très grande forme (Forte domination).")
    elif xg_moyen < 1.0:
        print("💡 Verdict : Attaque en difficulté (Peu d'occasions créées).")

if __name__ == "__main__":
    check_recent_matches(5)
