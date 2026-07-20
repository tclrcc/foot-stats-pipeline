"""
Tests des storylines du dossier club (synthèse narrative "À la une").
Reconstruites depuis les données déjà calculées par club_dossier, sans
source supplémentaire — et sans jamais fabriquer une dépendance par
buteur (aucune table de profondeur d'effectif club n'existe).
"""
import service


def test_standings_gap_uses_true_home_away_not_assumed_favorite():
    """
    Regression directe d'un bug trouve en testant : la phrase citait
    a tort la MEILLEURE equipe comme si elle recevait toujours, alors
    que le domicile reel peut etre l'equipe la moins bien classee.
    """
    standings = {"home": {"rank": 9, "points": 24, "played": 18, "gd": -6, "form": []},
                "away": {"rank": 1, "points": 42, "played": 18, "gd": 21, "form": []}}
    s = service._club_storylines("Qingdao Youth Island", "Chengdu Better City",
                                 None, standings, {"home": [], "away": []}, [], {})
    assert any("Qingdao Youth Island (#9)" in line and "reçoit Chengdu Better City (#1)" in line
              for line in s)


def test_close_standings_flagged_as_derby():
    standings = {"home": {"rank": 5, "points": 30, "played": 18, "gd": 2, "form": []},
                "away": {"rank": 6, "points": 29, "played": 18, "gd": 1, "form": []}}
    s = service._club_storylines("A", "B", None, standings, {"home": [], "away": []}, [], {})
    assert any("proches au classement" in line for line in s)


def test_moderate_standings_gap_no_longer_silent():
    """
    Regression : un ecart entre 3 et 7 places ne produisait AUCUNE
    storyline (zone morte entre 'gros ecart' >=8 et 'proches' <=2) —
    trouve sur le cas reel #12 vs #6 (ecart de 6).
    """
    standings = {"home": {"rank": 12, "points": 15, "played": 12, "gd": -3, "form": []},
                "away": {"rank": 6, "points": 19, "played": 12, "gd": 3, "form": []}}
    s = service._club_storylines("Kalmar FF", "Malmo FF", None, standings,
                                 {"home": [], "away": []}, [], {})
    assert any("Avantage au classement pour Malmo FF" in line for line in s)


def test_model_favorite_and_scoreline_reported():
    pred = {"markets": {"home_win": 21.3, "draw": 25.8, "away_win": 52.9},
            "top_scorelines": [{"score": "0-1"}], "xg_home": 0.98, "xg_away": 1.67}
    s = service._club_storylines("A", "B", pred, {"home": None, "away": None},
                                 {"home": [], "away": []}, [], {})
    assert any("B" in line and "53%" in line and "0-1" in line for line in s)


def test_lopsided_h2h_history_flagged():
    h2h = [{"home_team": "B", "away_team": "A", "home_score": 5, "away_score": 1, "date": "2026-04-03"},
           {"home_team": "A", "away_team": "B", "home_score": 2, "away_score": 2, "date": "2025-10-26"},
           {"home_team": "B", "away_team": "A", "home_score": 1, "away_score": 1, "date": "2025-05-17"},
           {"home_team": "A", "away_team": "B", "home_score": 1, "away_score": 1, "date": "2024-10-27"},
           {"home_team": "B", "away_team": "A", "home_score": 7, "away_score": 0, "date": "2024-05-26"}]
    balance = {"home_wins": 0, "draws": 3, "away_wins": 2}
    s = service._club_storylines("A", "B", None, {"home": None, "away": None},
                                 {"home": [], "away": []}, h2h, balance)
    assert any("Dernière confrontation" in line and "5-1" in line for line in s)
    assert any("Écart marqué" in line and "7-0" in line for line in s)


def test_form_streaks_detected_from_most_recent_first():
    """form.home/away sont ordonnes du plus recent au plus ancien (cf. recent_form())."""
    winless_form = [
        {"result": "D", "score": "0-1", "venue": "away"},
        {"result": "D", "score": "0-1", "venue": "home"},
        {"result": "N", "score": "1-1", "venue": "home"},
        {"result": "V", "score": "2-0", "venue": "away"},  # rompt la serie, ignoré
    ]
    s = service._club_storylines("A", "B", None, {"home": None, "away": None},
                                 {"home": winless_form, "away": []}, [], {})
    assert any("A traverse une période délicate : 3 matchs sans victoire" in line for line in s)


def test_no_key_players_fabricated():
    """Contrairement aux selections, aucune 'homme cle' ne doit jamais apparaitre (pas de donnee fiable)."""
    pred = {"markets": {"home_win": 40, "draw": 30, "away_win": 30},
            "top_scorelines": [{"score": "1-0"}], "xg_home": 1.2, "xg_away": 0.9}
    s = service._club_storylines("A", "B", pred, {"home": None, "away": None},
                                 {"home": [], "away": []}, [], {})
    assert not any("% des buts" in line for line in s)


def test_empty_inputs_return_empty_list_no_crash():
    assert service._club_storylines("A", "B", None, {"home": None, "away": None},
                                    {"home": [], "away": []}, [], {}) == []
