"""
Dossier de match — agrège toutes les informations qu'un journaliste utilise
pour préparer un avant-match : forme, face-à-face, forces, hommes clés,
absents, prédiction et angles narratifs générés automatiquement.

Purement construit sur les données existantes (historical_matches, ELO,
Dixon-Coles, dépendances joueurs, contexte CDM). Aucune dépendance externe.
"""

import os
import sqlite3
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models"))

import service
import dixon_coles as dc
from context_cdm2026 import is_knockout, HOST_NATIONS

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(PROJECT_ROOT, "data/db/foot_stats.db")


def _connect():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def load_coaches():
    """Charge data/coaches.json → dict {équipe: infos}. {} si absent."""
    import json
    fpath = os.path.join(PROJECT_ROOT, "data/coaches.json")
    if not os.path.exists(fpath):
        return {}
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return raw.get("coaches", {})
    except Exception:
        return {}


def load_lineups():
    """Charge data/lineups.json → dict {clé_match: {home, away}}. {} si absent."""
    import json
    fpath = os.path.join(PROJECT_ROOT, "data/lineups.json")
    if not os.path.exists(fpath):
        return {}
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return {k: v for k, v in raw.items() if not k.startswith("_")}
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# FORME RÉCENTE
# ─────────────────────────────────────────────────────────────────────────────
def team_form(team, n=6):
    conn = _connect()
    rows = conn.execute("""
        SELECT date, home_team, away_team, home_score, away_score, tournament
        FROM historical_matches
        WHERE (home_team=? OR away_team=?) AND home_score IS NOT NULL
        ORDER BY date DESC LIMIT ?
    """, (team, team, n)).fetchall()
    conn.close()

    matches = []
    w = d = l = gf = ga = 0
    for date, h, a, hs, as_, tour in rows:
        at_home = (h == team)
        f = int(hs if at_home else as_)
        ag = int(as_ if at_home else hs)
        opp = a if at_home else h
        res = "V" if f > ag else ("N" if f == ag else "D")
        w += res == "V"; d += res == "N"; l += res == "D"
        gf += f; ga += ag
        matches.append({
            "date": date[:10], "opponent": opp, "score": f"{f}-{ag}",
            "result": res, "competition": tour, "venue": "dom" if at_home else "ext",
        })

    # Séries (à partir du plus récent)
    unbeaten = 0
    for m in matches:
        if m["result"] in ("V", "N"): unbeaten += 1
        else: break
    winless = 0
    for m in matches:
        if m["result"] in ("D", "N"): winless += 1
        else: break
    scoring = 0
    for m in matches:
        if int(m["score"].split("-")[0]) > 0: scoring += 1
        else: break
    clean_sheets = sum(1 for m in matches if int(m["score"].split("-")[1]) == 0)

    return {
        "matches": matches,
        "summary": {"w": w, "d": d, "l": l, "gf": gf, "ga": ga},
        "streaks": {
            "unbeaten": unbeaten, "winless": winless,
            "scoring": scoring, "clean_sheets": clean_sheets,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# FACE-À-FACE
# ─────────────────────────────────────────────────────────────────────────────
def head_to_head(home, away, recent_n=5):
    conn = _connect()
    rows = conn.execute("""
        SELECT date, home_team, away_team, home_score, away_score, tournament
        FROM historical_matches
        WHERE ((home_team=? AND away_team=?) OR (home_team=? AND away_team=?))
          AND home_score IS NOT NULL
        ORDER BY date DESC
    """, (home, away, away, home)).fetchall()
    conn.close()

    home_wins = away_wins = draws = home_goals = away_goals = 0
    recent = []
    for i, (date, h, a, hs, as_, tour) in enumerate(rows):
        hs, as_ = int(hs), int(as_)
        # Buts ramenés au point de vue de `home`
        hg = hs if h == home else as_
        ag = as_ if h == home else hs
        home_goals += hg; away_goals += ag
        if hg > ag: home_wins += 1
        elif hg < ag: away_wins += 1
        else: draws += 1
        if i < recent_n:
            recent.append({
                "date": date[:10], "home": h, "away": a,
                "score": f"{hs}-{as_}", "competition": tour,
            })

    return {
        "played": len(rows),
        "home_wins": home_wins, "draws": draws, "away_wins": away_wins,
        "home_goals": home_goals, "away_goals": away_goals,
        "recent": recent,
        "last_meeting": recent[0] if recent else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ANGLES NARRATIFS (générés automatiquement)
# ─────────────────────────────────────────────────────────────────────────────
def _year(date_str):
    return date_str[:4]


def generate_storylines(home, away, pred, strength, form_h, form_a, h2h,
                        players_h, players_a, is_ko):
    s = []

    # Enjeu / contexte
    if is_ko:
        s.append("Match à élimination directe : historiquement plus fermé et plus tendu, le moindre détail compte.")

    # Écart de niveau
    gap = strength.get("elo_gap", 0)
    if gap is not None:
        if gap >= 150:
            fav = strength["favorite"]
            s.append(f"Gros déséquilibre sur le papier : {fav} domine largement au classement ELO (écart de {int(gap)} points).")
        elif gap <= 40:
            s.append("Duel très équilibré selon les notes de force : difficile de désigner un favori net.")

    # Prédiction du modèle
    m = pred["markets"]
    top = max(("home", m["home_win"]), ("draw", m["draw"]), ("away", m["away_win"]), key=lambda x: x[1])
    label = {"home": home, "draw": "le nul", "away": away}[top[0]]
    s.append(f"Le modèle penche pour {label} ({top[1]:.0f}%). Score le plus probable : {pred['top_scorelines'][0]['score']}.")
    total_xg = pred["xg_home"] + pred["xg_away"]
    if total_xg >= 2.8:
        s.append(f"Rencontre attendue ouverte : {total_xg:.1f} buts espérés au total.")
    elif total_xg <= 1.9:
        s.append(f"Match attendu fermé : seulement {total_xg:.1f} buts espérés au total.")

    # Face-à-face
    if h2h["played"] == 0:
        s.append(f"Première confrontation de l'histoire entre {home} et {away}.")
    else:
        if h2h["last_meeting"]:
            lm = h2h["last_meeting"]
            s.append(f"Dernière confrontation : {lm['home']} {lm['score']} {lm['away']} ({_year(lm['date'])}, {lm['competition']}).")
        dom_home = h2h["home_wins"]; dom_away = h2h["away_wins"]
        if h2h["played"] >= 4:
            if dom_home >= dom_away * 2 and dom_home >= 3:
                s.append(f"Ascendant psychologique pour {home} : {dom_home} victoires contre {dom_away} en {h2h['played']} confrontations.")
            elif dom_away >= dom_home * 2 and dom_away >= 3:
                s.append(f"Ascendant psychologique pour {away} : {dom_away} victoires contre {dom_home} en {h2h['played']} confrontations.")

    # Formes
    for team, f in ((home, form_h), (away, form_a)):
        st = f["streaks"]
        if st["unbeaten"] >= 4:
            s.append(f"{team} reste sur {st['unbeaten']} matchs sans défaite.")
        elif st["winless"] >= 3:
            s.append(f"{team} traverse une période délicate : {st['winless']} matchs sans victoire.")
        if st["scoring"] >= 5:
            s.append(f"{team} a marqué lors de chacun de ses {st['scoring']} derniers matchs.")

    # Hommes clés
    for team, ps in ((home, players_h), (away, players_a)):
        if ps:
            top_p = ps[0]
            if top_p["dependency_pct"] >= 30:
                s.append(f"{team} s'appuie fortement sur {top_p['name']} ({top_p['dependency_pct']:.0f}% des buts de l'équipe) — un joueur à surveiller de près.")

    return s


# ─────────────────────────────────────────────────────────────────────────────
# STADE / ENJEU
# ─────────────────────────────────────────────────────────────────────────────
def _match_meta(home, away, date):
    is_ko = is_knockout(date) if date else False
    stage = "Élimination directe" if is_ko else "Phase de groupes"
    host = None
    if home in HOST_NATIONS:
        host = home
    elif away in HOST_NATIONS:
        host = away
    return {"stage": stage, "is_knockout": is_ko, "host_playing": host}


# ─────────────────────────────────────────────────────────────────────────────
# PHYSIONOMIE & LECTURE TACTIQUE
# ─────────────────────────────────────────────────────────────────────────────
def match_dynamics(home, away, neutral, strength, is_ko, lam_mult=1.0, mu_mult=1.0):
    """
    Dérive la physionomie probable du match depuis la distribution des scores,
    et une lecture tactique depuis les profils offensifs/défensifs.
    """
    tp, glob = service.get_model_params()
    gamma, rho = glob.get("gamma", 1.3), glob.get("rho", -0.1)
    lam, mu = dc.predict_lambdas(home, away, neutral, tp, gamma)
    if lam is None:
        return None
    lam *= lam_mult
    mu  *= mu_mult

    mat = dc.score_matrix(lam, mu, rho, max_goals=10)
    n = mat.shape[0]
    idx = np.arange(n)
    diff = idx[:, None] - idx[None, :]          # buts_home - buts_away
    total = idx[:, None] + idx[None, :]

    p_draw   = float(np.diag(mat).sum())
    p_margin1 = float(mat[np.abs(diff) == 1].sum())
    p_tight  = p_draw + p_margin1
    p_home_2 = float(mat[diff >= 2].sum())
    p_away_2 = float(mat[diff <= -2].sum())
    p_blowout = p_home_2 + p_away_2
    p_home_cs = float(mat[:, 0].sum())          # extérieur ne marque pas
    p_away_cs = float(mat[0, :].sum())          # domicile ne marque pas
    p_under_15 = float(mat[total <= 1].sum())
    p_over_35  = float(mat[total >= 4].sum())

    total_xg = lam + mu
    balance = lam - mu

    # Profil de match
    if total_xg <= 2.0:
        openness = "verrouillé"
    elif total_xg >= 3.0:
        openness = "ouvert"
    else:
        openness = "modéré"

    if abs(balance) >= 0.9:
        tilt = "déséquilibré"
    elif abs(balance) <= 0.35:
        tilt = "équilibré"
    else:
        tilt = "légèrement déséquilibré"

    profile = {
        ("verrouillé", "équilibré"): "Combat défensif serré",
        ("verrouillé", "légèrement déséquilibré"): "Match fermé, léger favori",
        ("verrouillé", "déséquilibré"): "Domination sans spectacle",
        ("modéré", "équilibré"): "Duel équilibré",
        ("modéré", "légèrement déséquilibré"): "Match disputé, un favori se dégage",
        ("modéré", "déséquilibré"): "Favori net, adversaire accrocheur",
        ("ouvert", "équilibré"): "Match ouvert et indécis",
        ("ouvert", "légèrement déséquilibré"): "Rencontre animée, un favori",
        ("ouvert", "déséquilibré"): "Démonstration offensive annoncée",
    }.get((openness, tilt), "Duel équilibré")

    # Indice de tempo (ouverture) 0-100 : mappe total_xg de 1.4 → 3.6
    tempo = int(max(0, min(100, (total_xg - 1.4) / (3.6 - 1.4) * 100)))

    # Prolongation (8es) : proxy = P(nul à 90')
    extra_time = p_draw if is_ko else None

    # ── Lecture tactique depuis α/β ──
    sh, sa = strength["home"], strength["away"]
    reads = []
    fav = strength.get("favorite")

    # Meilleure défense en jeu ?
    def_best = None
    if sh["defense"] is not None and sa["defense"] is not None:
        if min(sh["defense"], sa["defense"]) <= 0.30:
            def_best = home if sh["defense"] <= sa["defense"] else away
            other = away if def_best == home else home
            reads.append(
                f"{def_best} présente l'une des défenses les plus hermétiques du tournoi. "
                f"La clé du match : {other} parviendra-t-il à la faire céder ?"
            )

    # Attaque forte contre défense faible ?
    if sh["attack"] and sa["defense"] and sh["attack"] >= 3.3 and sa["defense"] >= 0.45:
        reads.append(f"L'attaque de {home} devrait trouver des espaces face à une défense adverse plus perméable.")
    if sa["attack"] and sh["defense"] and sa["attack"] >= 3.3 and sh["defense"] >= 0.45:
        reads.append(f"L'attaque de {away} a les armes pour exploiter les failles défensives de {home}.")

    # Physionomie synthétique
    if openness == "verrouillé":
        reads.append("Peu de buts attendus : le match devrait se jouer sur des détails, un coup de génie ou un coup de pied arrêté.")
    elif openness == "ouvert":
        reads.append("Les deux équipes ayant de quoi marquer, la rencontre s'annonce rythmée et à plusieurs buts.")

    if is_ko and p_draw >= 0.30:
        reads.append(f"Match à élimination directe très indécis : {p_draw*100:.0f}% de probabilité de nul à l'issue des 90 minutes — la prolongation est une hypothèse sérieuse.")

    return {
        "profile": profile,
        "openness": openness,
        "tempo": tempo,
        "total_xg": round(total_xg, 2),
        "scenarios": {
            "tight": round(p_tight * 100, 1),
            "blowout": round(p_blowout * 100, 1),
            "clean_sheet_home": round(p_home_cs * 100, 1),
            "clean_sheet_away": round(p_away_cs * 100, 1),
            "under_1_5": round(p_under_15 * 100, 1),
            "over_3_5": round(p_over_35 * 100, 1),
            "extra_time": round(extra_time * 100, 1) if extra_time is not None else None,
        },
        "tactical_read": reads,
    }


# ─────────────────────────────────────────────────────────────────────────────
# DOSSIER COMPLET
# ─────────────────────────────────────────────────────────────────────────────
def match_dossier(home, away, neutral=True, match_date=None):
    # ── Compositions (data/lineups.json) : applique l'effet aux xG ──
    lineup_effect = _compute_lineup_effect(home, away)
    lineup_active = lineup_effect["display"] is not None

    # ── Absents (data/absences.json) : impact offensif N4 si pas de compo ──
    absence_effect = _compute_absence_effect(home, away, lineup_active)

    lam_mult = lineup_effect["lam_mult"] * absence_effect["lam_mult"]
    mu_mult = lineup_effect["mu_mult"] * absence_effect["mu_mult"]

    pred = service.predict(home, away, neutral, lam_mult=lam_mult, mu_mult=mu_mult)
    if pred is None:
        return None
    # Méthode explicite selon les sources d'ajustement réellement actives
    tags = []
    if lineup_active:
        tags.append("compo")
    if absence_effect["display"] is not None and not lineup_active and \
       (abs(absence_effect["lam_mult"] - 1) > 0.005 or abs(absence_effect["mu_mult"] - 1) > 0.005):
        tags.append("absences")
    pred["method"] = "dixon_coles" + ("+" + "+".join(tags) if tags else "")

    th = service.get_team(home) or {}
    ta = service.get_team(away) or {}

    elo_h = th.get("elo"); elo_a = ta.get("elo")
    elo_gap = abs(elo_h - elo_a) if (elo_h and elo_a) else None
    favorite = None
    if elo_h and elo_a:
        favorite = home if elo_h >= elo_a else away

    strength = {
        "home": {"elo": elo_h, "elo_rank": th.get("elo_rank"),
                 "attack": th.get("attack"), "defense": th.get("defense")},
        "away": {"elo": elo_a, "elo_rank": ta.get("elo_rank"),
                 "attack": ta.get("attack"), "defense": ta.get("defense")},
        "elo_gap": round(elo_gap, 1) if elo_gap else None,
        "favorite": favorite,
    }

    form_h = team_form(home)
    form_a = team_form(away)
    h2h = head_to_head(home, away)
    players_h = th.get("key_players", [])
    players_a = ta.get("key_players", [])
    meta = _match_meta(home, away, match_date)
    dynamics = match_dynamics(home, away, neutral, strength, meta["is_knockout"],
                              lam_mult=lam_mult, mu_mult=mu_mult)

    # Sélectionneurs (contexte éditorial)
    coaches_map = load_coaches()
    coaches = {"home": coaches_map.get(home), "away": coaches_map.get(away)}

    storylines = generate_storylines(
        home, away, pred, strength, form_h, form_a, h2h,
        players_h, players_a, meta["is_knockout"],
    )
    storylines += _coach_storylines(home, away, coaches)
    storylines += absence_effect["storylines"]
    # Choc de styles + effet compo/absences dans la lecture tactique
    if dynamics is not None:
        clash = _style_clash(home, away, coaches)
        if clash:
            dynamics["tactical_read"].insert(0, clash)
        for n in lineup_effect["notes"]:
            dynamics["tactical_read"].append(n)
        for n in absence_effect["notes"]:
            dynamics["tactical_read"].append(n)

    return {
        "fixture": {
            "home_team": home, "away_team": away,
            "neutral": neutral, "date": match_date,
            "stage": meta["stage"], "is_knockout": meta["is_knockout"],
            "host_playing": meta["host_playing"],
        },
        "prediction": pred,
        "dynamics": dynamics,
        "strength": strength,
        "form": {"home": form_h, "away": form_a},
        "head_to_head": h2h,
        "key_players": {"home": players_h, "away": players_a},
        "coaches": coaches,
        "lineups": lineup_effect["display"],
        "absences": absence_effect["display"],
        "storylines": storylines,
    }


def _compute_absence_effect(home, away, lineup_active):
    """
    Charge les absents (data/absences.json, rempli à la main ou par la
    commande 'injuries') et calcule l'impact offensif via le Niveau 4.
    Si la compo officielle du match est déjà connue (lineup_active), les
    absences restent affichées mais ne modifient plus les xG — la compo
    alignée est la vérité terrain (évite le double comptage).
    """
    import sys as _sys
    _sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models"))
    import squad_impact as si
    import json as _json

    empty = {"lam_mult": 1.0, "mu_mult": 1.0, "display": None, "notes": [], "storylines": []}
    absences = si.load_absences()
    if not absences.get(home) and not absences.get(away):
        return empty

    # Détail (motifs) écrit par la commande injuries — clé _ ignorée par N4
    detail = {}
    if os.path.exists(si.ABSENCES_FILE):
        try:
            with open(si.ABSENCES_FILE, "r", encoding="utf-8") as f:
                detail = _json.load(f).get("_detail", {})
        except Exception:
            detail = {}

    depth = si.load_scorer_depth()
    adj_h = si.compute_attack_adjustment(home, absences.get(home, []), depth)
    adj_a = si.compute_attack_adjustment(away, absences.get(away, []), depth)

    def side_display(team, adj):
        reasons = {d["name"]: d.get("reason") for d in detail.get(team, [])}
        deps = {p: dep for p, dep, _, _ in adj["detail"]}
        out = []
        for p in absences.get(team, []):
            out.append({"name": p, "reason": reasons.get(p) or None,
                        "dependency_pct": round(deps[p], 1) if p in deps else None})
        return out

    display = {"home": side_display(home, adj_h), "away": side_display(away, adj_a)}

    notes, stories = [], []
    for team, adj in ((home, adj_h), (away, adj_a)):
        if adj["total_impact"] > 0.005:
            pct = adj["total_impact"] * 100
            if lineup_active:
                notes.append(f"{team} privé de {', '.join(adj['matched_absents'])} — déjà reflété dans la compo alignée.")
            else:
                notes.append(f"{team} : potentiel offensif réduit d'environ {pct:.0f}% par les forfaits ({', '.join(adj['matched_absents'])}).")
        for p, dep, _, _ in adj["detail"]:
            if dep >= 15:
                stories.append(f"Coup dur pour {team} : forfait de {p}, son buteur à {dep:.0f}% de dépendance.")

    lam_mult = 1.0 if lineup_active else adj_h["multiplier"]
    mu_mult = 1.0 if lineup_active else adj_a["multiplier"]
    return {"lam_mult": lam_mult, "mu_mult": mu_mult,
            "display": display, "notes": notes, "storylines": stories}


def _compute_lineup_effect(home, away):
    """
    Cherche la compo du match dans data/lineups.json et calcule son effet.
    Robuste : formation seule si pas de notes. Renvoie multiplicateurs +
    données d'affichage + notes.
    """
    import sys as _sys
    _sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models"))
    import lineup_strength as ls

    empty = {"lam_mult": 1.0, "mu_mult": 1.0, "notes": [], "display": None}
    lineups = load_lineups()
    entry = lineups.get(f"{home} vs {away}")
    if not entry or "home" not in entry or "away" not in entry:
        return empty

    try:
        eff = ls.match_lineup_adjustment(entry["home"], entry["away"])
    except Exception:
        return empty

    display = {
        "home": {"formation": entry["home"].get("formation"),
                 "xi": entry["home"].get("xi", [])},
        "away": {"formation": entry["away"].get("formation"),
                 "xi": entry["away"].get("xi", [])},
    }
    notes = [n for n in eff.get("notes", []) if "couverture notes" not in n]
    if abs(eff["lam_mult"] - 1) < 0.005 and abs(eff["mu_mult"] - 1) < 0.005:
        notes.append("Compositions prises en compte : dispositifs équilibrés, xG inchangés (ajoute les notes joueurs pour affiner).")
    else:
        notes.append("Prédiction ajustée selon les compositions alignées.")
    return {"lam_mult": eff["lam_mult"], "mu_mult": eff["mu_mult"],
            "notes": notes, "display": display}


def _coach_storylines(home, away, coaches):
    """Angles narratifs liés aux bancs de touche."""
    out = []
    for team, side in ((home, "home"), (away, "away")):
        c = coaches.get(side)
        if c and c.get("context"):
            out.append(f"Sur le banc de {team} : {c['name']} — {c['context']}")
    return out


def _style_clash(home, away, coaches):
    """Détecte un contraste de styles entre les deux sélectionneurs."""
    ch, ca = coaches.get("home"), coaches.get("away")
    if not ch or not ca:
        return None
    sh = " ".join(ch.get("style", [])).lower()
    sa = " ".join(ca.get("style", [])).lower()
    press_h = "pressing" in sh
    press_a = "pressing" in sa
    poss_h = "possession" in sh
    poss_a = "possession" in sa
    if press_h and poss_a:
        return f"Choc de styles : le pressing haut de {ch['name']} ({home}) face à la maîtrise du ballon de {ca['name']} ({away})."
    if press_a and poss_h:
        return f"Choc de styles : la possession de {ch['name']} ({home}) face au pressing haut de {ca['name']} ({away})."
    return None
