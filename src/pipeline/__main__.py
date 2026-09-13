"""Run the whole pipeline: raw JSON -> volleyball.db -> validation -> dashboard.

The database is built to a staging file and only replaces
data/processed/volleyball.db if every validation check passes, so a bad
build never overwrites a good database or regenerates the dashboard.

Run from repo root:
    source .venv/bin/activate
    python3 -m src.pipeline
"""

import os
import sys

from src.config import DB_PATH
from src.dashboard import build as dashboard
from src.pipeline import build, validate


def main() -> int:
    staging_path = DB_PATH.with_name(DB_PATH.stem + ".staging.db")
    build.build(staging_path)
    print()
    if validate.run(staging_path):
        print(f"\nValidation failed; left {DB_PATH.name} untouched (inspect {staging_path}).")
        return 1
    os.replace(staging_path, DB_PATH)
    print(f"\nPromoted {staging_path.name} -> {DB_PATH}\n")
    dashboard.build(DB_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
