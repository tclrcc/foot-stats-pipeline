"""
Force de composition (Niveau 7).

Convertit le XI de départ réel + notes joueurs en multiplicateurs sur les xG.

Principe clé — on mesure l'ÉCART à la normale, pas la qualité absolue :
    La force d'équipe est déjà encodée dans α/β (Dixon-Coles). Ici on capte
    seulement si le XI aligné ce soir est plus fort/faible que ce que
    l'équipe aligne d'habitude (rotations, forfaits, jeunes lancés...).

    ref_off / ref_def = niveau de référence de l'équipe (ses meilleurs joueurs)
    xi_off  / xi_def  = niveau du XI effectivement aligné

    att_mult = 1 + clip((xi_off/ref_off − 1) × SENS, −CAP, +CAP)   (>1 = attaque renforcée)
    def_mult = 1 − clip((xi_def/ref_def − 1) × SENS, −CAP, +CAP)   (<1 = défense renforcée)

Application sur les lambdas (dans predict_upcoming) :
    λ_home ×= att_mult_home × def_mult_away
    μ_away ×= att_mult_away × def_mult_home

Formation : ajustement tactique léger et borné, dérivé du dispositif observé
(≥5 défenseurs = intention défensive, etc.). Secondaire aux notes.
"""

# ─────────────────────────────────────────────────────────────────────────────
# HYPERPARAMÈTRES
# ─────────────────────────────────────────────────────────────────────────────
MAX_ADJUST   = 0.25   # cap ±25% (choix utilisateur : modéré)
SENSITIVITY  = 2.0    # pente écart-de-note → multiplicateur
MIN_COVERAGE = 0.60   # part minimale du XI devant avoir une note, sinon on skip

# Postes offensifs / défensifs (API-Football : G, D, M, F)
OFF_POS = {"M", "F"}   # milieux + attaquants
DEF_POS = {"G", "D"}   # gardien + défenseurs

# Formation : bornes de l'effet tactique
FORMATION_MAX = 0.06   # ±6% max, volontairement petit


def _clip(x, lo, hi):
    return max(lo, min(hi, x))


# ─────────────────────────────────────────────────────────────────────────────
# Indices d'un groupe de joueurs
# ─────────────────────────────────────────────────────────────────────────────
def team_line_ratings(players):
    """
    players : liste de dicts {pos: 'G'/'D'/'M'/'F', rating: float|None}
    Renvoie (off_rating, def_rating, coverage) — moyennes des notes par ligne.
    coverage = part des joueurs ayant une note exploitable.
    """
    off_vals, def_vals = [], []
    n_total = len(players)
    n_rated = 0

    for p in players:
        r = p.get("rating")
        try:
            r = float(r)
        except (TypeError, ValueError):
            r = None
        if r is None or r <= 0:
            continue
        n_rated += 1
        if p.get("pos") in OFF_POS:
            off_vals.append(r)
        elif p.get("pos") in DEF_POS:
            def_vals.append(r)

    coverage = (n_rated / n_total) if n_total else 0.0
    off_rating = sum(off_vals) / len(off_vals) if off_vals else None
    def_rating = sum(def_vals) / len(def_vals) if def_vals else None
    return off_rating, def_rating, coverage


# ─────────────────────────────────────────────────────────────────────────────
# Multiplicateurs attaque / défense d'une équipe
# ─────────────────────────────────────────────────────────────────────────────
def team_multipliers(xi_players, ref_off, ref_def):
    """
    Renvoie (att_mult, def_mult, note) pour une équipe.
    Si la couverture des notes est insuffisante → (1.0, 1.0, warning).
    """
    xi_off, xi_def, coverage = team_line_ratings(xi_players)

    if coverage < MIN_COVERAGE:
        return 1.0, 1.0, f"couverture notes insuffisante ({coverage*100:.0f}%) — compo ignorée"

    att_mult, def_mult = 1.0, 1.0
    details = []

    if xi_off and ref_off:
        rel = xi_off / ref_off - 1.0
        adj = _clip(rel * SENSITIVITY, -MAX_ADJUST, MAX_ADJUST)
        att_mult = 1.0 + adj
        if abs(adj) >= 0.02:
            details.append(f"attaque ×{att_mult:.2f} (XI off {xi_off:.2f} vs réf {ref_off:.2f})")

    if xi_def and ref_def:
        rel = xi_def / ref_def - 1.0
        adj = _clip(rel * SENSITIVITY, -MAX_ADJUST, MAX_ADJUST)
        def_mult = 1.0 - adj   # défense forte → réduit les buts adverses
        if abs(adj) >= 0.02:
            details.append(f"défense ×{def_mult:.2f} (XI def {xi_def:.2f} vs réf {ref_def:.2f})")

    note = "; ".join(details) if details else "XI conforme à la normale"
    return att_mult, def_mult, note


# ─────────────────────────────────────────────────────────────────────────────
# Ajustement de formation (léger)
# ─────────────────────────────────────────────────────────────────────────────
def formation_adjustment(formation):
    """
    Renvoie (own_att_mult, opp_att_mult, note) à partir d'une chaîne '4-3-3'.
    Dispositif défensif → l'équipe attaque moins ET concède moins.
    """
    if not formation or "-" not in formation:
        return 1.0, 1.0, None
    try:
        parts = [int(x) for x in formation.split("-")]
    except ValueError:
        return 1.0, 1.0, None

    defenders = parts[0]
    forwards  = parts[-1]

    own, opp, label = 1.0, 1.0, None
    if defenders >= 5:
        own = 1.0 - FORMATION_MAX          # attaque bridée
        opp = 1.0 - FORMATION_MAX * 0.7    # bloc bas → adversaire concède moins de situations
        label = f"{formation} défensif"
    elif forwards >= 3 and defenders <= 3:
        own = 1.0 + FORMATION_MAX          # intention offensive
        opp = 1.0 + FORMATION_MAX * 0.5    # plus ouvert derrière
        label = f"{formation} offensif"

    return own, opp, label


# ─────────────────────────────────────────────────────────────────────────────
# Combinaison pour un match
# ─────────────────────────────────────────────────────────────────────────────
def match_lineup_adjustment(home_data, away_data):
    """
    home_data / away_data : dict {
        formation: '4-3-3',
        xi: [{pos, rating}, ...],
        ref_off: float, ref_def: float
    }
    Renvoie {lam_mult, mu_mult, notes[]} à appliquer sur λ_home, μ_away.
    """
    notes = []

    # Notes joueurs (ref_off/ref_def optionnels : sans eux, seule la formation joue)
    h_att, h_def, h_note = team_multipliers(home_data.get("xi", []), home_data.get("ref_off"), home_data.get("ref_def"))
    a_att, a_def, a_note = team_multipliers(away_data.get("xi", []), away_data.get("ref_off"), away_data.get("ref_def"))

    # Formation
    h_fown, h_fopp, h_flabel = formation_adjustment(home_data.get("formation"))
    a_fown, a_fopp, a_flabel = formation_adjustment(away_data.get("formation"))

    # λ_home dépend de : attaque H (+ formation H) et défense A (+ formation A côté opp)
    lam_mult = h_att * a_def * h_fown * a_fopp
    # μ_away dépend de : attaque A (+ formation A) et défense H (+ formation H côté opp)
    mu_mult  = a_att * h_def * a_fown * h_fopp

    if h_note and "conforme" not in h_note:
        notes.append(f"{home_data.get('team','Domicile')} : {h_note}")
    if a_note and "conforme" not in a_note:
        notes.append(f"{away_data.get('team','Extérieur')} : {a_note}")
    if h_flabel:
        notes.append(f"{home_data.get('team','Domicile')} : {h_flabel}")
    if a_flabel:
        notes.append(f"{away_data.get('team','Extérieur')} : {a_flabel}")

    return {"lam_mult": lam_mult, "mu_mult": mu_mult, "notes": notes}


# ─────────────────────────────────────────────────────────────────────────────
# Adaptateur API-Football (exécuté sur le VPS — non testable ici)
# ─────────────────────────────────────────────────────────────────────────────
def build_team_data_from_api(lineup_entry, players_stats, team_name):
    """
    Construit le dict team_data à partir des réponses API-Football.

    lineup_entry : {'coach':..., 'formation':'4-3-3', 'starters':[noms...]}
                   + on a besoin des positions → voir note ci-dessous.
    players_stats: liste [{name, rating, goals, assists}, ...] (endpoint /players)

    NOTE : l'endpoint /fixtures/lineups fournit startXI avec player.pos (G/D/M/F).
    Il faut donc enrichir get_match_lineups pour conserver la position de chaque
    titulaire (voir patch de l'extracteur). On joint ensuite par nom aux notes.
    """
    # Index note par nom
    rating_by_name = {}
    for p in players_stats or []:
        try:
            rating_by_name[p["name"]] = float(p.get("rating") or 0) or None
        except (TypeError, ValueError):
            rating_by_name[p["name"]] = None

    # XI avec position + note
    xi = []
    for starter in lineup_entry.get("starters_detailed", []):
        # starter attendu : {'name':..., 'pos':'G'/'D'/'M'/'F'}
        xi.append({
            "pos": starter.get("pos"),
            "rating": rating_by_name.get(starter.get("name")),
        })

    # Référence = moyenne des meilleures notes de l'effectif par ligne.
    # On approxime les postes via l'ordre des joueurs (les stats /players ne
    # donnent pas toujours la position ; on prend une réf globale prudente).
    all_ratings = [r for r in rating_by_name.values() if r]
    ref_global = sum(all_ratings) / len(all_ratings) if all_ratings else 6.8
    # Réfs off/def = même base globale (faute de positions dans /players).
    # Conservateur : l'écart XI/réf reste piloté par les titulaires réels.
    return {
        "team": team_name,
        "formation": lineup_entry.get("formation"),
        "xi": xi,
        "ref_off": ref_global,
        "ref_def": ref_global,
    }


if __name__ == "__main__":
    # Démo avec des compos fictives
    print("=== DÉMO force de composition ===\n")

    # Belgique full strength vs Belgique remaniée
    belgium_full = {
        "team": "Belgium", "formation": "4-3-3",
        "ref_off": 7.10, "ref_def": 6.95,
        "xi": [
            {"pos": "G", "rating": 7.0}, {"pos": "D", "rating": 7.1}, {"pos": "D", "rating": 6.9},
            {"pos": "D", "rating": 7.0}, {"pos": "D", "rating": 6.8}, {"pos": "M", "rating": 7.3},
            {"pos": "M", "rating": 7.1}, {"pos": "M", "rating": 7.0}, {"pos": "F", "rating": 7.4},
            {"pos": "F", "rating": 7.2}, {"pos": "F", "rating": 7.0},
        ],
    }
    senegal_rotated = {
        "team": "Senegal", "formation": "5-3-2",
        "ref_off": 7.00, "ref_def": 6.90,
        "xi": [
            {"pos": "G", "rating": 6.8}, {"pos": "D", "rating": 6.7}, {"pos": "D", "rating": 6.6},
            {"pos": "D", "rating": 6.9}, {"pos": "D", "rating": 6.5}, {"pos": "D", "rating": 6.6},
            {"pos": "M", "rating": 6.7}, {"pos": "M", "rating": 6.5}, {"pos": "M", "rating": 6.4},
            {"pos": "F", "rating": 6.3}, {"pos": "F", "rating": 6.5},
        ],
    }

    res = match_lineup_adjustment(belgium_full, senegal_rotated)
    print(f"λ_Belgium × {res['lam_mult']:.3f}")
    print(f"μ_Senegal × {res['mu_mult']:.3f}")
    for n in res["notes"]:
        print(f"  • {n}")
