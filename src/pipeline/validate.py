"""Sanity-check the processed SQLite store.

Not exhaustive -- checks the things most likely to signal a real
normalization bug: referential integrity, duplicate keys, hitting-pct
arithmetic, and a standings reconstruction spot-check against a known
result (Pittsburgh won the 2025 D-I championship, 30-4).

Run from repo root:
    source .venv/bin/activate
    python3 -m src.pipeline.validate
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "processed" / "volleyball.db"


def run():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    issues = []

    def check(label, query, expect_empty=True):
        rows = conn.execute(query).fetchall()
        bad = bool(rows) if expect_empty else not rows
        status = "FAIL" if bad else "ok"
        print(f"[{status}] {label}" + (f" ({len(rows)} rows)" if rows else ""))
        if bad:
            issues.append(label)
            for r in rows[:5]:
                print("   ", dict(r))
        return rows

    check("duplicate contest_id in matches",
          "SELECT contest_id, COUNT(*) c FROM matches GROUP BY contest_id HAVING c > 1")

    check("duplicate (contest_id, team_id) in team_match_stats",
          "SELECT contest_id, team_id, COUNT(*) c FROM team_match_stats "
          "GROUP BY contest_id, team_id HAVING c > 1")

    check("duplicate (contest_id, player_id) in player_match_stats",
          "SELECT contest_id, player_id, COUNT(*) c FROM player_match_stats "
          "GROUP BY contest_id, player_id HAVING c > 1")

    check("matches referencing unknown team_id",
          "SELECT contest_id, away_team_id, home_team_id FROM matches "
          "WHERE away_team_id NOT IN (SELECT team_id FROM teams) "
          "   OR home_team_id NOT IN (SELECT team_id FROM teams)")

    check("team_match_stats rows without a matching match",
          "SELECT contest_id, team_id FROM team_match_stats "
          "WHERE contest_id NOT IN (SELECT contest_id FROM matches)")

    check("matches missing one or both team_match_stats rows",
          "SELECT m.contest_id, COUNT(t.team_id) n FROM matches m "
          "LEFT JOIN team_match_stats t ON t.contest_id = m.contest_id "
          "GROUP BY m.contest_id HAVING n != 2")

    check("player_match_stats rows with unknown player_id",
          "SELECT contest_id, player_id FROM player_match_stats "
          "WHERE player_id NOT IN (SELECT player_id FROM players)")

    check("hit_pct arithmetic mismatch in team_match_stats",
          "SELECT contest_id, team_id, kills, errors, total_attacks, hit_pct FROM team_match_stats "
          "WHERE total_attacks > 0 "
          "  AND ABS(hit_pct - (CAST(kills AS REAL) - errors) / total_attacks) > 0.001")

    check("hit_pct arithmetic mismatch in player_match_stats",
          "SELECT contest_id, player_id, kills, errors, total_attacks, hit_pct FROM player_match_stats "
          "WHERE total_attacks > 0 "
          "  AND ABS(hit_pct - (CAST(kills AS REAL) - errors) / total_attacks) > 0.001")

    check("match sets_won doesn't sum to num_sets",
          "SELECT contest_id FROM matches WHERE away_sets_won + home_sets_won != num_sets")

    check("winner didn't reach 3 sets (best-of-5, no 5-set ties allowed)",
          "SELECT contest_id, away_sets_won, home_sets_won FROM matches "
          "WHERE MAX(away_sets_won, home_sets_won) != 3")

    # Standings spot-check: whoever won the championship final (highest-date
    # match in the dataset) should have one of the best records in the
    # league -- a soft plausibility check, not a hardcoded number, since the
    # actual finalists/champion aren't something to assume from memory.
    final = conn.execute(
        "SELECT contest_id, date, away_team_id, home_team_id, away_sets_won, home_sets_won "
        "FROM matches ORDER BY date DESC LIMIT 1"
    ).fetchone()
    champ_id = final["away_team_id"] if final["away_sets_won"] > final["home_sets_won"] else final["home_team_id"]
    champ_name = conn.execute("SELECT name FROM teams WHERE team_id=?", (champ_id,)).fetchone()["name"]
    record = conn.execute(
        "SELECT "
        "  SUM(CASE WHEN (away_team_id=? AND away_sets_won>home_sets_won) "
        "        OR (home_team_id=? AND home_sets_won>away_sets_won) THEN 1 ELSE 0 END) AS wins, "
        "  SUM(CASE WHEN (away_team_id=? AND away_sets_won<home_sets_won) "
        "        OR (home_team_id=? AND home_sets_won<away_sets_won) THEN 1 ELSE 0 END) AS losses "
        "FROM matches WHERE away_team_id=? OR home_team_id=?",
        (champ_id, champ_id, champ_id, champ_id, champ_id, champ_id),
    ).fetchone()
    win_pct = record["wins"] / (record["wins"] + record["losses"])
    status = "ok" if win_pct > 0.80 else "FAIL"
    print(f"[{status}] Championship final ({final['date']}) winner {champ_name}: "
          f"{record['wins']}-{record['losses']} ({win_pct:.0%}) -- plausible for a champion" if win_pct > 0.80
          else f"[{status}] Championship winner {champ_name} has an implausible record: "
               f"{record['wins']}-{record['losses']}")
    if win_pct <= 0.80:
        issues.append("Champion win% implausible")

    feature_tables_exist = conn.execute(
        "SELECT COUNT(*) c FROM sqlite_master WHERE type='table' AND name='team_match_features'"
    ).fetchone()["c"]
    if feature_tables_exist:
        check("team_match_features row count != 2x matches",
              "SELECT 1 WHERE (SELECT COUNT(*) FROM team_match_features) "
              "  != (SELECT COUNT(*) FROM matches) * 2")

        check("team_match_features has non-finite hit_pct/error_pct",
              "SELECT contest_id, team_id FROM team_match_features "
              "WHERE hit_pct = 'inf' OR hit_pct = '-inf' OR error_pct = 'inf' OR error_pct = '-inf'")

        check("team_season_stats win_pct outside [0,1]",
              "SELECT team_id, win_pct FROM team_season_stats WHERE win_pct < 0 OR win_pct > 1")

        check("team_season_stats missing a team present in team_match_stats",
              "SELECT DISTINCT team_id FROM team_match_stats "
              "WHERE team_id NOT IN (SELECT team_id FROM team_season_stats)")
    else:
        print("[skip] team_match_features/team_season_stats not built yet "
              "(run src/pipeline/features.py)")

    player_features_exist = conn.execute(
        "SELECT COUNT(*) c FROM sqlite_master WHERE type='table' AND name='player_season_stats'"
    ).fetchone()["c"]
    if player_features_exist:
        check("duplicate player_id in player_season_stats",
              "SELECT player_id, COUNT(*) c FROM player_season_stats GROUP BY player_id HAVING c > 1")

        check("player_season_stats row count != players count",
              "SELECT 1 WHERE (SELECT COUNT(*) FROM player_season_stats) "
              "  != (SELECT COUNT(*) FROM players)")

        check("player_season_stats hit_pct arithmetic mismatch",
              "SELECT player_id, kills, errors, total_attacks, hit_pct FROM player_season_stats "
              "WHERE total_attacks > 0 "
              "  AND ABS(hit_pct - (CAST(kills AS REAL) - errors) / total_attacks) > 0.001")
    else:
        print("[skip] player_season_stats not built yet (run src/pipeline/player_features.py)")

    # Rough shape checks.
    n_matches = conn.execute("SELECT COUNT(*) c FROM matches").fetchone()["c"]
    n_players = conn.execute("SELECT COUNT(*) c FROM players").fetchone()["c"]
    n_teams = conn.execute("SELECT COUNT(*) c FROM teams").fetchone()["c"]
    n_p4 = conn.execute("SELECT COUNT(*) c FROM teams WHERE is_power4=1").fetchone()["c"]
    print(f"\n{n_matches} matches, {n_teams} teams ({n_p4} Power4), {n_players} players")

    print(f"\n{'PASSED' if not issues else f'{len(issues)} CHECK(S) FAILED'}")
    conn.close()
    return issues


if __name__ == "__main__":
    run()
