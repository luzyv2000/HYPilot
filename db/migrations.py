# db/migrations.py (NEU)
# Dateiname: db/migrations.py
# Datum: 2026-05-06
# nachgeholt aus Copilot 01

from pathlib import Path
import sqlite3
from typing import Optional

MIGRATIONS = [
    # Migration 001: Initial Schema
    {
        "version": 1,
        "description": "Initial schema with all core tables",
        "up": """
        CREATE TABLE IF NOT EXISTS instruments (...);
        CREATE TABLE IF NOT EXISTS dividend_data (...);
        ...
        """,
        "down": """
        DROP TABLE IF EXISTS threshold_crossings;
        DROP TABLE IF EXISTS dividend_history;
        ...
        """,
    },
    # Migration 002: Add yield_bps_prev für Schwellwert-Tracking
    {
        "version": 2,
        "description": "Add yield_bps_prev and skip_until to dividend_data",
        "up": """
        ALTER TABLE dividend_data ADD COLUMN yield_bps_prev INTEGER;
        ALTER TABLE dividend_data ADD COLUMN skip_until DATE;
        """,
        "down": """
        -- Keine Rollback möglich in SQLite, aber versioned tracking vorhanden
        """,
    },
]

def init_migrations_table(conn: sqlite3.Connection) -> None:
    """Erstelle die schema_versions-Tabelle."""
    conn.execute("""
    CREATE TABLE IF NOT EXISTS schema_versions (
        version INTEGER PRIMARY KEY,
        description TEXT,
        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()

def get_current_version(conn: sqlite3.Connection) -> int:
    """Gibt die aktuelle Migrations-Version zurück."""
    cursor = conn.execute(
        "SELECT MAX(version) FROM schema_versions"
    )
    result = cursor.fetchone()[0]
    return result or 0

def apply_migrations(db_path: Path) -> None:
    """Wendet alle ausstehenden Migrationen an."""
    with sqlite3.connect(db_path) as conn:
        init_migrations_table(conn)
        current_version = get_current_version(conn)
        
        for migration in MIGRATIONS:
            if migration["version"] > current_version:
                logger.info(
                    f"Applying migration {migration['version']}: "
                    f"{migration['description']}"
                )
                conn.executescript(migration["up"])
                conn.execute(
                    "INSERT INTO schema_versions (version, description) "
                    "VALUES (?, ?)",
                    (migration["version"], migration["description"])
                )
                conn.commit()