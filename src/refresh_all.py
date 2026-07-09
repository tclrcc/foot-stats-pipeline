"""
Orchestrateur : rafraîchit tout le pipeline dans le bon ordre.

Usage : python src/refresh_all.py
"""

import os
import sys

# Permet aux modules de s'importer entre eux
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from loader.history_loader import build_historical_database
from extractor.worldcup_extractor import refresh_cdm
from models.elo_engine import run as run_elo
from models.dixon_coles import run as run_dc
from player_impact import build_player_impact_table


def main():
    print("\n🚀 RAFRAÎCHISSEMENT COMPLET DU PIPELINE FOOT-STATS")
    print("=" * 60)

    # 0. Historique international depuis data/raw/*.csv (reproductible
    #    sur un clone frais : la base n'est plus versionnée)
    build_historical_database()

    # 1. Schedule + scores CDM 2026
    refresh_cdm()

    # 2. ELO dynamique sur tout l'historique
    run_elo()

    # 3. Estimation Dixon-Coles MLE (4 ans de matchs sérieux)
    run_dc()

    # 4. Dépendances joueurs
    build_player_impact_table()

    print("\n🎉 Pipeline rafraîchi de bout en bout.")
    print("   → Lance maintenant : python src/predict_upcoming.py\n")


if __name__ == "__main__":
    main()
