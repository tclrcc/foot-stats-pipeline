import requests
import pandas as pd
import os
import json
from dotenv import load_dotenv

# Charger la clé API depuis le .env
load_dotenv()

API_KEY = os.getenv("API_FOOTBALL_KEY")
HEADERS = {"x-apisports-key": API_KEY}
BASE_URL = "https://v3.football.api-sports.io"

def check_api_errors(data):
    """Intercepte et explique les erreurs de l'API de manière claire."""
    if data.get('errors'):
        print("\n❌ L'API a refusé la requête :", data['errors'])
        if "token" in str(data['errors']):
            print("💡 Conseil : Ta clé API est invalide ou mal copiée.")
        elif "requests" in str(data['errors']):
            print("💡 Conseil : Limite de requêtes gratuites (100/jour) atteinte.")
        return True
    return False

# ---------------------------------------------------------
# 1. RÉCUPÉRATION DU MATCH (Pour obtenir le Fixture ID)
# ---------------------------------------------------------
def get_fixture_id(team_A, team_B, date):
    """Recherche l'ID officiel du match à une date donnée pour interroger les compositions."""
    print(f"📡 Recherche de l'ID du match {team_A} vs {team_B}...")
    querystring = {"date": date, "league": "1", "season": "2026"}
    
    response = requests.get(f"{BASE_URL}/fixtures", headers=HEADERS, params=querystring)
    if response.status_code != 200: return None
    
    data = response.json()
    if check_api_errors(data) or not data.get('response'): return None
    
    for match in data['response']:
        h_team = match['teams']['home']['name']
        a_team = match['teams']['away']['name']
        if (team_A in h_team or team_B in h_team) and (team_A in a_team or team_B in a_team):
            fixture_id = match['fixture']['id']
            print(f"✅ Match trouvé ! Fixture ID : {fixture_id}")
            return fixture_id
    
    print("⚠️ Match introuvable à cette date dans l'API.")
    return None

# ---------------------------------------------------------
# 2. COMPOSITIONS ET SÉLECTIONNEURS (Dispo 1h avant le match)
# ---------------------------------------------------------
def get_match_lineups(fixture_id):
    """Récupère le 11 de départ, la formation tactique et les entraîneurs en 1 seule requête."""
    print(f"📡 Récupération des compositions officielles (Fixture {fixture_id})...")
    querystring = {"fixture": fixture_id}
    
    response = requests.get(f"{BASE_URL}/fixtures/lineups", headers=HEADERS, params=querystring)
    if response.status_code != 200: return None
    
    data = response.json()
    if check_api_errors(data) or not data.get('response'):
        print("⚠️ Compositions non disponibles (Généralement publiées 1h avant le match).")
        return None
        
    lineups_data = {}
    for team_data in data['response']:
        team_name = team_data['team']['name']
        coach_name = team_data['coach']['name']
        formation = team_data['formation']
        
        # Extraction des 11 titulaires
        starters = [player['player']['name'] for player in team_data['startXI']]
        
        lineups_data[team_name] = {
            "coach": coach_name,
            "formation": formation,
            "starters": starters
        }
        
        print(f"✅ {team_name} | Coach: {coach_name} | Dispo: {formation}")
        
    return lineups_data

# ---------------------------------------------------------
# 3. STATISTIQUES INDIVIDUELLES (Buts, Passes, Notes)
# ---------------------------------------------------------
def get_team_top_players(team_id, season="2026"):
    """Récupère les statistiques détaillées des joueurs de l'équipe (1 appel API = toute l'équipe)."""
    print(f"📡 Récupération des statistiques des joueurs (Team ID: {team_id})...")
    # Pour ne pas exploser le quota, on récupère uniquement la Page 1 (les 20 meilleurs joueurs)
    querystring = {"team": team_id, "season": season, "page": "1"}
    
    response = requests.get(f"{BASE_URL}/players", headers=HEADERS, params=querystring)
    if response.status_code != 200: return None
    
    data = response.json()
    if check_api_errors(data) or not data.get('response'): return None
    
    players_stats = []
    for item in data['response']:
        p_name = item['player']['name']
        # On prend les stats de la première compétition listée (souvent la CDM ou qualifs)
        stats = item['statistics'][0] 
        
        rating = stats['games'].get('rating', 'N/A')
        goals = stats['goals'].get('total', 0)
        assists = stats['goals'].get('assists', 0)
        
        players_stats.append({
            "name": p_name,
            "rating": rating if rating is not None else "0.0",
            "goals": goals if goals is not None else 0,
            "assists": assists if assists is not None else 0
        })
        
    # Tri des joueurs par nombre de buts
    players_stats.sort(key=lambda x: x['goals'], reverse=True)
    print(f"✅ {len(players_stats)} joueurs analysés.")
    
    return players_stats

# ---------------------------------------------------------
# ZONE DE TEST (Simulation avant match)
# ---------------------------------------------------------
if __name__ == "__main__":
    # Test avec des données fictives/réelles pour valider la communication API
    print("--- DÉMARRAGE DU TEST API-FOOTBALL V2 ---")
    
    # 1. Trouver l'ID d'un match de la journée
    # Remplacer par des équipes qui jouent aujourd'hui (ex: "Scotland", "Brazil")
    match_date = "2026-06-24"
    f_id = get_fixture_id("Scotland", "Brazil", match_date)
    
    if f_id:
        # 2. Tenter de récupérer les compos et le coach
        lineups = get_match_lineups(f_id)
        
        # 3. Récupération des statistiques d'effectif
        # L'ID du Brésil dans API-Football est le 6, l'Écosse est le 49.
        # (L'ID de l'équipe peut être récupéré via l'endpoint /teams)
        brazil_id = 6 
        print("\n⭐ Top 3 Joueurs - Brésil :")
        brazil_players = get_team_top_players(brazil_id, season="2026")
        
        if brazil_players:
            for p in brazil_players[:3]:
                print(f"   👤 {p['name']} | Note: {p['rating']} | ⚽ {p['goals']} Buts | 👟 {p['assists']} Passes")
