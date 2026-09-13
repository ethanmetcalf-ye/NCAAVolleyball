"""What predicts winning a match? Pearson correlation of each team-match
stat against the match outcome (won: 0/1), ranked by |r|.

Formalizes the hit_pct-vs-win-rate pattern spotted during Phase 2
exploration into a full ranked comparison across stats. Prints a report;
also called by src/dashboard/build.py to feed the dashboard's insights
panel.

Run from repo root, after src/pipeline/build.py:
    source .venv/bin/activate
    python3 -m src.analysis.correlations
"""

from pathlib import Path

import pandas as pd

from src import db
from src.config import DB_PATH

STAT_LABELS = {
    "hit_pct": "Hitting %",
    "error_pct": "Error %",
    "kills_per_set": "Kills / Set",
    "digs_per_set": "Digs / Set",
    "blocks_per_set": "Blocks / Set",
    "aces_per_set": "Aces / Set",
    "assists_per_set": "Assists / Set",
    "point_differential": "Point Differential",
    "opponent_hit_pct": "Opponent Hitting %",
}


def compute(db_path: Path = DB_PATH) -> pd.DataFrame:
    conn = db.connect(db_path)
    df = pd.read_sql("SELECT * FROM team_match_features", conn)
    conn.close()

    rows = []
    for field, label in STAT_LABELS.items():
        r = df[field].corr(df["won"])
        rows.append({"stat": field, "label": label, "correlation": r})

    result = pd.DataFrame(rows).sort_values("correlation", key=lambda s: s.abs(), ascending=False)
    return result.reset_index(drop=True)


def report():
    result = compute()
    print("Correlation with match outcome (won=1/lost=0), ranked by |r|:\n")
    for _, row in result.iterrows():
        direction = "higher -> more likely to win" if row["correlation"] > 0 else "higher -> less likely to win"
        print(f"  {row['label']:22s} r = {row['correlation']:+.3f}   ({direction})")
    return result


if __name__ == "__main__":
    report()
