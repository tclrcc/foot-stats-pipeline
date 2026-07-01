"""
Ajustements contextuels spécifiques à la Coupe du Monde 2026 (USA/MEX/CAN).

Trois effets modélisés :

1. AVANTAGE HÔTE — USA, Mexique, Canada jouent "à domicile" (public acquis,
   déplacements courts, acclimatation). Les autres équipes sont en terrain
   neutre. On applique un multiplicateur d'attaque à la nation hôte.

2. PHASE À ÉLIMINATION DIRECTE — à partir des 8es (ici Round of 32 vu le
   format à 48), les matchs sont plus fermés : moins de buts, plus de prudence
   tactique. On atténue légèrement les deux xG. Effet documenté (les matchs à
   élimination directe en CDM marquent ~10-12% de buts en moins que les poules).

3. ALTITUDE — Mexico (2240m), Toluca (2660m), Guadalajara (1566m) : l'effort
   aérobie est dégradé pour les équipes non acclimatées. Pénalité d'attaque
   pour l'équipe visiteuse si elle ne vient pas d'un pays d'altitude.
   Ne s'active que si la ville du match est connue.
"""

import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# HYPERPARAMÈTRES
# ─────────────────────────────────────────────────────────────────────────────
HOST_NATIONS = {"United States", "Mexico", "Canada"}
HOST_ATTACK_BONUS = 1.12   # +12% sur l'attaque de l'hôte (avantage partiel,
                           # inférieur au +25% d'un vrai match à domicile club)

KNOCKOUT_START_DATE  = "2026-06-28"   # début Round of 32 (poules finies le 27)
KNOCKOUT_GOAL_FACTOR = 0.93           # -7% sur les xG en élimination directe

# Villes en altitude (mètres) et seuil d'effet significatif
ALTITUDE_VENUES = {
    "Mexico City": 2240,
    "Toluca":      2660,
    "Guadalajara": 1566,
}
ALTITUDE_THRESHOLD = 1200
ALTITUDE_PENALTY   = 0.93   # -7% sur l'attaque du visiteur non acclimaté

# Nations habituées à l'altitude (n'écopent pas de la pénalité)
HIGHLAND_NATIONS = {"Mexico", "Bolivia", "Ecuador", "Colombia", "Peru"}


# ─────────────────────────────────────────────────────────────────────────────
def is_knockout(match_date):
    """True si le match est en phase à élimination directe."""
    d = pd.Timestamp(match_date).normalize()
    return d >= pd.Timestamp(KNOCKOUT_START_DATE)


def altitude_of(city):
    """Altitude de la ville (0 si inconnue ou plaine)."""
    if not city:
        return 0
    return ALTITUDE_VENUES.get(city, 0)


# ─────────────────────────────────────────────────────────────────────────────
# Calcul des multiplicateurs contextuels
# ─────────────────────────────────────────────────────────────────────────────
def match_context(home_team, away_team, match_date, city=None):
    """
    Renvoie un dict :
        lam_mult   : multiplicateur sur λ (attaque équipe H)
        mu_mult    : multiplicateur sur μ (attaque équipe A)
        neutral    : False si un hôte joue (info, non utilisée directement ici)
        notes      : liste lisible des ajustements appliqués
    """
    lam_mult = 1.0
    mu_mult  = 1.0
    notes = []
    neutral = True

    # 1) Avantage hôte
    if home_team in HOST_NATIONS:
        lam_mult *= HOST_ATTACK_BONUS
        neutral = False
        notes.append(f"Hôte {home_team} : attaque ×{HOST_ATTACK_BONUS}")
    if away_team in HOST_NATIONS:
        mu_mult *= HOST_ATTACK_BONUS
        neutral = False
        notes.append(f"Hôte {away_team} : attaque ×{HOST_ATTACK_BONUS}")

    # 2) Phase à élimination directe
    if is_knockout(match_date):
        lam_mult *= KNOCKOUT_GOAL_FACTOR
        mu_mult  *= KNOCKOUT_GOAL_FACTOR
        notes.append(f"Élimination directe : xG ×{KNOCKOUT_GOAL_FACTOR}")

    # 3) Altitude (si ville connue et en altitude)
    alt = altitude_of(city)
    if alt >= ALTITUDE_THRESHOLD:
        if home_team not in HIGHLAND_NATIONS:
            lam_mult *= ALTITUDE_PENALTY
            notes.append(f"Altitude {city} ({alt}m) : {home_team} non acclimaté ×{ALTITUDE_PENALTY}")
        if away_team not in HIGHLAND_NATIONS:
            mu_mult *= ALTITUDE_PENALTY
            notes.append(f"Altitude {city} ({alt}m) : {away_team} non acclimaté ×{ALTITUDE_PENALTY}")

    return {
        "lam_mult": lam_mult,
        "mu_mult":  mu_mult,
        "neutral":  neutral,
        "notes":    notes,
    }


if __name__ == "__main__":
    # Démo
    cases = [
        ("Belgium", "Senegal", "2026-07-01", None),        # knockout, pas d'hôte
        ("United States", "Bosnia and Herzegovina", "2026-07-01", None),  # hôte + knockout
        ("Mexico", "Germany", "2026-06-15", "Mexico City"), # hôte + altitude, poules
        ("France", "Brazil", "2026-06-20", None),           # poules, neutre
    ]
    for h, a, d, c in cases:
        ctx = match_context(h, a, d, c)
        print(f"\n{h} vs {a}  ({d}, {c or 'ville inconnue'})")
        print(f"   λ×{ctx['lam_mult']:.3f}  μ×{ctx['mu_mult']:.3f}")
        for n in ctx["notes"]:
            print(f"   • {n}")
        if not ctx["notes"]:
            print("   (aucun ajustement — match neutre de poule)")
