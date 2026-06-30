"""
Extracteur CDM 2026 — version 2.

Principes :
  - L'API worldcup26.ir ne sert QU'AU PLANNING (dates + équipes des 104 matchs).
    Ses scores sont fabriqués pour les matchs non joués et donc ignorés.
  - Le CSV Kaggle (`data/raw/results.csv`) est la source unique de vérité pour
    les scores réels.
  - Chaque match reçoit un statut tri-état :
      played    : score réel disponible (Kaggle)
      pending   : match passé mais pas encore ingéré dans Kaggle
      scheduled : match futur

Si l'API tombe, fallback complet sur Kaggle (donc pas de matchs à venir
visibles tant que la nouvelle source de planning n'est pas branchée).
"""

import os
import sqlite3
import requests
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(PROJECT_ROOT, "data/db/foot_stats.db")
KAGGLE_CSV = os.path.join(PROJECT_ROOT, "data/raw/results.csv")

# ─────────────────────────────────────────────────────────────────────────────
# Mapping noms API → noms canoniques (= ceux de Kaggle / table ELO)
# Ajouter ici toute future divergence détectée.
# ─────────────────────────────────────────────────────────────────────────────
TEAM_NAME_MAP = {
    "Democratic Republic of the Congo": "DR Congo",
}


def _canonical(name):
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return None
    return TEAM_NAME_MAP.get(name, name)


# ─────────────────────────────────────────────────────────────────────────────
# TABLE ELO (statique pour l'instant — sera dynamisée au Niveau 2)
# ─────────────────────────────────────────────────────────────────────────────
ELO_RATINGS = [
    ('Argentina', 1790), ('France', 1745), ('Brazil', 1730), ('England', 1715),
    ('Spain', 1720), ('Portugal', 1718), ('Germany', 1710), ('Netherlands', 1700),
    ('Belgium', 1685), ('Croatia', 1675), ('Uruguay', 1660), ('Colombia', 1660),
    ('Morocco', 1620), ('United States', 1615), ('Mexico', 1610), ('Switzerland', 1640),
    ('Sweden', 1645), ('Norway', 1640), ('Austria', 1598), ('Czech Republic', 1590),
    ('Turkey', 1585), ('Japan', 1580), ('South Korea', 1565), ('Senegal', 1600),
    ('Ivory Coast', 1585), ('Algeria', 1555), ('Ecuador', 1560), ('Canada', 1555),
    ('Ghana', 1485), ('Egypt', 1530), ('Iran', 1540), ('Australia', 1530),
    ('Scotland', 1540), ('Tunisia', 1520), ('Paraguay', 1520),
    ('Bosnia and Herzegovina', 1530), ('Saudi Arabia', 1490), ('Cape Verde', 1450),
    ('Panama', 1450), ('South Africa', 1435), ('DR Congo', 1425), ('Uzbekistan', 1415),
    ('New Zealand', 1420), ('Iraq', 1470), ('Qatar', 1445), ('Jordan', 1435),
    ('Haiti', 1385), ('Curaçao', 1380),
]


# ─────────────────────────────────────────────────────────────────────────────
# Étape 1 : récupérer le planning depuis l'API
# ─────────────────────────────────────────────────────────────────────────────
def fetch_schedule_from_api():
    """Retourne un DataFrame [date, home_team, away_team] — scores ignorés."""
    print("📡 Récupération du planning CDM 2026 depuis worldcup26.ir...")
    response = requests.get("https://worldcup26.ir/get/games", timeout=15)
    response.raise_for_status()

    raw = pd.DataFrame(response.json()["games"])
    raw = raw.rename(columns={
        "local_date":        "date",
        "home_team_name_en": "home_team",
        "away_team_name_en": "away_team",
    })

    raw["date"]      = pd.to_datetime(raw["date"], format="mixed")
    raw["home_team"] = raw["home_team"].map(_canonical)
    raw["away_team"] = raw["away_team"].map(_canonical)

    schedule = raw[["date", "home_team", "away_team"]].copy()
    print(f"   📅 {len(schedule)} matchs au planning.")
    return schedule


# ─────────────────────────────────────────────────────────────────────────────
# Étape 2 : charger les scores réels depuis Kaggle
# ─────────────────────────────────────────────────────────────────────────────
def load_kaggle_played_matches():
    """Retourne un DataFrame des matchs CDM 2026 réellement joués (Kaggle)."""
    if not os.path.exists(KAGGLE_CSV):
        raise FileNotFoundError(f"CSV Kaggle introuvable : {KAGGLE_CSV}")

    df = pd.read_csv(KAGGLE_CSV)
    wc = df[(df["tournament"] == "FIFA World Cup") & (df["date"] >= "2026-01-01")].copy()
    wc["date"] = pd.to_datetime(wc["date"])
    wc = wc.rename(columns={"home_score": "home_goals", "away_score": "away_goals"})
    wc["home_goals"] = pd.to_numeric(wc["home_goals"], errors="coerce").astype("Int64")
    wc["away_goals"] = pd.to_numeric(wc["away_goals"], errors="coerce").astype("Int64")

    print(f"   📦 {len(wc)} matchs CDM 2026 trouvés dans Kaggle.")
    return wc[["date", "home_team", "away_team", "home_goals", "away_goals"]]


# ─────────────────────────────────────────────────────────────────────────────
# Étape 3 : merger planning + scores réels + statut
# ─────────────────────────────────────────────────────────────────────────────
def build_cdm_table(schedule, kaggle_played, today=None):
    """
    Joint le planning avec les résultats Kaggle.
    Calcule le statut tri-état et le drapeau legacy is_finished.
    """
    today = today or pd.Timestamp.now().normalize()

    # Clé de jointure sur la date (sans l'heure) + équipes
    sched = schedule.copy()
    sched["match_date"] = sched["date"].dt.normalize()
    kag = kaggle_played.copy()
    kag["match_date"] = kag["date"].dt.normalize()

    merged = sched.merge(
        kag[["match_date", "home_team", "away_team", "home_goals", "away_goals"]],
        on=["match_date", "home_team", "away_team"],
        how="left",
    )

    # Statut : played si Kaggle a un score, sinon pending/scheduled selon la date
    has_score = merged["home_goals"].notna() & merged["away_goals"].notna()
    is_past   = merged["match_date"] <= today

    merged["match_status"] = "scheduled"
    merged.loc[is_past & ~has_score, "match_status"] = "pending"
    merged.loc[has_score, "match_status"] = "played"

    # Drapeau legacy pour compat avec predict_upcoming.py
    merged["is_finished"] = (merged["match_status"] == "played").astype(int)

    # Colonnes finales — on garde la date complète d'origine (avec l'heure)
    out = merged[[
        "date", "home_team", "away_team",
        "home_goals", "away_goals",
        "is_finished", "match_status",
    ]].sort_values("date").reset_index(drop=True)

    return out


# ─────────────────────────────────────────────────────────────────────────────
# Étape 4 : écriture en base
# ─────────────────────────────────────────────────────────────────────────────
def write_to_db(cdm_df):
    conn = sqlite3.connect(DB_PATH)
    cdm_df.to_sql("cdm_2026", conn, if_exists="replace", index=False)

    # Table ELO (refresh statique pour l'instant)
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
        seen.setdefault(team, elo)
    cursor.executemany("INSERT INTO team_elo VALUES (?, ?)", seen.items())

    conn.commit()
    conn.close()

    nb_played    = (cdm_df["match_status"] == "played").sum()
    nb_pending   = (cdm_df["match_status"] == "pending").sum()
    nb_scheduled = (cdm_df["match_status"] == "scheduled").sum()
    print(f"   📥 Table 'cdm_2026' : {nb_played} joués, "
          f"{nb_pending} en attente Kaggle, {nb_scheduled} à venir.")
    print(f"   🏆 Table 'team_elo' : {len(seen)} équipes.")


# ─────────────────────────────────────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────────────────────────────────────
def refresh_cdm():
    print("\n🔄 Rafraîchissement des données CDM 2026")
    print("=" * 60)

    try:
        schedule = fetch_schedule_from_api()
    except Exception as e:
        print(f"   ⚠️  API inaccessible ({e}). Fallback : planning depuis Kaggle.")
        schedule = load_kaggle_played_matches()[["date", "home_team", "away_team"]]

    kaggle_played = load_kaggle_played_matches()
    cdm = build_cdm_table(schedule, kaggle_played)
    write_to_db(cdm)

    # Avertir si des matchs en attente bloquent depuis trop longtemps
    pending = cdm[cdm["match_status"] == "pending"]
    if len(pending) > 0:
        oldest = pending["date"].min()
        gap_days = (pd.Timestamp.now() - oldest).days
        print(f"\n   ⚠️  {len(pending)} match(s) joué(s) en attente d'ingestion Kaggle.")
        print(f"      Plus ancien : {oldest.date()} ({gap_days} jours de retard).")
        print(f"      → Mettre à jour data/raw/results.csv depuis Kaggle si > 7 jours.")

    print("\n✅ Base rafraîchie avec succès !\n")


if __name__ == "__main__":
    refresh_cdm()
