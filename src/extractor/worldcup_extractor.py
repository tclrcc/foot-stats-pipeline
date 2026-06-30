import sqlite3
import requests
import pandas as pd
import os

# FIX : dirname x3 depuis src/extractor/worldcup_extractor.py -> foot-stats-pipeline/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(PROJECT_ROOT, "data/db/foot_stats.db")

# ─────────────────────────────────────────────────────────────────────────────
# TABLE ELO COMPLÈTE — 48 ÉQUIPES CDM 2026
# ─────────────────────────────────────────────────────────────────────────────
ELO_RATINGS = [
    ('Argentina',              1790),
    ('France',                 1745),
    ('Brazil',                 1730),
    ('England',                1715),
    ('Spain',                  1720),
    ('Portugal',               1718),
    ('Germany',                1710),
    ('Netherlands',            1700),
    ('Belgium',                1685),
    ('Croatia',                1675),
    ('Uruguay',                1660),
    ('Colombia',               1660),
    ('Morocco',                1620),
    ('United States',          1615),
    ('Mexico',                 1610),
    ('Switzerland',            1640),
    ('Sweden',                 1645),
    ('Norway',                 1640),
    ('Austria',                1598),
    ('Czech Republic',         1590),
    ('Turkey',                 1585),
    ('Japan',                  1580),
    ('South Korea',            1565),
    ('Senegal',                1600),
    ('Ivory Coast',            1585),
    ('Algeria',                1555),
    ('Ecuador',                1560),
    ('Canada',                 1555),
    ('Ghana',                  1485),
    ('Egypt',                  1530),
    ('Iran',                   1540),
    ('Australia',              1530),
    ('Scotland',               1540),
    ('Tunisia',                1520),
    ('Paraguay',               1520),
    ('Bosnia and Herzegovina', 1530),
    ('Saudi Arabia',           1490),
    ('Cape Verde',             1450),
    ('Panama',                 1450),
    ('South Africa',           1435),
    ('DR Congo',               1425),
    ('Uzbekistan',             1415),
    ('New Zealand',            1420),
    ('Iraq',                   1470),
    ('Qatar',                  1445),
    ('Jordan',                 1435),
    ('Haiti',                  1385),
    ('Curaçao',                1380),
]


def repair_and_load_cdm():
    print("📡 Récupération des données CDM 2026 depuis worldcup26.ir...")

    df = None

    try:
        response = requests.get("https://worldcup26.ir/get/games", timeout=15)
        response.raise_for_status()
        raw = pd.DataFrame(response.json()['games'])

        raw = raw.rename(columns={
            'local_date':        'date',
            'home_team_name_en': 'home_team',
            'away_team_name_en': 'away_team',
            'home_score':        'home_goals',
            'away_score':        'away_goals',
        })

        raw['date']       = pd.to_datetime(raw['date'], format='mixed')
        raw['home_goals'] = pd.to_numeric(raw['home_goals'], errors='coerce')
        raw['away_goals'] = pd.to_numeric(raw['away_goals'], errors='coerce')

        # FIX CRITIQUE : L'API retourne finished=True pour TOUS les matchs (bug connu).
        # On détecte le vrai statut via la présence des scores.
        raw['is_finished'] = raw['home_goals'].notna() & raw['away_goals'].notna()

        df = raw[['date', 'home_team', 'away_team', 'home_goals', 'away_goals', 'is_finished']]

        nb_done = int(df['is_finished'].sum())
        nb_todo = int((~df['is_finished']).sum())
        print(f"   ✅ {len(df)} matchs récupérés ({nb_done} terminés, {nb_todo} à venir)")

    except Exception as e:
        print(f"   ⚠️  API inaccessible : {e}")
        print("   🔄 Fallback : reconstruction depuis le CSV Kaggle...")
        df = _build_cdm_from_kaggle()

    conn = sqlite3.connect(DB_PATH)
    df.to_sql("cdm_2026", conn, if_exists="replace", index=False)
    print("   📥 Table 'cdm_2026' mise à jour.")

    # ─── TABLE ELO ───────────────────────────────────────────────────────────
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS team_elo;")
    cursor.execute("""
        CREATE TABLE team_elo (
            team        TEXT PRIMARY KEY,
            elo_rating  INTEGER
        )
    """)
    seen = {}
    for team, elo in ELO_RATINGS:
        if team not in seen:
            seen[team] = elo
    cursor.executemany("INSERT INTO team_elo VALUES (?, ?)", seen.items())

    conn.commit()
    conn.close()
    print(f"   🏆 Table 'team_elo' créée avec {len(seen)} équipes.")
    print("✅ Base rafraîchie avec succès !")


def _build_cdm_from_kaggle():
    """Fallback si l'API worldcup26.ir est down ou retourne des données incohérentes."""
    raw_path = os.path.join(PROJECT_ROOT, "data/raw/results.csv")
    if not os.path.exists(raw_path):
        raise FileNotFoundError(f"CSV introuvable : {raw_path}")

    df_all = pd.read_csv(raw_path)
    df_cdm = df_all[
        (df_all['tournament'] == 'FIFA World Cup') &
        (df_all['date'] >= '2026-01-01')
    ].copy()

    df_cdm = df_cdm.rename(columns={
        'home_score': 'home_goals',
        'away_score': 'away_goals'
    })
    df_cdm['is_finished'] = df_cdm['home_goals'].notna()
    df_cdm['date']        = pd.to_datetime(df_cdm['date'])

    nb_done = int(df_cdm['is_finished'].sum())
    nb_todo = int((~df_cdm['is_finished']).sum())
    print(f"   ✅ {len(df_cdm)} matchs depuis Kaggle ({nb_done} terminés, {nb_todo} à venir)")

    return df_cdm[['date', 'home_team', 'away_team', 'home_goals', 'away_goals', 'is_finished']]


if __name__ == "__main__":
    repair_and_load_cdm()
