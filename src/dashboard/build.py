"""Build the Phase 3 team-level dashboard: a self-contained HTML file.

Pulls standings/leaderboard and season-trend data out of
data/processed/volleyball.db, embeds it as JSON into src/dashboard/template.html,
and writes src/dashboard/dashboard.html. No server, no external data
fetches at view time (Chart.js loads from a CDN, everything else is
embedded).

Run from repo root, after src/pipeline/build.py and features.py:
    source .venv/bin/activate
    python3 -m src.dashboard.build
"""

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "processed" / "volleyball.db"
TEMPLATE_PATH = Path(__file__).parent / "template.html"
OUTPUT_PATH = Path(__file__).parent / "dashboard.html"

sys.path.insert(0, str(ROOT))
from src.pipeline.correlations import compute as compute_correlations  # noqa: E402


def fetch_data(conn: sqlite3.Connection) -> dict:
    conn.row_factory = sqlite3.Row

    teams = [dict(r) for r in conn.execute(
        "SELECT team_id, name, conference FROM teams WHERE is_power4=1 ORDER BY conference, name"
    )]

    standings = [dict(r) for r in conn.execute(
        "SELECT s.team_id, te.name, te.conference, s.matches_played, s.wins, s.losses, "
        "  s.win_pct, s.avg_hit_pct, s.avg_error_pct, s.kills_per_set, s.digs_per_set, "
        "  s.blocks_per_set, s.aces_per_set, s.strength_of_schedule "
        "FROM team_season_stats s JOIN teams te ON te.team_id = s.team_id "
        "WHERE te.is_power4 = 1 ORDER BY s.win_pct DESC"
    )]

    players = [dict(r) for r in conn.execute(
        "SELECT p.player_id, p.name, p.primary_position AS position, "
        "  te.team_id, te.name AS team_name, te.conference, "
        "  s.matches_played, s.sets_played, s.kills, s.errors, s.total_attacks, s.hit_pct, "
        "  s.assists, s.aces, s.service_errors, s.digs, "
        "  (s.block_solos + s.block_assists) AS blocks, s.points, "
        "  s.kills_per_set, s.digs_per_set, s.blocks_per_set, s.aces_per_set, "
        "  s.assists_per_set, s.points_per_set "
        "FROM player_season_stats s "
        "JOIN players p ON p.player_id = s.player_id "
        "JOIN teams te ON te.team_id = p.primary_team_id "
        "WHERE te.is_power4 = 1"
    )]

    trends = [dict(r) for r in conn.execute(
        "SELECT f.team_id, f.date, f.won, f.hit_pct, f.error_pct, f.kills_per_set, "
        "  f.digs_per_set, f.blocks_per_set, f.aces_per_set, f.point_differential, "
        "  opp.name AS opponent_name "
        "FROM team_match_features f "
        "JOIN teams opp ON opp.team_id = f.opponent_team_id "
        "WHERE f.team_id IN (SELECT team_id FROM teams WHERE is_power4 = 1) "
        "ORDER BY f.team_id, f.date"
    )]

    meta = conn.execute(
        "SELECT COUNT(*) n_matches, MIN(date) start_date, MAX(date) end_date FROM matches"
    ).fetchone()
    league_avg_hit_pct = conn.execute(
        "SELECT AVG(win_pct) w, AVG(avg_hit_pct) h FROM team_season_stats s "
        "JOIN teams te ON te.team_id = s.team_id WHERE te.is_power4 = 1"
    ).fetchone()

    correlations = compute_correlations(DB_PATH).to_dict(orient="records")

    return {
        "teams": teams,
        "standings": standings,
        "trends": trends,
        "players": players,
        "correlations": correlations,
        "meta": {
            "n_matches": meta["n_matches"],
            "start_date": meta["start_date"][:10],
            "end_date": meta["end_date"][:10],
            "n_teams": len(teams),
            "league_avg_hit_pct": league_avg_hit_pct["h"],
        },
    }


def build():
    conn = sqlite3.connect(DB_PATH)
    data = fetch_data(conn)
    conn.close()

    template = TEMPLATE_PATH.read_text()
    html = template.replace("/*__DASHBOARD_DATA__*/", json.dumps(data))
    OUTPUT_PATH.write_text(html)

    print(f"{len(data['teams'])} teams, {len(data['standings'])} standings rows, "
          f"{len(data['trends'])} trend rows, {len(data['players'])} players")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    build()
