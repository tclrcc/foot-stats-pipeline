"""
Module d'ajustement de l'attaque (paramètre α du Dixon-Coles) en fonction
des absences déclarées et de la profondeur d'effectif.

Modèle :
    Pour chaque joueur absent de dépendance d :
        - On évalue la "densité de remplacement" = somme des dépendances
          des top 2-6 buteurs restants
        - shortfall = max(0.3, d / (d + density_remplaçants))
          * Le plancher 0.3 reflète qu'un titulaire absent crée toujours une
            perte minimale (chimie, automatismes), même avec super remplaçant
        - impact_individuel = d × shortfall
    Pour plusieurs absents, les impacts s'additionnent (plafonnés à 60%
    pour éviter qu'avec 3-4 forfaits l'équipe devienne fictive).

    α_ajusté = α × (1 - total_impact)

Limites :
    - Ne couvre que l'attaque (les défenseurs/gardien ne sont pas dans
      les données de buteurs). Le Niveau 6 ajoutera la défense via les
      lineups API-Football.
    - Suppose que les forfaits sont des joueurs présents dans le top 8
      des buteurs. Un absent inconnu (ex. un milieu créatif sans but)
      sera ignoré — c'est conservateur.
"""

import os
import json
import sqlite3
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH      = os.path.join(PROJECT_ROOT, "data/db/foot_stats.db")
ABSENCES_FILE = os.path.join(PROJECT_ROOT, "data/absences.json")

# Hyperparamètres
SHORTFALL_FLOOR = 0.30   # perte minimale même avec super remplaçant
TOTAL_IMPACT_CAP = 0.60  # plafond cumulé multi-absents (équipe pas annihilée)
REPLACEMENT_DEPTH = 6    # on regarde le top 2-6 comme remplaçants potentiels


# ─────────────────────────────────────────────────────────────────────────────
# Chargement
# ─────────────────────────────────────────────────────────────────────────────
def load_scorer_depth():
    """Renvoie un DataFrame indexé par team, avec les 8 meilleurs buteurs."""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM team_scorer_depth ORDER BY team, rank", conn)
    conn.close()
    return df


def load_absences():
    """
    Lit le fichier data/absences.json s'il existe. Format attendu :
    {
        "France": ["Kylian Mbappé"],
        "Norway": ["Erling Haaland"],
        ...
    }
    Les clés commençant par "_" sont des méta-données ignorées (doc, exemples).
    Renvoie {} si le fichier n'existe pas.
    """
    if not os.path.exists(ABSENCES_FILE):
        return {}
    with open(ABSENCES_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if not k.startswith("_")}


# ─────────────────────────────────────────────────────────────────────────────
# Calcul de l'impact d'une liste d'absents pour UNE équipe
# ─────────────────────────────────────────────────────────────────────────────
def compute_attack_adjustment(team, absent_players, depth_df):
    """
    Renvoie un dict avec :
        - multiplier        : facteur à appliquer à α (ex. 0.83 = -17%)
        - total_impact      : impact cumulé (0 à TOTAL_IMPACT_CAP)
        - matched_absents   : liste des joueurs effectivement matchés dans la profondeur
        - unmatched_absents : liste des absents non trouvés (warning)
        - detail            : liste de (joueur, dep%, shortfall, impact%)
    """
    team_depth = depth_df[depth_df["team"] == team].copy()

    if team_depth.empty or not absent_players:
        return {
            "multiplier": 1.0,
            "total_impact": 0.0,
            "matched_absents": [],
            "unmatched_absents": list(absent_players or []),
            "detail": [],
        }

    matched = []
    unmatched = []
    detail = []
    total_impact = 0.0

    for player in absent_players:
        match = team_depth[team_depth["scorer"] == player]
        if match.empty:
            unmatched.append(player)
            continue

        dep = float(match["dependency_pct"].iloc[0])

        # Remplaçants potentiels = rang 2..6 hors joueur absent et hors absents
        # déjà matchés (pour éviter de "compter sur" un joueur qu'on a déjà retiré)
        all_absent_so_far = set(matched + [player])
        replacements = team_depth[
            (~team_depth["scorer"].isin(all_absent_so_far))
            & (team_depth["rank"] <= REPLACEMENT_DEPTH)
        ]
        density_replacements = float(replacements["dependency_pct"].sum())

        shortfall = max(SHORTFALL_FLOOR, dep / (dep + density_replacements))
        individual_impact = (dep / 100.0) * shortfall  # ramené en fraction

        matched.append(player)
        detail.append((player, dep, shortfall, individual_impact * 100))
        total_impact += individual_impact

    total_impact = min(TOTAL_IMPACT_CAP, total_impact)

    return {
        "multiplier": 1.0 - total_impact,
        "total_impact": total_impact,
        "matched_absents": matched,
        "unmatched_absents": unmatched,
        "detail": detail,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Démo / inspection en ligne de commande
# ─────────────────────────────────────────────────────────────────────────────
def show_team_depth(team_names=None):
    """Affiche la profondeur d'effectif des équipes demandées (ou toutes CDM)."""
    depth_df = load_scorer_depth()

    if team_names is None:
        # Toutes les équipes CDM 2026
        conn = sqlite3.connect(DB_PATH)
        team_names = pd.read_sql_query(
            "SELECT DISTINCT home_team t FROM cdm_2026 WHERE home_team IS NOT NULL "
            "UNION SELECT DISTINCT away_team FROM cdm_2026 WHERE away_team IS NOT NULL",
            conn
        )["t"].tolist()
        conn.close()

    for team in sorted(team_names):
        sub = depth_df[depth_df["team"] == team].head(8)
        if sub.empty:
            continue
        print(f"\n{team}")
        print("   " + "─" * 60)
        for _, r in sub.iterrows():
            bar = "█" * max(1, int(r["dependency_pct"] / 2))
            print(f"   #{int(r['rank'])} {r['scorer']:<25} {int(r['goals']):>3}b "
                  f"{r['dependency_pct']:>5.1f}% {bar}")


def simulate_absence(team, absent_players):
    """Simule un scénario d'absence et affiche le résultat."""
    depth_df = load_scorer_depth()
    res = compute_attack_adjustment(team, absent_players, depth_df)

    print(f"\n📋 Simulation : {team} sans {absent_players}")
    print("   " + "─" * 60)
    if res["unmatched_absents"]:
        print(f"   ⚠️  Joueurs absents non trouvés dans le top 8 : "
              f"{res['unmatched_absents']}  (ignorés — impact 0)")
    for player, dep, shortfall, impact in res["detail"]:
        print(f"   • {player:<25} dep={dep:5.1f}%  shortfall={shortfall:.2f}  "
              f"→ perte {impact:.1f}% de α")
    print(f"   ───")
    print(f"   ⇒ α multiplié par {res['multiplier']:.3f}  "
          f"(perte totale = {res['total_impact']*100:.1f}%)")


if __name__ == "__main__":
    print("=" * 60)
    print("DÉMO : impact des absences sur l'attaque")
    print("=" * 60)

    simulate_absence("France",    ["Kylian Mbappé"])
    simulate_absence("Norway",    ["Erling Haaland"])
    simulate_absence("Argentina", ["Lionel Messi"])
    simulate_absence("France",    ["Kylian Mbappé", "Antoine Griezmann"])
    simulate_absence("England",   ["Harry Kane", "Bukayo Saka"])
