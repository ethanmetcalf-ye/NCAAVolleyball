"""Synthetic raw data for pipeline tests.

Scraped data isn't committed to this repo, so tests build a small fake season
in the same raw JSON shape the scraper writes. Each match exercises one case
the pipeline has to classify (see MATCHES).
"""

import json

import pytest

from src.pipeline import build

ALPHA, BETA, GAMMA, XRAY = "100001", "100002", "100003", "200001"

POWER4_TEAMS = [
    {"team_id": ALPHA, "name": "Alpha", "conference": "SEC", "home_venues": ["Alpha Arena (Alphaville, AL)"]},
    {"team_id": BETA, "name": "Beta", "conference": "SEC", "home_venues": ["Beta Gym (Betatown, BT)"]},
    {"team_id": GAMMA, "name": "Gamma", "conference": "ACC", "home_venues": ["Gamma Center (Gammaburg, GA)"]},
]
TEAM_NAMES = {ALPHA: "Alpha", BETA: "Beta", GAMMA: "Gamma", XRAY: "Xray"}
POSITIONS = {ALPHA: ("OH", "S"), BETA: ("MB", "OPP"), GAMMA: ("OH", "S"), XRAY: ("L", "DS")}

# contest_id, date, away, home, venue, away set scores, home set scores
MATCHES = [
    # regular-season conference match at Alpha's home (venue has stray whitespace)
    ("9000001", "09/20/2025 07:00 PM", BETA, ALPHA, "Alpha Arena  (Alphaville, AL)", [20, 25, 18, 22], [25, 23, 25, 25]),
    # conference tournament: neutral site, inside the tournament window
    ("9000002", "11/22/2025 02:30 PM", ALPHA, BETA, "Tourney Hall (Neutral City, NC)", [22, 25, 23, 25, 13], [25, 20, 25, 22, 15]),
    # same-conference postseason meeting (like the NCAA final): excluded from game_spine
    ("9000003", "12/21/2025 03:30 PM", ALPHA, BETA, "Final Arena (Kansas City, MO)", [25, 25, 25], [20, 21, 19]),
    # non-Power4 host at an untracked venue: site_type unknown
    ("9000004", "09/05/2025 06:00 PM", ALPHA, XRAY, "Xray Gym (Xville, XX)", [20, 25, 20, 19], [25, 23, 25, 25]),
    # Power4 team at its own home venue vs non-Power4
    ("9000005", "09/10/2025 07:00 PM", XRAY, GAMMA, "Gamma Center (Gammaburg, GA)", [15, 17, 20], [25, 25, 25]),
    # non-Power4 listed home at a third Power4 team's venue: neutral
    ("9000006", "09/12/2025 07:00 PM", GAMMA, XRAY, "Beta Gym (Betatown, BT)", [25, 22, 25, 25], [18, 25, 20, 16]),
    # source lists the host (Gamma, at its own venue) as the away team
    ("9000007", "09/14/2025 01:00 PM", GAMMA, XRAY, "Gamma Center (Gammaburg, GA)", [25, 25, 25], [10, 12, 14]),
    # non-conference Power4 vs Power4 at Beta's home
    ("9000008", "10/01/2025 07:00 PM", GAMMA, BETA, "Beta Gym (Betatown, BT)", [20, 20, 20], [25, 25, 25]),
]

SEASON_CONFIG = {
    "season": "2025",
    "postseason_start": "2025-12-04",
    "conference_tournaments": [
        {"conference": "SEC", "venue": "Tourney Hall (Neutral City, NC)", "start": "2025-11-21", "end": "2025-11-25"},
    ],
    "known_anomalies": {"illegal_set_scores": {}},
    "expected_counts": {
        "teams": 4,
        "power4_teams": 3,
        "matches": 8,
        "match_sets": 29,
        "team_match_stats": 16,
        "players": 8,
        "player_match_stats": 32,
        "matches_by_season_phase": {"conference_tournament": 1, "postseason": 1, "regular": 6},
        "matches_by_site_type": {"home": 4, "neutral": 3, "unknown": 1},
        "game_spine": 2,
        "game_spine_by_conference": {"SEC": 2},
        "champion": "Alpha",
    },
}


def stat_line(team_id, contest_id, num_sets, slot, seed):
    """One player's box-score line; slot 0 is an attacker, slot 1 a setter."""
    kills, errors, attacks = (10 + seed, 3 + seed % 3, 30 + seed) if slot == 0 else (2, 1, 8)
    line = {
        "sets": num_sets, "kills": kills, "errors": errors, "total_attacks": attacks,
        "assists": 1 if slot == 0 else 25 + seed, "aces": 1 + slot, "service_errors": 2,
        "digs": 6 + seed, "reception_attempts": 12, "reception_errors": 1,
        "block_solos": 1 - slot, "block_assists": 2 + slot, "block_errors": 0, "ball_handling_errors": slot,
    }
    line["hit_pct"] = f"{(kills - errors) / attacks:.3f}"
    line["points"] = f"{kills + line['aces'] + line['block_solos'] + 0.5 * line['block_assists']:.1f}"
    return {k: str(v) for k, v in line.items()}


def raw_match(contest_id, date, away, home, venue, away_sets, home_sets, seed):
    num_sets = len(away_sets)
    player_stats, team_totals = [], []
    for team_id in (away, home):
        lines = []
        for slot in (0, 1):
            line = stat_line(team_id, contest_id, num_sets, slot, seed + int(team_id) % 7)
            lines.append(line)
            player_stats.append({
                "jersey": str(slot + 1), "name": f"{TEAM_NAMES[team_id]} Player {slot + 1}",
                "position": POSITIONS[team_id][slot], **line,
                "player_id": f"{team_id}{slot + 1:02d}", "is_team_total": False,
                "contest_id": contest_id, "team_id": team_id,
            })
        zero = {k: "0" for k in lines[0]}
        total = {k: str(sum(float(l[k]) for l in lines)) for k in lines[0]}
        for k in lines[0]:
            if k not in ("points", "hit_pct"):
                total[k] = str(int(float(total[k])))
        total["sets"] = str(num_sets)
        total["hit_pct"] = f"{(int(total['kills']) - int(total['errors'])) / int(total['total_attacks']):.3f}"
        for name, row in (("TEAM", zero), (TEAM_NAMES[team_id], total)):
            team_totals.append({"jersey": "", "name": name, "position": "", **row, "player_id": None,
                                "is_team_total": True, "contest_id": contest_id, "team_id": team_id})
    return {
        "match": {
            "contest_id": contest_id,
            "teams": [{"team_id": away, "name": TEAM_NAMES[away]}, {"team_id": home, "name": TEAM_NAMES[home]}],
            "away_team": {"name": TEAM_NAMES[away], "set_scores": [str(s) for s in away_sets],
                          "sets_won": str(sum(a > h for a, h in zip(away_sets, home_sets)))},
            "home_team": {"name": TEAM_NAMES[home], "set_scores": [str(s) for s in home_sets],
                          "sets_won": str(sum(h > a for a, h in zip(away_sets, home_sets)))},
            "date": date, "venue": venue, "attendance": 1000 + seed,
        },
        "player_stats": player_stats,
        "team_totals": team_totals,
    }


@pytest.fixture
def raw_dir(tmp_path):
    d = tmp_path / "raw"
    d.mkdir()
    for seed, m in enumerate(MATCHES):
        (d / f"match_{m[0]}.json").write_text(json.dumps(raw_match(*m, seed=seed)))
    return d


@pytest.fixture
def reference_dir(tmp_path):
    d = tmp_path / "reference"
    d.mkdir()
    (d / "power4_teams.json").write_text(json.dumps(POWER4_TEAMS))
    (d / "season_2025.json").write_text(json.dumps(SEASON_CONFIG))
    return d


@pytest.fixture
def db_path(tmp_path, raw_dir, reference_dir):
    path = tmp_path / "processed" / "test.db"
    build.build(path, raw_dir=raw_dir, reference_dir=reference_dir, season="2025")
    return path
