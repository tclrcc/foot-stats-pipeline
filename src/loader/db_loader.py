import sqlite3
import pandas as pd
import os

# Chemin absolu pour s'assurer que la BDD est toujours au bon endroit
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(BASE_DIR, "data/db/foot_stats.db")

def init_db():
    """Crée la base de données et la table si elles n'existent pas."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Création de la table 'matches' avec une sécurité anti-doublon
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        side TEXT,
        opponent_name TEXT,
        team_goals INTEGER,
        opponent_goals INTEGER,
        team_xG REAL,
        team_xGA REAL,
        xG_diff REAL,
        result TEXT,
        UNIQUE(date, opponent_name) -- Empêche d'insérer le même match en double
    )
    ''')
    conn.commit()
    conn.close()
    print("✅ Base de données SQLite prête.")

def save_to_db(df: pd.DataFrame, table_name: str = "matches"):
    """Insère le DataFrame dans la base de données de manière sécurisée."""
    conn = sqlite3.connect(DB_PATH)
    
    try:
        # La puissance de Pandas : on insère tout le tableau en une ligne
        # if_exists='append' permet d'ajouter les nouveaux matchs sans écraser l'historique
        df.to_sql(table_name, conn, if_exists='append', index=False)
        print(f"📥 {len(df)} matchs injectés avec succès dans la table '{table_name}'.")
    except sqlite3.IntegrityError:
        print("⚠️ Certains matchs sont déjà en base (Ignorés grâce à la contrainte UNIQUE).")
    except Exception as e:
        print(f"❌ Erreur SQL lors de l'insertion : {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
