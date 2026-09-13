"""Build the team-level dashboard: a self-contained HTML file.

Pulls standings/leaderboard and season-trend data out of
data/processed/volleyball.db, embeds it as JSON into src/dashboard/template.html,
and writes src/dashboard/dashboard.html. No server, no external data
fetches at view time (Chart.js loads from a CDN, everything else is
embedded).

Run from repo root, after src/pipeline/build.py:
    source .venv/bin/activate
    python3 -m src.dashboard.build
"""

import json
import sqlite3
from pathlib import Path

from src import db
from src.analysis.correlations import compute as compute_correlations
from src.config import DB_PATH

TEMPLATE_PATH = Path(__file__).parent / "template.html"
OUTPUT_PATH = Path(__file__).parent / "dashboard.html"


def fetch_data(conn: sqlite3.Connection, db_path: Path) -> dict:
    conn.row_factory = sqlite3.Row

    teams = [dict(r) for r in conn.execute(
        "SELECT team_id, name, conference FROM teams WHERE is_power4 = 1 ORDER BY conference, name"
    )]

    # Aliases keep the template's field names; the template is reworked in the dashboard phase.
    standings = [dict(r) for r in conn.execute(
        "SELECT team_id, name, conference, matches_played, wins, losses, win_pct, "
        "  hit_pct AS avg_hit_pct, error_pct AS avg_error_pct, kills_per_set, digs_per_set, "
        "  blocks_per_set, aces_per_set, strength_of_schedule "
        "FROM team_season_stats WHERE is_power4 = 1 ORDER BY win_pct DESC"
    )]

    players = [dict(r) for r in conn.execute(
        "SELECT player_id, name, position, team_id, team_name, conference, "
        "  matches_played, sets_played, kills, errors, total_attacks, hit_pct, "
        "  assists, aces, service_errors, digs, blocks, points, "
        "  kills_per_set, digs_per_set, blocks_per_set, aces_per_set, "
        "  assists_per_set, points_per_set "
        "FROM player_season_stats WHERE is_power4 = 1"
    )]

    trends = [dict(r) for r in conn.execute(
        "SELECT f.team_id, f.match_date AS date, f.won, f.hit_pct, f.error_pct, f.kills_per_set, "
        "  f.digs_per_set, f.blocks_per_set, f.aces_per_set, f.point_differential, "
        "  opp.name AS opponent_name "
        "FROM team_match_features f "
        "JOIN teams t ON t.team_id = f.team_id AND t.is_power4 = 1 "
        "JOIN teams opp ON opp.team_id = f.opponent_team_id "
        "ORDER BY f.team_id, f.match_date, f.contest_id"
    )]

    meta = conn.execute(
        "SELECT COUNT(*) n_matches, MIN(match_date) start_date, MAX(match_date) end_date FROM matches"
    ).fetchone()
    league_avg_hit_pct = conn.execute(
        "SELECT AVG(hit_pct) FROM team_season_stats WHERE is_power4 = 1"
    ).fetchone()[0]

    correlations = compute_correlations(db_path).to_dict(orient="records")

    return {
        "teams": teams,
        "standings": standings,
        "trends": trends,
        "players": players,
        "correlations": correlations,
        "meta": {
            "n_matches": meta["n_matches"],
            "start_date": meta["start_date"],
            "end_date": meta["end_date"],
            "n_teams": len(teams),
            "league_avg_hit_pct": league_avg_hit_pct,
        },
    }


def build(db_path: Path = DB_PATH, output_path: Path = OUTPUT_PATH):
    conn = db.connect(db_path)
    data = fetch_data(conn, db_path)
    conn.close()

    template = TEMPLATE_PATH.read_text()
    html = template.replace("/*__DASHBOARD_DATA__*/", json.dumps(data))
    output_path.write_text(html)

    print(f"{len(data['teams'])} teams, {len(data['standings'])} standings rows, "
          f"{len(data['trends'])} trend rows, {len(data['players'])} players")
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    build()
