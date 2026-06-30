import sqlite3
import pandas as pd
import os
from datetime import datetime, timedelta

# FIX : dirname x2 depuis src/player_impact.py -> foot-stats-pipeline/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "data/db/foot_stats.db")

def build_player_impact_table():
    print("⚙️ Génération du Moteur de Dépendance des Joueurs...")

    if not os.path.exists(DB_PATH):
        print(f"❌ Base de données introuvable : {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)

    # 1. Lecture directe avec Pandas
    df_scorers = pd.read_sql_query("SELECT * FROM historical_goalscorers", conn)

    # 2. Conversion forcée en datetime
    df_scorers['date'] = pd.to_datetime(df_scorers['date'], errors='coerce')

    # 3. Filtrage : 5 dernières années, hors buts contre son camp
    five_years_ago = pd.Timestamp.now() - pd.DateOffset(years=5)
    df_recent = df_scorers[
        (df_scorers['date'] >= five_years_ago) &
        (df_scorers['own_goal'] == False)
    ]

    print(f"  ℹ️  {len(df_recent)} buts trouvés après filtrage (5 dernières années, excl. CSC).")

    if df_recent.empty:
        print("❌ Aucune donnée de buteur récente. Vérifier la table 'historical_goalscorers'.")
        print(f"   Date la plus récente en base : {df_scorers['date'].max()}")
        conn.close()
        return

    # 4. Total buts par équipe
    team_totals = (
        df_recent.groupby('team')['scorer']
        .count()
        .reset_index()
        .rename(columns={'scorer': 'total_team_goals'})
    )

    # 5. Buts par joueur × équipe
    df_player_goals = (
        df_recent.groupby(['team', 'scorer'])
        .size()
        .reset_index(name='goals')
    )

    # 6. Fusion et calcul de la dépendance
    df_merged = pd.merge(df_player_goals, team_totals, on='team')
    df_merged['dependency_pct'] = (df_merged['goals'] / df_merged['total_team_goals']) * 100

    # 7. Garder uniquement les équipes avec assez de data (10+ buts)
    df_filtered = df_merged[df_merged['total_team_goals'] >= 10]

    # 8. Top 1 joueur par équipe (le plus décisif)
    df_stars = (
        df_filtered
        .sort_values(['team', 'dependency_pct'], ascending=[True, False])
        .drop_duplicates(subset=['team'], keep='first')
    )

    df_final = df_stars.round(1)
    df_final.to_sql("team_dependencies", conn, if_exists="replace", index=False)

    # 9. Aperçu des équipes CDM 2026 les plus dépendantes
    cdm_teams_query = """
        SELECT DISTINCT home_team as team FROM cdm_2026
        UNION
        SELECT DISTINCT away_team as team FROM cdm_2026
    """
    try:
        cdm_teams = pd.read_sql_query(cdm_teams_query, conn)['team'].tolist()
        df_cdm_stars = df_final[df_final['team'].isin(cdm_teams)].copy()
        df_cdm_stars = df_cdm_stars.sort_values('dependency_pct', ascending=False)

        print(f"\n✅ Table 'team_dependencies' créée — {len(df_final)} équipes.")
        print("\n🌟 TOP 15 — Dépendances joueurs (équipes CDM 2026) :")
        print(f"   {'Équipe':<30} {'Joueur clé':<25} {'Buts':>5}  {'Dépendance':>10}")
        print("   " + "─" * 75)
        for _, row in df_cdm_stars.head(15).iterrows():
            print(f"   {row['team']:<30} {row['scorer']:<25} {int(row['goals']):>5}  {row['dependency_pct']:>9.1f}%")
    except Exception:
        print(f"\n✅ Table 'team_dependencies' créée — {len(df_final)} équipes.")

    conn.close()


if __name__ == "__main__":
    build_player_impact_table()
