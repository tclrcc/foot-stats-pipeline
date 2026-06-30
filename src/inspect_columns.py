import sqlite3
import pandas as pd

def inspect():
    conn = sqlite3.connect("data/db/foot_stats.db")
    
    # 1. Vérifier le nom des tables disponibles
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
    print(f"📁 Tables trouvées dans la base : {[t[0] for t in tables]}")
    
    # 2. Inspecter la structure de cdm_2026
    if ('cdm_2026',) in tables:
        df = pd.read_sql_query("SELECT * FROM cdm_2026 LIMIT 1", conn)
        print(f"\n🔍 Colonnes exactes de la table 'cdm_2026' :")
        print(df.columns.tolist())
    else:
        print("\n⚠️ La table 'cdm_2026' n'existe pas ou porte un autre nom.")
        
    conn.close()

if __name__ == "__main__":
    inspect()
