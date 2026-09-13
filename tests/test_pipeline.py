import json
import sqlite3

import pytest

from src.analysis import correlations
from src.dashboard import build as dashboard
from src.pipeline import build, validate
from tests.conftest import ALPHA, BETA, GAMMA, XRAY


def query(db_path, sql, params=()):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(sql, params)]
    conn.close()
    return rows


def test_site_type_host_and_season_phase(db_path):
    rows = {r["contest_id"]: (r["site_type"], r["host_team_id"], r["season_phase"], r["is_conference_match"])
            for r in query(db_path, "SELECT * FROM matches")}
    assert rows == {
        "9000001": ("home", ALPHA, "regular", 1),
        "9000002": ("neutral", None, "conference_tournament", 1),
        "9000003": ("neutral", None, "postseason", 1),
        "9000004": (None, None, "regular", 0),
        "9000005": ("home", GAMMA, "regular", 0),
        "9000006": ("neutral", None, "regular", 0),
        "9000007": ("home", GAMMA, "regular", 0),
        "9000008": ("home", BETA, "regular", 0),
    }


def test_dates_venues_and_sets_are_normalized(db_path):
    m = query(db_path, "SELECT * FROM matches WHERE contest_id = '9000002'")[0]
    assert (m["match_date"], m["start_time"]) == ("2025-11-22", "14:30")
    assert query(db_path, "SELECT venue FROM matches WHERE contest_id = '9000001'")[0]["venue"] \
        == "Alpha Arena (Alphaville, AL)"
    sets = query(db_path, "SELECT set_number, away_points, home_points FROM match_sets "
                          "WHERE contest_id = '9000002' ORDER BY set_number")
    assert [(s["away_points"], s["home_points"]) for s in sets] == [(22, 25), (25, 20), (23, 25), (25, 22), (13, 15)]


def test_position_groups_merge_back_row_specialists(db_path):
    groups = {r["player_id"]: r["position_group"] for r in query(db_path, "SELECT * FROM players")}
    assert groups[f"{XRAY}01"] == groups[f"{XRAY}02"] == "L/DS"
    assert groups[f"{ALPHA}01"] == "OH"


def test_location_is_from_each_teams_perspective(db_path):
    loc = {(r["contest_id"], r["team_id"]): r["location"]
           for r in query(db_path, "SELECT contest_id, team_id, location FROM team_match_features")}
    assert loc[("9000001", ALPHA)] == "home" and loc[("9000001", BETA)] == "away"
    assert loc[("9000002", ALPHA)] == loc[("9000002", BETA)] == "neutral"
    assert loc[("9000004", ALPHA)] is None
    # listed away, but it's Gamma's building
    assert loc[("9000007", GAMMA)] == "home" and loc[("9000007", XRAY)] == "away"


def test_block_conventions(db_path):
    team = query(db_path, "SELECT f.blocks, s.block_solos, s.block_assists FROM team_match_features f "
                          "JOIN team_match_stats s USING (contest_id, team_id)")
    assert all(r["blocks"] == r["block_solos"] + 0.5 * r["block_assists"] for r in team)
    player = query(db_path, "SELECT blocks, block_solos, block_assists FROM player_season_stats")
    assert all(r["blocks"] == r["block_solos"] + r["block_assists"] for r in player)


def test_team_hit_pct_is_attempt_weighted(db_path):
    raw = query(db_path, "SELECT kills, errors, total_attacks FROM team_match_stats WHERE team_id = ?", (ALPHA,))
    expected = sum(r["kills"] - r["errors"] for r in raw) / sum(r["total_attacks"] for r in raw)
    actual = query(db_path, "SELECT hit_pct FROM team_season_stats WHERE team_id = ?", (ALPHA,))[0]["hit_pct"]
    assert actual == pytest.approx(expected)


def test_strength_of_schedule_uses_power4_opponents_excluding_head_to_head(db_path):
    # Worked by hand from MATCHES. Records: Alpha 2-2, Beta 2-2, Gamma 3-1, Xray 1-3.
    #   Alpha: Beta x3, Beta's record without Alpha = 1-0             -> 1.0
    #   Beta:  Alpha x3 (0-1 without Beta), Gamma x1 (3-0 w/o Beta)   -> (0+0+0+1)/4
    #   Gamma: Xray excluded (non-Power4); Beta x1 (1-2 w/o Gamma)    -> 1/3
    #   Xray:  Alpha x1 (2-1 w/o Xray), Gamma x3 (0-1 w/o Xray)       -> (2/3)/4
    sos = {r["team_id"]: r["strength_of_schedule"]
           for r in query(db_path, "SELECT team_id, strength_of_schedule FROM team_season_stats")}
    assert sos == pytest.approx({ALPHA: 1.0, BETA: 0.25, GAMMA: 1 / 3, XRAY: 1 / 6})


def test_conference_record_excludes_postseason(db_path):
    rec = {r["team_id"]: (r["conf_wins"], r["conf_losses"])
           for r in query(db_path, "SELECT team_id, conf_wins, conf_losses FROM team_season_stats")}
    assert rec[ALPHA] == (1, 1) and rec[BETA] == (1, 1) and rec[GAMMA] == (0, 0)


def test_game_spine_is_regular_season_and_conference_tournament_only(db_path):
    spine = query(db_path, "SELECT contest_id, site_type, home_won FROM game_spine ORDER BY contest_id")
    assert spine == [
        {"contest_id": "9000001", "site_type": "home", "home_won": 1},
        {"contest_id": "9000002", "site_type": "neutral", "home_won": 1},
    ]


def test_validate_passes_on_clean_data(db_path, reference_dir):
    assert validate.run(db_path, reference_dir=reference_dir, season="2025") == []


@pytest.mark.parametrize("corruption, failing_check", [
    ("UPDATE team_match_stats SET hit_pct = 0.9 WHERE contest_id = '9000001'",
     "hit_pct arithmetic mismatch in team_match_stats"),
    ("UPDATE match_sets SET away_points = 24 WHERE contest_id = '9000001' AND set_number = 1",
     "illegal set score (sets 1-4 to 25, set 5 to 15, win by 2; overtime ends at +2)"),
    ("UPDATE player_match_stats SET kills = kills + 1, points = points + 1 "
     "WHERE contest_id = '9000001' AND player_id = '10000101'",
     "team totals don't reconcile with sum of player rows"),
    ("UPDATE matches SET site_type = NULL, host_team_id = NULL WHERE contest_id = '9000001'",
     "Power4-hosted match with unknown site_type"),
])
def test_validate_catches_corruption(db_path, reference_dir, corruption, failing_check):
    conn = sqlite3.connect(db_path)
    conn.execute(corruption)
    conn.commit()
    conn.close()
    assert failing_check in validate.run(db_path, reference_dir=reference_dir, season="2025")


def test_failed_build_leaves_existing_db_untouched(tmp_path, raw_dir, reference_dir):
    db_path = tmp_path / "existing.db"
    db_path.write_text("previous good build")
    bad = json.loads((raw_dir / "match_9000001.json").read_text())
    bad["player_stats"][0]["team_id"] = "unknown-team"  # violates a foreign key mid-load
    (raw_dir / "match_9000001.json").write_text(json.dumps(bad))

    with pytest.raises(sqlite3.IntegrityError):
        build.build(db_path, raw_dir=raw_dir, reference_dir=reference_dir, season="2025")

    assert db_path.read_text() == "previous good build"
    assert list(tmp_path.glob("*.tmp")) == []


def test_downstream_consumers_run_against_views(db_path, tmp_path):
    assert len(correlations.compute(db_path)) == len(correlations.STAT_LABELS)
    out = tmp_path / "dashboard.html"
    dashboard.build(db_path, output_path=out)
    assert "/*__DASHBOARD_DATA__*/" not in out.read_text()
