"""Loads the committed crop catalog (crops_seed.json) into SQLite.

crops_seed.json is the single source of truth for crop data. Running the seed is safe to repeat:
rows are upserted by id (no duplicates) and rows no longer in the seed file are removed.
Manual run:  python -m database.seed_crops
"""
import json
import sqlite3
from pathlib import Path

SEED_PATH = Path(__file__).resolve().parent / "crops_seed.json"

# Column names are fixed constants (never user input), so building the SQL text from them is safe.
COLUMNS = ("id", "name", "emoji", "season", "description", "growing_duration", "temperature_range",
           "soil_moisture", "soil_requirements", "nitrogen_requirement", "fertilizer_notes",
           "water_requirement", "water_demand_score", "pest_disease_notes", "drought_tolerance",
           "is_legume", "preceding_crops", "following_crops", "display_order")


def load_seed() -> list:
    with open(SEED_PATH, encoding="utf-8") as f:
        crops = json.load(f)
    ids = [c["id"] for c in crops]
    if len(ids) != len(set(ids)):
        raise ValueError("crops_seed.json contains duplicate crop ids")
    return crops


def seed_crops(conn: sqlite3.Connection) -> int:
    """Make the crops table match the seed file. Returns the number of crops."""
    crops = load_seed()
    upsert = (f"INSERT INTO crops ({', '.join(COLUMNS)}) VALUES ({', '.join('?' * len(COLUMNS))}) "
              "ON CONFLICT(id) DO UPDATE SET " + ", ".join(f"{c}=excluded.{c}" for c in COLUMNS[1:]))
    rows = [tuple(json.dumps(c[k]) if k in ("preceding_crops", "following_crops") else
                  int(c[k]) if k == "is_legume" else c.get(k) for k in COLUMNS) for c in crops]
    with conn:  # one transaction: all or nothing
        conn.execute(f"DELETE FROM crops WHERE id NOT IN ({', '.join('?' * len(crops))})", [c["id"] for c in crops])
        conn.executemany(upsert, rows)
    return len(crops)


if __name__ == "__main__":
    from database.database import init_db
    print(f"Seeded {init_db()} crops.")
