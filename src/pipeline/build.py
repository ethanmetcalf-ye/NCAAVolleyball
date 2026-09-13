"""Build the processed SQLite store from raw scraped match JSON.

Reads every data/raw/match_*.json (from the scraper, not in this repo),
data/reference/power4_teams.json, and data/reference/season_{SEASON}.json;
normalizes into the raw tables in schema.sql and creates the derived views
in views.sql. Raw data is the source of truth and the DB is a derived
artifact, so every build starts from scratch. The new DB is written to a
temporary file and swapped in only once complete, so a failed build never
leaves a missing or half-written volleyball.db behind.

Run from repo root (or use `python3 -m src.pipeline` to build + validate +
regenerate the dashboard in one go):
    source .venv/bin/activate
    python3 -m src.pipeline.build
"""

import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from src import db
from src.config import DB_PATH, RAW_DIR, REFERENCE_DIR, SEASON

SQL_DIR = Path(__file__).parent

NUMERIC_FIELDS = [
    "sets", "kills", "errors", "total_attacks", "assists", "aces", "service_errors",
    "digs", "reception_attempts", "reception_errors", "block_solos", "block_assists",
    "block_errors", "ball_handling_errors",
]
FLOAT_FIELDS = ["hit_pct", "points"]
STAT_FIELDS = NUMERIC_FIELDS + FLOAT_FIELDS

# Liberos and defensive specialists are listed inconsistently (L, DS, L/DS)
# for what is the same back-row role, so they share one group.
POSITION_GROUPS = {"OH": "OH", "OPP": "OPP", "MB": "MB", "S": "S", "L": "L/DS", "DS": "L/DS", "L/DS": "L/DS"}


def to_int(v):
    return None if v in (None, "") else int(v)


def to_float(v):
    return None if v in (None, "") else float(v)


def normalize_venue(venue: str) -> str:
    return re.sub(r"\s+", " ", venue).strip()


def stat_row_values(rec: dict) -> dict:
    out = {f: to_int(rec[f]) for f in NUMERIC_FIELDS}
    out.update({f: to_float(rec[f]) for f in FLOAT_FIELDS})
    return out


def load_raw_matches(raw_dir: Path):
    for path in sorted(raw_dir.glob("match_*.json")):
        yield json.loads(path.read_text())


def load_season_config(reference_dir: Path, season: str) -> dict:
    return json.loads((reference_dir / f"season_{season}.json").read_text())


def build_teams_table(raw_matches, power4_teams):
    """Collect every team_id seen across all matches, with the most-common
    short name observed for it. Power4 teams get their name and conference
    from power4_teams.json; every other opponent gets conference=NULL.
    """
    power4_by_id = {t["team_id"]: t for t in power4_teams}
    names_by_team = defaultdict(Counter)

    for raw in raw_matches:
        m = raw["match"]
        pairs = [(m["teams"][0]["team_id"], m["away_team"]["name"]),
                 (m["teams"][1]["team_id"], m["home_team"]["name"])]
        for team_id, name in pairs:
            names_by_team[team_id][name] += 1

    teams = []
    for team_id, name_counts in names_by_team.items():
        p4 = power4_by_id.get(team_id)
        teams.append({
            "team_id": team_id,
            "name": p4["name"] if p4 else name_counts.most_common(1)[0][0],
            "conference": p4["conference"] if p4 else None,
            "is_power4": 1 if p4 else 0,
        })
    return teams


def build_players_table(raw_matches):
    names_by_player = defaultdict(Counter)
    teams_by_player = defaultdict(Counter)
    positions_by_player = defaultdict(Counter)

    for raw in raw_matches:
        for p in raw["player_stats"]:
            pid = p["player_id"]
            names_by_player[pid][p["name"]] += 1
            teams_by_player[pid][p["team_id"]] += 1
            if p["position"]:
                positions_by_player[pid][p["position"]] += 1

    players = []
    for pid in names_by_player:
        position = (positions_by_player[pid].most_common(1)[0][0]
                    if positions_by_player[pid] else None)
        players.append({
            "player_id": pid,
            "name": names_by_player[pid].most_common(1)[0][0],
            "primary_team_id": teams_by_player[pid].most_common(1)[0][0],
            "primary_position": position,
            "position_group": POSITION_GROUPS.get(position),
        })
    return players


def classify_site(venue, home_id, away_id, team_by_home_venue, power4_ids):
    """Return (site_type, host_team_id) for one match.

    Home venues are curated only for Power4 teams (power4_teams.json), so:
      - venue is either team's home venue -> 'home', hosted by that team
        (usually the listed home team; occasionally the source lists the
        host as away)
      - venue is some other Power4 team's home venue -> 'neutral'
      - listed home team is Power4 and not at its home venue -> 'neutral'
      - otherwise (non-Power4 listed home, venue not tracked) -> unknown
    """
    owner = team_by_home_venue.get(venue)
    if owner in (home_id, away_id):
        return "home", owner
    if owner is not None or home_id in power4_ids:
        return "neutral", None
    return None, None


def classify_phase(match_date, venue, same_conference, conference, season_config):
    if match_date >= season_config["postseason_start"]:
        return "postseason"
    for t in season_config["conference_tournaments"]:
        if (same_conference and conference == t["conference"] and venue == t["venue"]
                and t["start"] <= match_date <= t["end"]):
            return "conference_tournament"
    return "regular"


def build(db_path: Path = DB_PATH, raw_dir: Path = RAW_DIR,
          reference_dir: Path = REFERENCE_DIR, season: str = SEASON):
    power4_teams = json.loads((reference_dir / "power4_teams.json").read_text())
    season_config = load_season_config(reference_dir, season)
    raw_matches = list(load_raw_matches(raw_dir))
    if not raw_matches:
        raise FileNotFoundError(f"no match_*.json files in {raw_dir}")
    print(f"Loaded {len(raw_matches)} raw match files")

    teams = build_teams_table(raw_matches, power4_teams)
    players = build_players_table(raw_matches)
    print(f"{len(teams)} teams, {len(players)} players")

    team_conf = {t["team_id"]: t["conference"] for t in teams}
    power4_ids = {t["team_id"] for t in teams if t["is_power4"]}
    team_by_home_venue = {normalize_venue(v): t["team_id"]
                          for t in power4_teams for v in t["home_venues"]}

    match_rows, set_rows, team_stat_rows, player_stat_rows = [], [], [], []
    for raw in raw_matches:
        m = raw["match"]
        contest_id = m["contest_id"]
        away_id, home_id = m["teams"][0]["team_id"], m["teams"][1]["team_id"]
        started = datetime.strptime(m["date"], "%m/%d/%Y %I:%M %p")
        match_date = started.strftime("%Y-%m-%d")
        venue = normalize_venue(m["venue"])
        both_p4 = away_id in power4_ids and home_id in power4_ids
        same_conf = both_p4 and team_conf[away_id] == team_conf[home_id]
        site_type, host_team_id = classify_site(venue, home_id, away_id, team_by_home_venue, power4_ids)
        away_scores = [int(s) for s in m["away_team"]["set_scores"]]
        home_scores = [int(s) for s in m["home_team"]["set_scores"]]

        match_rows.append({
            "contest_id": contest_id,
            "match_date": match_date,
            "start_time": started.strftime("%H:%M"),
            "away_team_id": away_id,
            "home_team_id": home_id,
            "away_sets_won": int(m["away_team"]["sets_won"]),
            "home_sets_won": int(m["home_team"]["sets_won"]),
            "num_sets": len(away_scores),
            "venue": venue,
            "attendance": m["attendance"],
            "site_type": site_type,
            "host_team_id": host_team_id,
            "season_phase": classify_phase(match_date, venue, same_conf, team_conf[home_id], season_config),
            "both_power4": int(both_p4),
            "is_conference_match": int(same_conf),
        })

        for set_number, (away_pts, home_pts) in enumerate(zip(away_scores, home_scores), start=1):
            set_rows.append({"contest_id": contest_id, "set_number": set_number,
                             "away_points": away_pts, "home_points": home_pts})

        for t in raw["team_totals"]:
            if t["is_team_total"] and t["name"] == "TEAM":
                continue  # unattributed-stats breakdown row, not a real team total
            row = {"contest_id": contest_id, "team_id": t["team_id"]}
            row.update(stat_row_values(t))
            team_stat_rows.append(row)

        for p in raw["player_stats"]:
            row = {
                "contest_id": contest_id,
                "player_id": p["player_id"],
                "team_id": p["team_id"],
                "jersey": p["jersey"] or None,
                "position": p["position"] or None,
            }
            row.update(stat_row_values(p))
            player_stat_rows.append(row)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = db_path.with_name(db_path.name + ".tmp")
    tmp_path.unlink(missing_ok=True)
    conn = db.connect(tmp_path)
    try:
        conn.executescript((SQL_DIR / "schema.sql").read_text())
        # Parents before children, so foreign keys are enforced on insert.
        # Explicit column lists everywhere: with named placeholders but no
        # column list, sqlite maps values by the table's DDL order, which
        # once silently shifted every stat from hit_pct onward.
        for table, rows in [("teams", teams), ("players", players), ("matches", match_rows),
                            ("match_sets", set_rows), ("team_match_stats", team_stat_rows),
                            ("player_match_stats", player_stat_rows)]:
            cols = list(rows[0].keys())
            conn.executemany(
                f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)})",
                rows,
            )
        conn.executescript((SQL_DIR / "views.sql").read_text())
        conn.commit()
    except BaseException:
        conn.close()
        tmp_path.unlink(missing_ok=True)
        raise
    conn.close()
    os.replace(tmp_path, db_path)

    print(f"{len(match_rows)} matches, {len(set_rows)} sets, {len(team_stat_rows)} team-match rows, "
          f"{len(player_stat_rows)} player-match rows")
    print(f"Wrote {db_path}")


if __name__ == "__main__":
    build()
