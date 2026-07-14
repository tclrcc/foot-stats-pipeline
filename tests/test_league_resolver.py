"""
Tests du résolveur de ligues (resolve_leagues, is_cup_competition,
league_display_name). C'est exactement la classe de bug rencontrée en
production : un second point d'entrée (club_dixon_coles.py) avait son
propre parseur, jamais migré vers le résolveur unifié, qui plantait sur
tout alias. Ces tests couvrent le résolveur ET son usage depuis les
deux points d'entrée pour empêcher une régression de ce type.
"""
import sync_api_football as s


def test_resolve_big5():
    assert s.resolve_leagues("big5") == [39, 140, 135, 78, 61]


def test_resolve_known_alias():
    assert s.resolve_leagues("ligue1") == [61]
    assert s.resolve_leagues("pl") == [39]


def test_resolve_numeric_id():
    assert s.resolve_leagues("999") == [999]


def test_resolve_mixed_list_dedup():
    # big5 contient déjà 61 (Ligue 1) → pas de doublon
    result = s.resolve_leagues("big5,61,39")
    assert result == [39, 140, 135, 78, 61]


def test_resolve_unknown_alias_ignored_not_crashed():
    # Doit ignorer proprement, jamais lever d'exception
    result = s.resolve_leagues("nimporte_quoi,61")
    assert result == [61]


def test_resolve_extra_registry_alias(tmp_path, monkeypatch):
    """Alias du registre data/leagues.json (ligue2, jupiler, ...)."""
    registry = tmp_path / "leagues.json"
    registry.write_text(
        '{"ligue2": {"id": 62, "name": "Ligue 2", "type": "league"},'
        ' "europa": {"id": 3, "name": "Europa League", "type": "cup"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(s, "EXTRA_LEAGUES_PATH", str(registry))
    assert s.resolve_leagues("ligue2") == [62]
    assert s.resolve_leagues("big5,ligue2") == [39, 140, 135, 78, 61, 62]
    assert sorted(s.resolve_leagues("extra")) == [3, 62]


def test_resolve_extra_alias_without_id_does_not_crash(tmp_path, monkeypatch):
    """Alias connu mais id pas encore renseigné (null) : ignoré, pas d'exception."""
    registry = tmp_path / "leagues.json"
    registry.write_text('{"ligue2": {"id": null, "name": "Ligue 2", "type": "league"}}',
                        encoding="utf-8")
    monkeypatch.setattr(s, "EXTRA_LEAGUES_PATH", str(registry))
    assert s.resolve_leagues("ligue2,61") == [61]


def test_is_cup_competition(tmp_path, monkeypatch):
    registry = tmp_path / "leagues.json"
    registry.write_text(
        '{"europa": {"id": 3, "name": "Europa League", "type": "cup"},'
        ' "ligue2": {"id": 62, "name": "Ligue 2", "type": "league"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(s, "EXTRA_LEAGUES_PATH", str(registry))
    assert s.is_cup_competition(3) is True
    assert s.is_cup_competition(62) is False
    assert s.is_cup_competition(61) is False  # Ligue 1, hors registre


def test_league_display_name_big5():
    assert s.league_display_name(61) == "Ligue 1"


def test_league_display_name_extra(tmp_path, monkeypatch):
    registry = tmp_path / "leagues.json"
    registry.write_text('{"ligue2": {"id": 62, "name": "Ligue 2", "type": "league"}}',
                        encoding="utf-8")
    monkeypatch.setattr(s, "EXTRA_LEAGUES_PATH", str(registry))
    assert s.league_display_name(62) == "Ligue 2"


def test_league_display_name_unknown_falls_back_to_id():
    assert s.league_display_name(999999) == "999999"


def test_club_dixon_coles_cli_uses_same_resolver(tmp_path, monkeypatch):
    """
    Régression directe du bug de production : club_dixon_coles.py avait
    son propre parseur ('big5' ou int() brut) jamais migré. Vérifie que
    son point d'entrée résout maintenant un alias sans lever d'exception.
    """
    import club_dixon_coles as cdc
    registry = tmp_path / "leagues.json"
    registry.write_text('{"ligue2": {"id": 62, "name": "Ligue 2", "type": "league"}}',
                        encoding="utf-8")
    monkeypatch.setattr(s, "EXTRA_LEAGUES_PATH", str(registry))
    # Avant le correctif : `int("ligue2")` levait ValueError ici.
    assert cdc.resolve_leagues("ligue2") == [62]
