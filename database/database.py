"""SQLite crop database.

The catalog is static and read-only. On Render's free tier the filesystem is not persistent, so the
database file is treated as a disposable cache: it is rebuilt from crops_seed.json at startup (and
again on demand if the file or table is ever missing). Nothing here stores user data.
"""
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from database.seed_crops import seed_crops

DB_PATH = Path(os.getenv("HARVESTV_DB_PATH", Path(__file__).resolve().parent / "harvestv.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS crops (
    id                   TEXT PRIMARY KEY,            -- stable slug used in URLs, e.g. 'mung'
    name                 TEXT NOT NULL UNIQUE,        -- display name; rotation logic refers to crops by name
    emoji                TEXT,
    season               TEXT NOT NULL,               -- 'Summer' | 'Winter' | 'All Seasons' (single label, as in the frontend)
    description          TEXT,
    growing_duration     TEXT,
    temperature_range    TEXT,
    soil_moisture        TEXT,                        -- preferred soil moisture (label)
    soil_requirements    TEXT,
    nitrogen_requirement TEXT,
    fertilizer_notes     TEXT,
    water_requirement    TEXT,                        -- label, e.g. 'Moderate–Low'
    water_demand_score   REAL,                        -- numeric water demand used by the mock rotation logic
    pest_disease_notes   TEXT,
    drought_tolerance    TEXT,
    is_legume            INTEGER NOT NULL DEFAULT 0 CHECK (is_legume IN (0, 1)),
    preceding_crops      TEXT NOT NULL DEFAULT '[]',  -- JSON array of crop names
    following_crops      TEXT NOT NULL DEFAULT '[]',  -- JSON array of crop names
    display_order        INTEGER NOT NULL DEFAULT 0   -- keeps the order the website already shows
);
"""


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> int:
    """Create the table if needed and sync it with the seed file. Safe to call repeatedly."""
    with closing(get_connection()) as conn:
        conn.executescript(SCHEMA)
        return seed_crops(conn)


def _row_to_crop(row: sqlite3.Row) -> dict:
    crop = dict(row)
    crop.pop("display_order")
    crop["is_legume"] = bool(crop["is_legume"])
    crop["preceding_crops"] = json.loads(crop["preceding_crops"])
    crop["following_crops"] = json.loads(crop["following_crops"])
    return crop


def _query(sql: str, params: tuple = ()) -> list:
    """Run a read query. If the table is missing (e.g. file deleted), rebuild it once and retry."""
    for attempt in (1, 2):
        try:
            with closing(get_connection()) as conn:
                return conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            if attempt == 2:
                raise
            init_db()


def list_crops() -> list:
    return [_row_to_crop(r) for r in _query("SELECT * FROM crops ORDER BY display_order, name")]


def get_crop(crop_id: str):
    """Return one crop dict, or None if the id does not exist. Parameterized, so safe for any input."""
    rows = _query("SELECT * FROM crops WHERE id = ?", (crop_id,))
    return _row_to_crop(rows[0]) if rows else None
