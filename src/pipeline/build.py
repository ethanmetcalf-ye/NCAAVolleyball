"""Build the processed SQLite store from raw scraped match JSON.

Reads every data/raw/match_*.json (from src/scraper) plus
data/reference/power4_teams.json, normalizes into the relational schema
in schema.sql, and writes data/processed/volleyball.db. Safe to re-run:
drops and rebuilds the DB from raw data each time (raw data is the
source of truth, this is a derived artifact).

Run from repo root:
    source .venv/bin/activate
    python3 -m src.pipeline.build
"""

import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
REFERENCE_DIR = ROOT / "data" / "reference"
PROCESSED_DIR = ROOT / "data" / "processed"
DB_PATH = PROCESSED_DIR / "volleyball.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

NUMERIC_FIELDS = [
    "sets", "kills", "errors", "total_attacks", "assists", "aces", "service_errors",
    "digs", "reception_attempts", "reception_errors", "block_solos", "block_assists",
    "block_errors", "ball_handling_errors",
]
FLOAT_FIELDS = ["hit_pct", "points"]
STAT_FIELDS = NUMERIC_FIELDS + FLOAT_FIELDS


def to_int(v):
    return None if v in (None, "") else int(v)


def to_float(v):
    return None if v in (None, "") else float(v)


def parse_date(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%m/%d/%Y %I:%M %p")
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def stat_row_values(rec: dict) -> dict:
    out = {f: to_int(rec[f]) for f in NUMERIC_FIELDS}
    out.update({f: to_float(rec[f]) for f in FLOAT_FIELDS})
    return out


def load_raw_matches():
    for path in sorted(RAW_DIR.glob("match_*.json")):
        yield json.loads(path.read_text())


def build_teams_table(raw_matches, power4_teams):
    """Collect every team_id seen across all matches, with the most-common
    short name observed for it. Power4 teams get their conference from
    power4_teams.json; every other opponent gets conference=NULL.
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
        canonical_name = name_counts.most_common(1)[0][0]
        p4 = power4_by_id.get(team_id)
        teams.append({
            "team_id": team_id,
            "name": p4["name"] if p4 else canonical_name,
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
        players.append({
            "player_id": pid,
            "name": names_by_player[pid].most_common(1)[0][0],
            "primary_team_id": teams_by_player[pid].most_common(1)[0][0],
            "primary_position": (positions_by_player[pid].most_common(1)[0][0]
                                  if positions_by_player[pid] else None),
        })
    return players


def build(db_path: Path = DB_PATH):
    power4_teams = json.loads((REFERENCE_DIR / "power4_teams.json").read_text())
    raw_matches = list(load_raw_matches())
    print(f"Loaded {len(raw_matches)} raw match files")

    teams = build_teams_table(raw_matches, power4_teams)
    players = build_players_table(raw_matches)
    print(f"{len(teams)} teams, {len(players)} players")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    db_path.unlink(missing_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_PATH.read_text())

    team_conf = {t["team_id"]: t["conference"] for t in teams}
    team_p4 = {t["team_id"]: t["is_power4"] for t in teams}

    conn.executemany(
        "INSERT INTO teams (team_id, name, conference, is_power4) "
        "VALUES (:team_id, :name, :conference, :is_power4)",
        teams,
    )
    conn.executemany(
        "INSERT INTO players (player_id, name, primary_team_id, primary_position) "
        "VALUES (:player_id, :name, :primary_team_id, :primary_position)",
        players,
    )

    match_rows, team_stat_rows, player_stat_rows = [], [], []
    for raw in raw_matches:
        m = raw["match"]
        away_id, home_id = m["teams"][0]["team_id"], m["teams"][1]["team_id"]
        both_p4 = bool(team_p4.get(away_id) and team_p4.get(home_id))
        same_conf = both_p4 and team_conf.get(away_id) == team_conf.get(home_id)
        away_scores = [int(s) for s in m["away_team"]["set_scores"]]
        home_scores = [int(s) for s in m["home_team"]["set_scores"]]

        match_rows.append({
            "contest_id": m["contest_id"],
            "date": parse_date(m["date"]),
            "away_team_id": away_id,
            "home_team_id": home_id,
            "away_sets_won": int(m["away_team"]["sets_won"]),
            "home_sets_won": int(m["home_team"]["sets_won"]),
            "num_sets": len(away_scores),
            "away_set_scores": json.dumps(away_scores),
            "home_set_scores": json.dumps(home_scores),
            "venue": m["venue"],
            "attendance": m["attendance"],
            "both_power4": int(both_p4),
            "is_conference_match": int(same_conf),
        })

        for t in raw["team_totals"]:
            if t["is_team_total"] and t["name"] == "TEAM":
                continue  # unattributed-stats breakdown row, not a real team total
            row = {"contest_id": m["contest_id"], "team_id": t["team_id"]}
            row.update(stat_row_values(t))
            team_stat_rows.append(row)

        for p in raw["player_stats"]:
            row = {
                "contest_id": m["contest_id"],
                "player_id": p["player_id"],
                "team_id": p["team_id"],
                "jersey": p["jersey"] or None,
                "position": p["position"] or None,
            }
            row.update(stat_row_values(p))
            player_stat_rows.append(row)

    # Explicit column lists in every INSERT below: with named placeholders but
    # no column list, sqlite maps values positionally by the *table's* DDL
    # order, not by STAT_FIELDS' order -- those had drifted apart and every
    # stat from hit_pct onward landed in the wrong column.
    match_cols = list(match_rows[0].keys())
    conn.executemany(
        f"INSERT INTO matches ({', '.join(match_cols)}) "
        f"VALUES ({', '.join(':' + c for c in match_cols)})",
        match_rows,
    )

    stat_cols = ["contest_id", "team_id"] + STAT_FIELDS
    conn.executemany(
        f"INSERT INTO team_match_stats ({', '.join(stat_cols)}) "
        f"VALUES ({', '.join(':' + c for c in stat_cols)})",
        team_stat_rows,
    )

    player_stat_cols = ["contest_id", "player_id", "team_id", "jersey", "position"] + STAT_FIELDS
    conn.executemany(
        f"INSERT INTO player_match_stats ({', '.join(player_stat_cols)}) "
        f"VALUES ({', '.join(':' + c for c in player_stat_cols)})",
        player_stat_rows,
    )

    conn.commit()
    print(f"{len(match_rows)} matches, {len(team_stat_rows)} team-match rows, "
          f"{len(player_stat_rows)} player-match rows")
    print(f"Wrote {db_path}")
    conn.close()


if __name__ == "__main__":
    build()
