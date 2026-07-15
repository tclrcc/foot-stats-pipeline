"""
Tests du pont inter-divisions (TIER_LINKS) : un club promu/relégué,
sous le seuil de matchs dans sa nouvelle division, doit être complété
par une estimation rescalée depuis la division liée plutôt qu'exclu
entièrement du modèle jusqu'à accumuler 10 matchs.
"""
import sqlite3
import club_dixon_coles as cdc


def _seed_promotion_scenario(db_path):
    """Ligue 2 (62) : corpus complet. Ligue 1 (61) : gros clubs + le
    promu 'Troyes' avec seulement 3 matchs (sous le seuil de 10)."""
    import itertools, random
    random.seed(5)
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE club_matches (
        fixture_id INTEGER PRIMARY KEY, league_id INTEGER, league_name TEXT, season INTEGER,
        date TEXT, round TEXT, home_team TEXT, away_team TEXT,
        home_score INTEGER, away_score INTEGER, status TEXT, home_id INTEGER, away_id INTEGER)""")
    rows, fid = [], 0
    l2_teams = ["Troyes", "Rodez", "Laval", "Amiens", "Guingamp", "Grenoble", "Pau", "Annecy"]
    for i, (h, a) in enumerate(itertools.permutations(l2_teams, 2)):
        fid += 1
        rows.append((fid, 62, "Ligue 2", 2025, f"2025-{9+i%3:02d}-{(i%27)+1:02d}", f"J{i//4+1}",
                    h, a, max(0, int(random.gauss(1.1, 0.8))), max(0, int(random.gauss(0.9, 0.8))),
                    "FT", None, None))
    l1_teams = ["Paris Saint Germain", "Marseille", "Lyon", "Monaco", "Lille", "Nice", "Lens", "Rennes"]
    for i, (h, a) in enumerate(itertools.permutations(l1_teams, 2)):
        fid += 1
        rows.append((fid, 61, "Ligue 1", 2025, f"2025-{9+i%3:02d}-{(i%27)+1:02d}", f"J{i//4+1}",
                    h, a, max(0, int(random.gauss(1.6, 1))), max(0, int(random.gauss(1.1, 1))),
                    "FT", None, None))
    for i, (h, a) in enumerate([("Paris Saint Germain", "Troyes"), ("Troyes", "Lyon"),
                                ("Marseille", "Troyes")]):
        fid += 1
        rows.append((fid, 61, "Ligue 1", 2025, f"2025-08-{i+10:02d}", "J1", h, a, 2, 0, "FT", None, None))
    conn.executemany("INSERT INTO club_matches VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()


def test_promoted_team_excluded_without_cross_tier_source(temp_db):
    """Sans division liée entraînée au préalable, le promu reste exclu (comportement d'avant)."""
    _seed_promotion_scenario(temp_db)
    cdc.train_league(61, verbose=False)
    conn = sqlite3.connect(temp_db)
    row = conn.execute("SELECT * FROM club_dc_params WHERE league_id=61 AND team='Troyes'").fetchone()
    conn.close()
    assert row is None


def test_promoted_team_borrowed_and_rescaled(temp_db):
    """Ligue 2 entraînée d'abord -> Ligue 1 doit emprunter et rescaler Troyes."""
    _seed_promotion_scenario(temp_db)
    cdc.train_league(62, verbose=False)
    cdc.train_league(61, verbose=False)

    conn = sqlite3.connect(temp_db)
    troyes_l2 = conn.execute(
        "SELECT alpha, beta FROM club_dc_params WHERE league_id=62 AND team='Troyes'").fetchone()
    troyes_l1 = conn.execute(
        "SELECT alpha, beta, source_league_id FROM club_dc_params WHERE league_id=61 AND team='Troyes'"
    ).fetchone()
    l1_avg_alpha = conn.execute(
        "SELECT AVG(alpha) FROM club_dc_params WHERE league_id=61 AND source_league_id IS NULL"
    ).fetchone()[0]
    l2_avg_alpha = conn.execute("SELECT AVG(alpha) FROM club_dc_params WHERE league_id=62").fetchone()[0]
    conn.close()

    assert troyes_l1 is not None
    assert troyes_l1[2] == 62  # source_league_id marqué
    expected_alpha = troyes_l2[0] * (l1_avg_alpha / l2_avg_alpha)
    assert abs(expected_alpha - troyes_l1[0]) < 1e-6  # rescaling exact, pas une copie brute
    assert troyes_l1[0] != troyes_l2[0]  # jamais une copie brute (échelles différentes)


def test_predict_flags_estimation_only_when_relevant(temp_db):
    _seed_promotion_scenario(temp_db)
    cdc.train_league(62, verbose=False)
    cdc.train_league(61, verbose=False)

    import service
    pred_estimated = service.club_predict(61, "Paris Saint Germain", "Troyes")
    pred_normal = service.club_predict(61, "Paris Saint Germain", "Lyon")

    assert pred_estimated is not None and "+estimation" in pred_estimated["method"]
    assert pred_normal is not None and "+estimation" not in pred_normal["method"]


def test_promoted_team_appears_in_club_teams_listing(temp_db):
    """Avant ce pont, une equipe exclue etait invisible partout (dropdown compris)."""
    _seed_promotion_scenario(temp_db)
    cdc.train_league(62, verbose=False)
    cdc.train_league(61, verbose=False)

    import service
    teams = service.club_teams(61)
    assert any(t["team"] == "Troyes" for t in teams)


def test_no_borrow_when_no_tier_link_exists(temp_db):
    """Une ligue sans lien configuré (ex. Bundesliga=78) n'emprunte jamais."""
    import itertools
    conn = sqlite3.connect(temp_db)
    conn.execute("""CREATE TABLE club_matches (
        fixture_id INTEGER PRIMARY KEY, league_id INTEGER, league_name TEXT, season INTEGER,
        date TEXT, round TEXT, home_team TEXT, away_team TEXT,
        home_score INTEGER, away_score INTEGER, status TEXT, home_id INTEGER, away_id INTEGER)""")
    # Round-robin réel entre 5 équipes (deux manches -> 16 matchs/équipe,
    # au-dessus du seuil), + SmallClub avec 1 seul match (sous le seuil)
    # pour tester l'absence d'emprunt.
    big_teams = ["Bayern", "Dortmund", "Leipzig", "Leverkusen", "Frankfurt"]
    rows, fid = [], 0
    for leg in range(2):
        for i, (h, a) in enumerate(itertools.permutations(big_teams, 2)):
            fid += 1
            rows.append((fid, 78, "Bundesliga", 2025, f"2025-{9+leg:02d}-{(i%27)+1:02d}",
                        "J1", h, a, 2, 1, "FT", None, None))
    fid += 1
    rows.append((fid, 78, "Bundesliga", 2025, "2025-10-01", "J2", "Bayern", "SmallClub", 3, 0, "FT", None, None))
    conn.executemany("INSERT INTO club_matches VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    assert 78 not in cdc.TIER_LINKS
    cdc.train_league(78, verbose=False)
    conn = sqlite3.connect(temp_db)
    row = conn.execute("SELECT * FROM club_dc_params WHERE team='SmallClub'").fetchone()
    bayern = conn.execute("SELECT * FROM club_dc_params WHERE team='Bayern'").fetchone()
    conn.close()
    assert row is None          # sous le seuil, aucun lien -> exclu
    assert bayern is not None   # équipe normale, bien ajustée
