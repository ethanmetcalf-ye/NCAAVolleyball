"""Derive player_season_stats from player_match_stats.

hit_pct is computed weighted (sum(kills-errors)/sum(total_attacks)), not
as an average of each match's hit_pct, since attack volume varies a lot
match to match and a simple average would over-weight low-volume games.

Run from repo root, after src/pipeline/build.py:
    source .venv/bin/activate
    python3 -m src.pipeline.player_features
"""

import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "processed" / "volleyball.db"
SCHEMA_PATH = Path(__file__).parent / "player_features.sql"


def build(db_path: Path = DB_PATH):
    conn = sqlite3.connect(db_path)
    stats = pd.read_sql("SELECT * FROM player_match_stats", conn)

    agg = stats.groupby("player_id").agg(
        matches_played=("contest_id", "count"),
        sets_played=("sets", "sum"),
        kills=("kills", "sum"),
        errors=("errors", "sum"),
        total_attacks=("total_attacks", "sum"),
        assists=("assists", "sum"),
        aces=("aces", "sum"),
        service_errors=("service_errors", "sum"),
        digs=("digs", "sum"),
        block_solos=("block_solos", "sum"),
        block_assists=("block_assists", "sum"),
        points=("points", "sum"),
    ).reset_index()

    agg["hit_pct"] = (agg["kills"] - agg["errors"]) / agg["total_attacks"].replace(0, pd.NA)
    agg["kills_per_set"] = agg["kills"] / agg["sets_played"].replace(0, pd.NA)
    agg["digs_per_set"] = agg["digs"] / agg["sets_played"].replace(0, pd.NA)
    agg["blocks_per_set"] = (agg["block_solos"] + agg["block_assists"]) / agg["sets_played"].replace(0, pd.NA)
    agg["aces_per_set"] = agg["aces"] / agg["sets_played"].replace(0, pd.NA)
    agg["assists_per_set"] = agg["assists"] / agg["sets_played"].replace(0, pd.NA)
    agg["points_per_set"] = agg["points"] / agg["sets_played"].replace(0, pd.NA)

    cols = [
        "player_id", "matches_played", "sets_played", "kills", "errors", "total_attacks",
        "hit_pct", "assists", "aces", "service_errors", "digs", "block_solos", "block_assists",
        "points", "kills_per_set", "digs_per_set", "blocks_per_set", "aces_per_set",
        "assists_per_set", "points_per_set",
    ]
    agg = agg[cols]

    conn.executescript("DROP TABLE IF EXISTS player_season_stats;")
    conn.executescript(SCHEMA_PATH.read_text())
    agg.to_sql("player_season_stats", conn, if_exists="append", index=False)
    conn.commit()

    print(f"{len(agg)} player_season_stats rows")
    conn.close()


if __name__ == "__main__":
    build()
