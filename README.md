# NCAA Women's Volleyball Stats

Interactive dashboard for NCAA Division I women's volleyball statistics, scoped to the Power 4 conferences (ACC, Big 12, Big Ten, SEC), 2025 season.

## Overview

This project demonstrates a complete data pipeline for analyzing NCAA Division I women's volleyball statistics:

1. **Data Collection** → Match box scores from stats.ncaa.org (scraper excluded; see Notes)
2. **Pipeline** → Normalizes raw data into a relational SQLite database, with derived stats defined as SQL views
3. **Validation** → Structural invariants plus pinned dataset expectations; a failing build never replaces the database
4. **Dashboard** → Self-contained interactive HTML visualization

The pre-built database (`volleyball.db`) and dashboard are included, so you can explore immediately without running any pipeline steps.

## Quick Start

```bash
# View the dashboard
open src/dashboard/dashboard.html
```

To query the data, open `data/processed/volleyball.db` in any SQLite tool. See [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md) for every table and view.

## Architecture

```
docs/
  DATA_DICTIONARY.md               # Table/view reference for volleyball.db
src/
  config.py                  # Paths and season selection
  db.py                      # SQLite connection helper (foreign keys on)
  pipeline/
    __main__.py              # `python3 -m src.pipeline`: build -> validate -> dashboard
    build.py                 # Raw JSON -> raw tables (+ site type, season phase)
    schema.sql               # Raw tables
    views.sql                # Derived views: team/player season stats, game_spine, ...
    validate.py              # Invariants + dataset expectations; exits non-zero on failure
  analysis/
    correlations.py          # Stat-vs-outcome correlations (feeds the dashboard)
  dashboard/
    build.py                 # Database -> self-contained HTML
    template.html            # Chart.js dashboard template
    dashboard.html           # Generated output (open in browser)
  modeling/                  # Match-prediction work -- early stage
tests/                       # pytest suite on synthetic raw data
data/
  processed/volleyball.db    # Pre-built SQLite database
  reference/
    power4_teams.json        # Power 4 teams, conferences, curated home venues
    season_2025.json         # Season calendar, expected counts, known source anomalies
```

## Rebuilding

Requires Python 3.12+ and the raw match JSON in `data/raw/` (not included; see Notes).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

python3 -m src.pipeline      # build + validate + regenerate dashboard (~2s)
python3 -m pytest            # tests (no raw data needed)
```

The pipeline builds to a staging file and only replaces `volleyball.db` (and regenerates the dashboard) if every validation check passes. Individual steps can still be run on their own: `python3 -m src.pipeline.build`, `python3 -m src.pipeline.validate`, `python3 -m src.dashboard.build`.

## Notes

- Data was originally sourced from NCAA volleyball statistics via web scraping.
- The scraper and the raw scraped files are excluded from this repo to respect NCAA terms of service.
- The pre-built database contains 2025 Power 4 volleyball season data: 1,273 matches, 282 teams (67 Power 4), 3,748 players.
- The dashboard is a single self-contained HTML file (no server required).
