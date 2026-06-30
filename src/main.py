import asyncio
import sys
import os

# Permet d'importer les autres dossiers proprement
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from extractor.understat_extractor import get_team_stats
from loader.db_loader import init_db, save_to_db

async def run_pipeline():
    print("🚀 --- DÉMARRAGE DU PIPELINE ETL --- 🚀\n")
    
    # 1. Initialisation de la BDD (Load)
    init_db()
    
    # 2. Extraction & Transformation (Extract & Transform)
    # Tu pourras faire une boucle sur tes équipes favorites plus tard
    equipe_cible = "Lille"
    df_lille = await get_team_stats(equipe_cible, season=2025)
    
    # 3. Chargement en base (Load)
    if df_lille is not None:
        save_to_db(df_lille)
        print("\n✅ Flux de données terminé avec succès !")

if __name__ == "__main__":
    asyncio.run(run_pipeline())
