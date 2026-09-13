"""Sanity-check the processed SQLite store.

Two kinds of checks, on purpose:
  - Structural invariants: hold for any season or scope (box-score
    arithmetic, set scores, referential integrity, view consistency). These
    should never need editing when data is added.
  - Dataset expectations: row counts pinned in
    data/reference/season_{SEASON}.json["expected_counts"]. These are
    regression guards for one specific dataset and *should* fail when the
    scope changes -- update the JSON deliberately when that happens.

Exits non-zero if any check fails.

Run from repo root:
    source .venv/bin/activate
    python3 -m src.pipeline.validate
"""

import json
import sqlite3
import sys
from pathlib import Path

from src import db
from src.config import DB_PATH, REFERENCE_DIR, SEASON

# Team totals must equal the sum of the team's player rows for these columns.
# Reception attempts/errors are excluded: the source attributes some of them
# to an unlisted "TEAM" line inconsistently, so they don't reconcile for ~25%
# of team-matches.
RECONCILED_COLUMNS = [
    "kills", "errors", "total_attacks", "assists", "aces", "service_errors", "digs",
    "block_solos", "block_assists", "block_errors", "ball_handling_errors",
]


def run(db_path: Path = DB_PATH, reference_dir: Path = REFERENCE_DIR, season: str = SEASON) -> list[str]:
    season_config = json.loads((reference_dir / f"season_{season}.json").read_text())
    conn = db.connect(db_path)
    conn.row_factory = sqlite3.Row
    issues = []

    def check(label, query, params=()):
        """Fail if the query returns any rows."""
        rows = conn.execute(query, params).fetchall()
        print(f"[{'FAIL' if rows else 'ok'}] {label}" + (f" ({len(rows)} rows)" if rows else ""))
        if rows:
            issues.append(label)
            for r in rows[:5]:
                print("   ", dict(r))

    def expect(label, actual, expected):
        ok = actual == expected
        print(f"[{'ok' if ok else 'FAIL'}] {label}: {actual}" + ("" if ok else f" (expected {expected})"))
        if not ok:
            issues.append(label)

    def scalar(query):
        return conn.execute(query).fetchone()[0]

    print("-- structural invariants")

    check("foreign key violations", "PRAGMA foreign_key_check")

    check("match without exactly 2 team_match_stats rows",
          "SELECT m.contest_id, COUNT(t.team_id) n FROM matches m "
          "LEFT JOIN team_match_stats t ON t.contest_id = m.contest_id "
          "GROUP BY m.contest_id HAVING n != 2")

    check("team_match_stats team not playing in that match",
          "SELECT t.contest_id, t.team_id FROM team_match_stats t JOIN matches m USING (contest_id) "
          "WHERE t.team_id NOT IN (m.home_team_id, m.away_team_id)")

    check("player_match_stats team not playing in that match",
          "SELECT p.contest_id, p.player_id FROM player_match_stats p JOIN matches m USING (contest_id) "
          "WHERE p.team_id NOT IN (m.home_team_id, m.away_team_id)")

    for table, key in [("team_match_stats", "team_id"), ("player_match_stats", "player_id")]:
        check(f"hit_pct arithmetic mismatch in {table}",
              f"SELECT contest_id, {key}, kills, errors, total_attacks, hit_pct FROM {table} "
              "WHERE total_attacks > 0 "
              "  AND ABS(hit_pct - (CAST(kills AS REAL) - errors) / total_attacks) > 0.001")
        check(f"points != kills + aces + block_solos + 0.5*block_assists in {table}",
              f"SELECT contest_id, {key}, points FROM {table} "
              "WHERE ABS(points - (kills + aces + block_solos + 0.5 * block_assists)) > 0.01")

    check("team totals don't reconcile with sum of player rows",
          "SELECT t.contest_id, t.team_id FROM team_match_stats t JOIN ("
          "  SELECT contest_id, team_id, "
          + ", ".join(f"SUM({c}) AS {c}" for c in RECONCILED_COLUMNS)
          + "  FROM player_match_stats GROUP BY contest_id, team_id) p USING (contest_id, team_id) "
          "WHERE " + " OR ".join(f"t.{c} != p.{c}" for c in RECONCILED_COLUMNS))

    check("team sets played != match num_sets",
          "SELECT t.contest_id, t.team_id FROM team_match_stats t JOIN matches m USING (contest_id) "
          "WHERE t.sets != m.num_sets")

    check("match sets_won doesn't sum to num_sets, or winner didn't reach 3",
          "SELECT contest_id FROM matches "
          "WHERE away_sets_won + home_sets_won != num_sets OR MAX(away_sets_won, home_sets_won) != 3")

    check("match_sets rows != num_sets, or set winners don't match sets_won",
          "SELECT m.contest_id FROM matches m JOIN match_sets s USING (contest_id) "
          "GROUP BY m.contest_id "
          "HAVING COUNT(*) != m.num_sets "
          "    OR SUM(s.home_points > s.away_points) != m.home_sets_won "
          "    OR SUM(s.away_points > s.home_points) != m.away_sets_won")

    # Allowlisted source errors are skipped. Passed as a JSON array so an
    # empty allowlist works: a `NOT IN (NULL)` placeholder evaluates to NULL
    # and would silently skip every row.
    known_bad_sets = list(season_config["known_anomalies"].get("illegal_set_scores", {}))
    check("illegal set score (sets 1-4 to 25, set 5 to 15, win by 2; overtime ends at +2)",
          "SELECT contest_id, set_number, away_points, home_points FROM match_sets "
          f"WHERE contest_id NOT IN (SELECT value FROM json_each(?)) AND ("
          "  ABS(home_points - away_points) < 2 "
          "  OR MAX(home_points, away_points) < CASE WHEN set_number = 5 THEN 15 ELSE 25 END "
          "  OR (MAX(home_points, away_points) > CASE WHEN set_number = 5 THEN 15 ELSE 25 END "
          "      AND ABS(home_points - away_points) != 2))",
          (json.dumps(known_bad_sets),))

    check("home or away team playing itself",
          "SELECT contest_id FROM matches WHERE home_team_id = away_team_id")

    check("Power4-hosted match with unknown site_type",
          "SELECT m.contest_id FROM matches m JOIN teams t ON t.team_id = m.home_team_id "
          "WHERE t.is_power4 = 1 AND m.site_type IS NULL")

    check("host_team_id not one of the two teams",
          "SELECT contest_id FROM matches WHERE host_team_id NOT IN (home_team_id, away_team_id)")

    check("conference_tournament phase on a non-conference match",
          "SELECT contest_id FROM matches WHERE season_phase = 'conference_tournament' AND is_conference_match = 0")

    check("is_conference_match inconsistent with teams.conference",
          "SELECT m.contest_id FROM matches m "
          "JOIN teams h ON h.team_id = m.home_team_id JOIN teams a ON a.team_id = m.away_team_id "
          "WHERE m.is_conference_match != COALESCE(h.is_power4 AND a.is_power4 AND h.conference = a.conference, 0)")

    check("players with a position but no position_group",
          "SELECT player_id, primary_position FROM players "
          "WHERE primary_position IS NOT NULL AND position_group IS NULL")

    check("team_match_features: not exactly one winner per match",
          "SELECT contest_id FROM team_match_features GROUP BY contest_id "
          "HAVING COUNT(*) != 2 OR SUM(won) != 1")

    check("team_season_stats: wins + losses != matches_played, or win_pct outside [0, 1]",
          "SELECT team_id FROM team_season_stats "
          "WHERE wins + losses != matches_played OR win_pct < 0 OR win_pct > 1")

    check("game_spine: home side isn't the host at a home-site match",
          "SELECT g.contest_id FROM game_spine g JOIN matches m USING (contest_id) "
          "WHERE g.site_type = 'home' AND m.host_team_id != g.home_team_id")

    check("game_spine: a team appears under 2 conferences",
          "SELECT team_id FROM ("
          "  SELECT home_team_id AS team_id, conference FROM game_spine "
          "  UNION SELECT away_team_id, conference FROM game_spine) "
          "GROUP BY team_id HAVING COUNT(DISTINCT conference) > 1")

    print(f"\n-- dataset expectations (season_{season}.json)")
    expected = season_config["expected_counts"]
    actual = {
        "teams": scalar("SELECT COUNT(*) FROM teams"),
        "power4_teams": scalar("SELECT COUNT(*) FROM teams WHERE is_power4 = 1"),
        "matches": scalar("SELECT COUNT(*) FROM matches"),
        "match_sets": scalar("SELECT COUNT(*) FROM match_sets"),
        "team_match_stats": scalar("SELECT COUNT(*) FROM team_match_stats"),
        "players": scalar("SELECT COUNT(*) FROM players"),
        "player_match_stats": scalar("SELECT COUNT(*) FROM player_match_stats"),
        "matches_by_season_phase": {r[0]: r[1] for r in conn.execute(
            "SELECT season_phase, COUNT(*) FROM matches GROUP BY 1 ORDER BY 1")},
        "matches_by_site_type": {(r[0] or "unknown"): r[1] for r in conn.execute(
            "SELECT site_type, COUNT(*) FROM matches GROUP BY 1 ORDER BY 1")},
        "game_spine": scalar("SELECT COUNT(*) FROM game_spine"),
        "game_spine_by_conference": {r[0]: r[1] for r in conn.execute(
            "SELECT conference, COUNT(*) FROM game_spine GROUP BY 1 ORDER BY 1")},
        # Winner of the season's last match (the championship final). Guards
        # the date parsing and season_phase logic end to end.
        "champion": scalar(
            "SELECT t.name FROM team_match_features f JOIN teams t USING (team_id) "
            "WHERE f.won = 1 AND f.season_phase = 'postseason' "
            "ORDER BY f.match_date DESC, f.contest_id DESC LIMIT 1"),
    }
    for key, value in actual.items():
        expect(key, value, expected.get(key))

    home_win_rate = scalar("SELECT AVG(home_won) FROM game_spine WHERE site_type = 'home'")
    if home_win_rate is not None:
        print(f"\n[info] game_spine home win rate at true home sites: {home_win_rate:.4f}")

    print(f"\n{'PASSED' if not issues else f'{len(issues)} CHECK(S) FAILED'}")
    conn.close()
    return issues


if __name__ == "__main__":
    sys.exit(1 if run() else 0)
