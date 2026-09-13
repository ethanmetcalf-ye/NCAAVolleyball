"""Derive a feature layer on top of the normalized raw tables.

Adds two tables to data/processed/volleyball.db:
  - team_match_features: per-set rates and efficiency for one team in one
    match. Deliberately match-level (not pre-averaged into a fixed rolling
    window) so any window size can be computed downstream.
  - team_season_stats: season aggregates + a strength-of-schedule metric
    (mean opponent win_pct, using each opponent's full-season win_pct --
    a simplification, since a fully non-circular SOS would need iterative
    resolution and isn't warranted for a first pass).

Run from repo root, after src/pipeline/build.py:
    source .venv/bin/activate
    python3 -m src.pipeline.features
"""

import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "processed" / "volleyball.db"
SCHEMA_PATH = Path(__file__).parent / "features.sql"


def build(db_path: Path = DB_PATH):
    conn = sqlite3.connect(db_path)

    matches = pd.read_sql("SELECT * FROM matches", conn)
    stats = pd.read_sql("SELECT * FROM team_match_stats", conn)

    # One row per team-match, with the opponent's row alongside it.
    away = matches[["contest_id", "date", "away_team_id", "home_team_id",
                     "away_sets_won", "home_sets_won"]].rename(
        columns={"away_team_id": "team_id", "home_team_id": "opponent_team_id",
                 "away_sets_won": "team_sets_won", "home_sets_won": "opp_sets_won"})
    home = matches[["contest_id", "date", "home_team_id", "away_team_id",
                     "home_sets_won", "away_sets_won"]].rename(
        columns={"home_team_id": "team_id", "away_team_id": "opponent_team_id",
                 "home_sets_won": "team_sets_won", "away_sets_won": "opp_sets_won"})
    sides = pd.concat([away, home], ignore_index=True)
    sides["won"] = (sides["team_sets_won"] > sides["opp_sets_won"]).astype(int)

    merged = sides.merge(stats, on=["contest_id", "team_id"])
    opp_stats = stats.rename(columns={"team_id": "opponent_team_id", "hit_pct": "opponent_hit_pct"})
    merged = merged.merge(opp_stats[["contest_id", "opponent_team_id", "opponent_hit_pct"]],
                           on=["contest_id", "opponent_team_id"])

    merged["error_pct"] = merged["errors"] / merged["total_attacks"].replace(0, pd.NA)
    merged["kills_per_set"] = merged["kills"] / merged["sets"]
    merged["digs_per_set"] = merged["digs"] / merged["sets"]
    merged["blocks_per_set"] = (merged["block_solos"] + merged["block_assists"]) / merged["sets"]
    merged["aces_per_set"] = merged["aces"] / merged["sets"]
    merged["assists_per_set"] = merged["assists"] / merged["sets"]
    merged["point_differential"] = merged["points"] - merged.merge(
        stats.rename(columns={"team_id": "opponent_team_id", "points": "opp_points"}),
        on=["contest_id", "opponent_team_id"]
    )["opp_points"]

    match_features = merged[[
        "contest_id", "team_id", "opponent_team_id", "date", "won", "sets",
        "hit_pct", "error_pct", "kills_per_set", "digs_per_set", "blocks_per_set",
        "aces_per_set", "assists_per_set", "points", "point_differential", "opponent_hit_pct",
    ]].rename(columns={"sets": "sets_played"})

    # Season aggregates (first pass, no SOS yet -- SOS needs everyone's win_pct first).
    season = match_features.groupby("team_id").agg(
        matches_played=("contest_id", "count"),
        wins=("won", "sum"),
        avg_hit_pct=("hit_pct", "mean"),
        avg_error_pct=("error_pct", "mean"),
        kills_per_set=("kills_per_set", "mean"),
        digs_per_set=("digs_per_set", "mean"),
        blocks_per_set=("blocks_per_set", "mean"),
        aces_per_set=("aces_per_set", "mean"),
    ).reset_index()
    season["losses"] = season["matches_played"] - season["wins"]
    season["win_pct"] = season["wins"] / season["matches_played"]

    win_pct_by_team = season.set_index("team_id")["win_pct"]
    sos = match_features.merge(
        win_pct_by_team.rename("opp_win_pct"), left_on="opponent_team_id", right_index=True
    ).groupby("team_id")["opp_win_pct"].mean().rename("strength_of_schedule")
    season = season.merge(sos, left_on="team_id", right_index=True, how="left")

    season = season[[
        "team_id", "matches_played", "wins", "losses", "win_pct", "avg_hit_pct",
        "avg_error_pct", "kills_per_set", "digs_per_set", "blocks_per_set",
        "aces_per_set", "strength_of_schedule",
    ]]

    conn.executescript("DROP TABLE IF EXISTS team_match_features; DROP TABLE IF EXISTS team_season_stats;")
    conn.executescript(SCHEMA_PATH.read_text())
    match_features.to_sql("team_match_features", conn, if_exists="append", index=False)
    season.to_sql("team_season_stats", conn, if_exists="append", index=False)
    conn.commit()

    print(f"{len(match_features)} team_match_features rows, {len(season)} team_season_stats rows")
    conn.close()


if __name__ == "__main__":
    build()
