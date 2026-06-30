import sys
import os
import sqlite3
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW_DIR = os.path.join(PROJECT_ROOT, "data/raw")
DB_PATH = os.path.join(PROJECT_ROOT, "data/db/foot_stats.db")

def clean_and_load_file(filename, table_name, conn, date_col='date'):
    filepath = os.path.join(RAW_DIR, filename)
    if not os.path.exists(filepath):
        print(f"⚠️ Fichier manquant : {filename} (Ignoré)")
        return False
    
    print(f"⏳ Traitement de {filename} -> Table '{table_name}'...")
    df = pd.read_csv(filepath)
    
    # Normalisation des dates si la colonne existe
    if date_col in df.columns:
        df[date_col] = pd.to_datetime(df[date_col], errors='coerce').dt.strftime('%Y-%m-%d')
        df = df.dropna(subset=[date_col])
    
    # Injection SQL
    df.to_sql(table_name, conn, if_exists="replace", index=False)
    print(f"  ✅ {len(df)} lignes insérées.")
    return True

def build_historical_database():
    print("🗄️ Initialisation de l'intégration massive Kaggle...")
    conn = sqlite3.connect(DB_PATH)
    
    # 1. Chargement des 4 fichiers
    load_success = all([
        clean_and_load_file("results.csv", "historical_matches", conn),
        clean_and_load_file("goalscorers.csv", "historical_goalscorers", conn),
        clean_and_load_file("shootouts.csv", "historical_shootouts", conn),
        clean_and_load_file("former_names.csv", "historical_former_names", conn, date_col=None)
    ])

    if load_success:
        print("\n⚙️ Optimisation des index relationnels...")
        cursor = conn.cursor()
        
        # Index pour historical_matches (Recherches ultra-rapides)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_match_date ON historical_matches(date);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_match_home ON historical_matches(home_team);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_match_away ON historical_matches(away_team);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_match_tourney ON historical_matches(tournament);")
        
        # Index pour goalscorers (Liaisons et recherches par joueur)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_goal_match ON historical_goalscorers(date, home_team, away_team);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_goal_scorer ON historical_goalscorers(scorer);")
        
        # Index pour shootouts
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_shootout_match ON historical_shootouts(date, home_team, away_team);")
        
        conn.commit()
        print("✅ Base de données historique structurée et indexée avec succès !")
    else:
        print("\n❌ L'intégration a été partielle en raison de fichiers manquants.")

    conn.close()

if __name__ == "__main__":
    build_historical_database()
