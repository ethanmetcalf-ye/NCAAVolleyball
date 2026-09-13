"""Project paths and season selection, shared by pipeline, dashboard, and analysis."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
REFERENCE_DIR = DATA_DIR / "reference"
PROCESSED_DIR = DATA_DIR / "processed"
DB_PATH = PROCESSED_DIR / "volleyball.db"

# Everything season-specific (calendar, expected row counts, known source
# anomalies) lives in data/reference/season_{SEASON}.json.
SEASON = "2025"
