"""
Moteur de détection de value bets.

Pour chaque sélection cotée par le bookmaker :
  1. Proba modèle p_model    (Dixon-Coles, calibré au Niveau 5)
  2. Proba implicite bookmaker p_book = 1/cote (contient la marge)
  3. Proba "juste" p_fair = p_book normalisée sur le marché (marge retirée)
  4. Espérance : EV = p_model × cote − 1
  5. Edge     : p_model − p_fair  (désaccord avec la vraie opinion du book)
  6. Mise Kelly fractionnée : f* = (b·p − q)/b, appliquée à KELLY_FRACTION

Une value est retenue si :
  - EV ≥ EV_MIN
  - cote ≥ MIN_ODDS  (on évite les toutes petites cotes, peu rentables)
  - p_model ≥ P_MIN  (on évite de miser sur des issues trop improbables)

Prérequis : le modèle doit être calibré (cf. backtest.py). Sans ça, les EV
calculées sont trompeuses.
"""

# Seuils (ajustables)
EV_MIN         = 0.05   # 5% d'espérance minimum
MIN_ODDS       = 1.50   # cote plancher
P_MIN          = 0.10   # proba modèle plancher
KELLY_FRACTION = 0.25   # Kelly fractionné (1/4) pour limiter la variance
KELLY_CAP      = 0.05   # mise max 5% de la bankroll par pari (garde-fou)


# ─────────────────────────────────────────────────────────────────────────────
# Correspondance sélection cotée ↔ proba modèle
# ─────────────────────────────────────────────────────────────────────────────
def _model_prob_for(selection_key, market_name, model_probs):
    """
    Mappe une sélection de cote (ex. '1', 'Over 2.5', 'Oui') vers la proba
    correspondante du modèle. Renvoie None si non gérée.
    """
    m = market_name.lower()
    s = selection_key.strip().lower()

    if "1n2" in m or "h2h" in m:
        return {"1": model_probs["home"], "n": model_probs["draw"],
                "2": model_probs["away"]}.get(s)

    if "total" in m or "over" in m or "under" in m:
        if s in ("over 2.5", "+2.5", "plus 2.5"):   return model_probs["over_2_5"]
        if s in ("under 2.5", "-2.5", "moins 2.5"): return model_probs["under_2_5"]
        if s in ("over 1.5", "+1.5", "plus 1.5"):   return model_probs["over_1_5"]
        return None

    if "btts" in m or "deux marquent" in m:
        if s in ("oui", "yes"): return model_probs["btts_yes"]
        if s in ("non", "no"):  return model_probs["btts_no"]
        return None

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Retrait de la marge (vig) sur un marché
# ─────────────────────────────────────────────────────────────────────────────
def remove_vig(odds_dict):
    """
    Renvoie {selection: p_fair} en normalisant les probas implicites.
    Méthode proportionnelle (standard, robuste).
    """
    implied = {k: 1.0 / v for k, v in odds_dict.items() if v and v > 1.0}
    total = sum(implied.values())
    if total <= 0:
        return {}
    return {k: p / total for k, p in implied.items()}, total - 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Kelly
# ─────────────────────────────────────────────────────────────────────────────
def kelly_fraction(p_model, odds):
    """Fraction de Kelly optimale (avant application de KELLY_FRACTION)."""
    b = odds - 1.0
    q = 1.0 - p_model
    if b <= 0:
        return 0.0
    f = (b * p_model - q) / b
    return max(0.0, f)


# ─────────────────────────────────────────────────────────────────────────────
# Analyse d'un match
# ─────────────────────────────────────────────────────────────────────────────
def find_values_for_match(match_name, model_probs, match_odds):
    """
    Renvoie la liste des values détectées pour un match.
    match_odds : {market_name: {selection: cote}}
    """
    values = []
    for market_name, selections in match_odds.items():
        vig_result = remove_vig(selections)
        if not vig_result:
            continue
        fair_probs, overround = vig_result

        for sel_key, odds in selections.items():
            if not odds or odds < 1.01:
                continue
            p_model = _model_prob_for(sel_key, market_name, model_probs)
            if p_model is None:
                continue

            p_fair = fair_probs.get(sel_key, 1.0 / odds)
            ev = p_model * odds - 1.0
            edge = p_model - p_fair

            # Critères de sélection
            if ev < EV_MIN or odds < MIN_ODDS or p_model < P_MIN:
                continue

            k_full = kelly_fraction(p_model, odds)
            stake = min(KELLY_CAP, k_full * KELLY_FRACTION)

            values.append({
                "match": match_name,
                "market": market_name,
                "selection": sel_key,
                "odds": round(odds, 2),
                "p_model": round(p_model * 100, 1),
                "p_fair": round(p_fair * 100, 1),
                "edge": round(edge * 100, 1),
                "ev": round(ev * 100, 1),
                "kelly_stake_pct": round(stake * 100, 2),
                "overround": round(overround * 100, 1),
            })

    return values


def rank_values(all_values):
    """Trie les values par EV décroissant."""
    return sorted(all_values, key=lambda v: v["ev"], reverse=True)


# ─────────────────────────────────────────────────────────────────────────────
# Affichage
# ─────────────────────────────────────────────────────────────────────────────
def print_values(all_values, bankroll=None):
    if not all_values:
        print("\n💤 Aucune value détectée avec les cotes fournies "
              f"(seuils : EV≥{EV_MIN*100:.0f}%, cote≥{MIN_ODDS}, p≥{P_MIN*100:.0f}%).")
        return

    ranked = rank_values(all_values)
    print("\n" + "=" * 92)
    print(f"💎 VALUE BETS DÉTECTÉES ({len(ranked)})".center(92))
    print("=" * 92)
    print(f"   {'Match':<26} {'Marché':<10} {'Sél.':<10} {'Cote':>5} "
          f"{'pMod':>6} {'pJuste':>7} {'Edge':>6} {'EV':>6} {'Kelly':>7}")
    print("   " + "─" * 86)
    for v in ranked:
        stake_str = f"{v['kelly_stake_pct']:.2f}%"
        if bankroll:
            stake_str = f"{v['kelly_stake_pct']/100*bankroll:.0f}€"
        print(f"   {v['match']:<26} {v['market']:<10} {v['selection']:<10} "
              f"{v['odds']:>5.2f} {v['p_model']:>5.1f}% {v['p_fair']:>6.1f}% "
              f"{v['edge']:>+5.1f}% {v['ev']:>+5.1f}% {stake_str:>7}")
    print("   " + "─" * 86)
    print("   pMod = proba modèle · pJuste = proba book sans marge · "
          "EV = espérance · Kelly = mise conseillée")
    if bankroll:
        total_stake = sum(v['kelly_stake_pct']/100*bankroll for v in ranked)
        print(f"   Mise totale conseillée : {total_stake:.0f}€ "
              f"(bankroll {bankroll:.0f}€, Kelly 1/4)")
