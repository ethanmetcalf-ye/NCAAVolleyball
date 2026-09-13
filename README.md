# NCAA Women's Volleyball Stats

Interactive dashboard for NCAA Division I women's volleyball statistics, scoped to the Power 4 conferences (ACC, Big 12, Big Ten, SEC), 2025 season.

## Overview

This project demonstrates a complete data pipeline for analyzing NCAA Division I women's volleyball statistics:

1. **Data Collection** → Match data from stats.ncaa.org (scraper excluded; see Notes)
2. **Pipeline** → Normalizes raw data into a relational SQLite database
3. **Feature Engineering** → Computes advanced statistics (hit %, per-set metrics, strength of schedule, win prediction correlations)
4. **Dashboard** → Self-contained interactive HTML visualization

The pre-built database (`volleyball.db`) is included, so you can explore the dashboard immediately without running any pipeline steps.

## Quick Start

```bash
# Install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# View the dashboard
open src/dashboard/dashboard.html
```

That's it! The pre-built database is included, so you can explore the dashboard immediately.

## Architecture

```
src/
  pipeline/   # Normalization, aggregation, feature engineering
    build.py                 # Raw data → SQLite schema
    player_features.py       # Compute per-player season statistics
    features.py              # Compute per-team season statistics
    correlations.py          # Analyze stat correlations with win %
  dashboard/  # Interactive visualization
    build.py                 # Database → self-contained HTML
    template.html            # Chart.js dashboard template
    dashboard.html           # Generated output (open in browser)
data/
  processed/
    volleyball.db            # Pre-built SQLite database
  reference/                 # Team reference data
notebooks/                   # Exploratory analysis
tests/                       # Test suite
```

## Regenerating the Database

If you want to re-run the pipeline (requires raw match data):

```bash
source .venv/bin/activate
python3 -m src.pipeline.build            # Load raw JSON into database
python3 -m src.pipeline.player_features  # Compute player-level stats
python3 -m src.pipeline.features         # Compute team-level stats
python3 -m src.pipeline.correlations     # Analyze correlations
python3 -m src.dashboard.build           # Regenerate dashboard
```

## Notes

- Data was originally sourced from NCAA volleyball statistics via web scraping
- The scraper is excluded from this repo to respect NCAA terms of service
- The pre-built database (`data/processed/volleyball.db`) contains 2025 Power 4 volleyball season data
- The dashboard is a single self-contained HTML file (no server required)
