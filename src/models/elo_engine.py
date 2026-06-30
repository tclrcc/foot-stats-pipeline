"""
Moteur ELO dynamique pour le foot international.

Calcule un ELO en parcourant chronologiquement TOUS les matchs historiques
(49k+ matchs depuis 1872) et l'écrit dans la table `team_elo`.

L'historique complet est aussi écrit dans `team_elo_history` (utilisé plus
tard pour le backtest du Niveau 5).

Doit être lancé après `worldcup_extractor.py` pour intégrer les derniers
matchs CDM 2026.
"""

import os
import sqlite3
import pandas as pd
from collections import defaultdict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(PROJECT_ROOT, "data/db/foot_stats.db")

INITIAL_ELO    = 1500
HOME_ADVANTAGE = 100   # points ELO ajoutés à l'équipe à domicile (sauf neutre)

# ─────────────────────────────────────────────────────────────────────────────
# K-FACTOR par importance de compétition.
# Calibré à partir de la grille FIFA, avec quelques regroupements.
# Liste ordonnée : la première règle qui matche gagne.
# ─────────────────────────────────────────────────────────────────────────────
K_RULES = [
    # K=60 — Phase finale CDM
    (lambda t: t == "FIFA World Cup", 60),

    # K=50 — Phases finales continentales majeures
    (lambda t: t in {
        "UEFA Euro", "Copa América", "African Cup of Nations",
        "AFC Asian Cup", "Gold Cup", "CONCACAF Championship",
        "Confederations Cup",
    }, 50),

    # K=40 — Qualifs CDM
    (lambda t: t == "FIFA World Cup qualification", 40),

    # K=35 — Nations Leagues + phases finales continentales secondaires
    (lambda t: t in {
        "UEFA Nations League", "CONCACAF Nations League",
        "AFF Championship", "Arab Cup", "CECAFA Cup",
        "Gulf Cup", "WAFF Championship", "SAFF Cup",
        "EAFF Championship", "Oceania Nations Cup",
    }, 35),

    # K=30 — Toutes les qualifications continentales
    (lambda t: t.endswith("qualification"), 30),

    # K=25 — Jeux Olympiques (U-23 + 3 overage)
    (lambda t: t == "Olympic Games", 25),

    # K=20 — Amicaux
    (lambda t: t == "Friendly", 20),
]

# Tout le reste (tournois mineurs / régionaux / exhibition) tombe à K=15
DEFAULT_K = 15


def get_k_factor(tournament):
    for rule, k in K_RULES:
        if rule(tournament):
            return k
    return DEFAULT_K


def goal_diff_multiplier(goal_diff):
    """Multiplicateur de différence de buts (formule FIFA classique)."""
    if goal_diff < 2:
        return 1.0
    if goal_diff == 2:
        return 1.5
    return (11.0 + goal_diff) / 8.0


def expected_score(rating_home, rating_away, neutral):
    """Espérance de victoire de l'équipe à domicile (incluant l'avantage terrain)."""
    ha = 0 if neutral else HOME_ADVANTAGE
    return 1.0 / (1.0 + 10.0 ** ((rating_away - rating_home - ha) / 400.0))


# ─────────────────────────────────────────────────────────────────────────────
# Boucle principale de calcul
# ─────────────────────────────────────────────────────────────────────────────
def compute_elo():
    print("⚙️  Calcul du moteur ELO dynamique...")
    conn = sqlite3.connect(DB_PATH)

    df = pd.read_sql_query("""
        SELECT date, home_team, away_team, home_score, away_score,
               tournament, neutral
        FROM historical_matches
        WHERE home_score IS NOT NULL AND away_score IS NOT NULL
        ORDER BY date ASC
    """, conn)

    print(f"   📊 {len(df):,} matchs à traiter (1872 → {df['date'].max()}).")

    ratings = defaultdict(lambda: INITIAL_ELO)
    history_rows = []

    # Cast une seule fois
    df["home_score"] = df["home_score"].astype(int)
    df["away_score"] = df["away_score"].astype(int)
    df["neutral"]    = df["neutral"].astype(bool)

    for row in df.itertuples(index=False):
        home, away = row.home_team, row.away_team
        R_h, R_a = ratings[home], ratings[away]

        E_h = expected_score(R_h, R_a, row.neutral)
        E_a = 1.0 - E_h

        # Résultat observé
        if row.home_score > row.away_score:
            S_h, S_a = 1.0, 0.0
        elif row.home_score < row.away_score:
            S_h, S_a = 0.0, 1.0
        else:
            S_h, S_a = 0.5, 0.5

        K = get_k_factor(row.tournament)
        G = goal_diff_multiplier(abs(row.home_score - row.away_score))

        delta_h = K * G * (S_h - E_h)
        delta_a = K * G * (S_a - E_a)

        new_R_h = R_h + delta_h
        new_R_a = R_a + delta_a

        history_rows.append((row.date, home, new_R_h, away, new_R_a))

        ratings[home] = new_R_h
        ratings[away] = new_R_a

    print(f"   ✅ ELO calculé pour {len(ratings)} équipes.")
    return ratings, history_rows, conn


# ─────────────────────────────────────────────────────────────────────────────
# Écriture en base
# ─────────────────────────────────────────────────────────────────────────────
def write_elo(ratings, history_rows, conn):
    cursor = conn.cursor()

    # 1) Table principale : ELO actuel
    cursor.execute("DROP TABLE IF EXISTS team_elo;")
    cursor.execute("""
        CREATE TABLE team_elo (
            team        TEXT PRIMARY KEY,
            elo_rating  REAL,
            last_updated TEXT
        )
    """)
    now = pd.Timestamp.now().strftime("%Y-%m-%d")
    cursor.executemany(
        "INSERT INTO team_elo VALUES (?, ?, ?)",
        [(team, round(r, 2), now) for team, r in ratings.items()]
    )

    # 2) Historique complet : ELO à chaque match
    cursor.execute("DROP TABLE IF EXISTS team_elo_history;")
    cursor.execute("""
        CREATE TABLE team_elo_history (
            date           TEXT,
            home_team      TEXT,
            home_elo_after REAL,
            away_team      TEXT,
            away_elo_after REAL
        )
    """)
    cursor.executemany(
        "INSERT INTO team_elo_history VALUES (?, ?, ?, ?, ?)",
        [(d, h, round(rh, 2), a, round(ra, 2)) for d, h, rh, a, ra in history_rows]
    )
    cursor.execute("CREATE INDEX idx_elo_hist_date ON team_elo_history(date);")
    cursor.execute("CREATE INDEX idx_elo_hist_home ON team_elo_history(home_team);")
    cursor.execute("CREATE INDEX idx_elo_hist_away ON team_elo_history(away_team);")

    conn.commit()
    print(f"   💾 Table 'team_elo' : {len(ratings)} équipes.")
    print(f"   💾 Table 'team_elo_history' : {len(history_rows):,} snapshots.")


# ─────────────────────────────────────────────────────────────────────────────
# Aperçu — top 25
# ─────────────────────────────────────────────────────────────────────────────
def print_top_teams(ratings, top_n=25):
    sorted_teams = sorted(ratings.items(), key=lambda x: x[1], reverse=True)
    print(f"\n🏆 TOP {top_n} — Classement ELO actuel")
    print("   " + "─" * 50)
    print(f"   {'#':<4} {'Équipe':<30} {'ELO':>8}")
    print("   " + "─" * 50)
    for i, (team, r) in enumerate(sorted_teams[:top_n], 1):
        print(f"   {i:<4} {team:<30} {r:>8.1f}")


# ─────────────────────────────────────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────────────────────────────────────
def run():
    print("\n🔄 Moteur ELO dynamique")
    print("=" * 60)
    ratings, history_rows, conn = compute_elo()
    write_elo(ratings, history_rows, conn)
    print_top_teams(ratings, top_n=25)
    conn.close()
    print("\n✅ ELO mis à jour avec succès !\n")


if __name__ == "__main__":
    run()
