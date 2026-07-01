"""
Ingestion des cotes de matchs.

Deux sources supportées :
  1. Fichier manuel data/odds.json  (toujours dispo, aucune dépendance réseau)
  2. API the-odds-api.com            (optionnelle — clé dans .env : ODDS_API_KEY)

Schéma normalisé renvoyé (dict) :
  {
      "France vs Sweden": {
          "1N2":     {"1": 1.85, "N": 3.50, "2": 4.20},
          "Totaux":  {"Over 2.5": 1.90, "Under 2.5": 1.95},
          "BTTS":    {"Oui": 2.05, "Non": 1.75}
      },
      ...
  }

Note : the-odds-api renvoie surtout le 1N2 (h2h) et les totaux en gratuit.
Le BTTS n'est pas toujours dispo — on prend ce qu'on a.
"""

import os
import json
import requests

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ODDS_FILE = os.path.join(PROJECT_ROOT, "data/odds.json")

ODDS_API_BASE = "https://api.the-odds-api.com/v4"
# Sport key pour la CDM : 'soccer_fifa_world_cup'. En dehors, adapter.
DEFAULT_SPORT_KEY = "soccer_fifa_world_cup"


# ─────────────────────────────────────────────────────────────────────────────
# Source 1 : fichier manuel
# ─────────────────────────────────────────────────────────────────────────────
def load_odds_from_file():
    """Charge data/odds.json. Ignore les clés méta (préfixe '_'). {} si absent."""
    if not os.path.exists(ODDS_FILE):
        return {}
    with open(ODDS_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if not k.startswith("_")}


# ─────────────────────────────────────────────────────────────────────────────
# Source 2 : the-odds-api (optionnelle)
# ─────────────────────────────────────────────────────────────────────────────
def load_odds_from_api(sport_key=DEFAULT_SPORT_KEY, regions="eu", api_key=None):
    """
    Récupère les cotes via the-odds-api.com. Nécessite ODDS_API_KEY.
    Renvoie le schéma normalisé, ou {} en cas d'échec.
    """
    api_key = api_key or os.environ.get("ODDS_API_KEY")
    if not api_key:
        print("   ℹ️  Pas de ODDS_API_KEY dans l'environnement — API ignorée.")
        return {}

    url = f"{ODDS_API_BASE}/sports/{sport_key}/odds"
    params = {
        "apiKey": api_key,
        "regions": regions,
        "markets": "h2h,totals",
        "oddsFormat": "decimal",
    }
    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"   ⚠️  Échec API the-odds-api : {e}")
        return {}

    remaining = resp.headers.get("x-requests-remaining", "?")
    print(f"   ✅ {len(data)} matchs récupérés via API (crédits restants : {remaining})")
    return _normalize_odds_api(data)


def _normalize_odds_api(data):
    """Convertit la réponse the-odds-api vers le schéma normalisé."""
    out = {}
    for game in data:
        home = game.get("home_team")
        away = game.get("away_team")
        if not home or not away:
            continue
        key = f"{home} vs {away}"

        # On agrège en prenant la MEILLEURE cote dispo par sélection (best price)
        best = {"1N2": {}, "Totaux": {}}
        for bm in game.get("bookmakers", []):
            for market in bm.get("markets", []):
                if market["key"] == "h2h":
                    for oc in market["outcomes"]:
                        name = oc["name"]
                        price = oc["price"]
                        if name == home:   sel = "1"
                        elif name == away: sel = "2"
                        else:              sel = "N"  # Draw
                        best["1N2"][sel] = max(best["1N2"].get(sel, 0), price)
                elif market["key"] == "totals":
                    for oc in market["outcomes"]:
                        point = oc.get("point")
                        name = oc["name"]  # 'Over' / 'Under'
                        price = oc["price"]
                        sel = f"{name} {point}"
                        best["Totaux"][sel] = max(best["Totaux"].get(sel, 0), price)

        clean = {k: v for k, v in best.items() if v}
        if clean:
            out[key] = clean
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Point d'entrée unifié
# ─────────────────────────────────────────────────────────────────────────────
def load_odds(prefer_api=False, sport_key=DEFAULT_SPORT_KEY):
    """
    Charge les cotes. Fusionne fichier + API (l'API complète/écrase le fichier
    si prefer_api=True, sinon le fichier a priorité).
    """
    file_odds = load_odds_from_file()
    api_odds = load_odds_from_api(sport_key) if prefer_api else {}

    if prefer_api and api_odds:
        merged = dict(file_odds)
        merged.update(api_odds)   # API prioritaire
        return merged
    # Fichier prioritaire, API en complément
    merged = dict(api_odds)
    merged.update(file_odds)
    return merged


if __name__ == "__main__":
    print("Cotes chargées :")
    odds = load_odds()
    for match, markets in odds.items():
        print(f"\n{match}")
        for mkt, sels in markets.items():
            print(f"   {mkt}: {sels}")
    if not odds:
        print("   (aucune — crée data/odds.json ou configure ODDS_API_KEY)")
