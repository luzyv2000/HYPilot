# Dateiname:     tests/conftest.py
# Version:       2026-04-22
# Abhängigkeiten (intern): db.init_db, core.dividend_source
# Abhängigkeiten (extern): pytest
"""
tests/conftest.py

Gemeinsame Fixtures für alle HYPilot-Tests.

Designprinzipien:
  - Alle DB-Tests laufen gegen In-Memory-SQLite → kein Zustand zwischen Tests
  - Keine Netzwerk-Calls in Unit-Tests (yfinance wird gemockt)
  - Fixture-Scope bewusst gewählt: function (default) für DB-Isolation
"""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Generator

import pytest

# Projektpfad damit imports funktionieren
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from db.init_db import init_database
from core.dividend_source import DividendPayment, DividendSnapshot


# ── Datenbank-Fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def in_memory_db() -> Generator[Path, None, None]:
    """
    Temporäre In-Memory-SQLite-DB mit vollständigem Schema.
    Jeder Test bekommt eine frische, leere Datenbank.

    Yields:
        Path zu ':memory:' — wird von Repository-Funktionen akzeptiert
        wenn sie db_path als Parameter nehmen.

    Hinweis: SQLite :memory: kann nicht als Path übergeben werden.
    Wir nutzen eine temporäre Datei in /tmp stattdessen.
    """
    import tempfile
    import os

    fd, path_str = tempfile.mkstemp(suffix=".db", prefix="hypilot_test_")
    os.close(fd)
    db_path = Path(path_str)

    try:
        init_database(db_path)
        yield db_path
    finally:
        db_path.unlink(missing_ok=True)


@pytest.fixture
def db_with_instruments(in_memory_db: Path) -> Path:
    """
    DB mit einer Handvoll Test-Instrumente vorbefüllt.
    Basis für Tests die Instrumente voraussetzen.
    """
    instruments = [
        ("Realty Income Corp",     "US7561091049", "A1J5SB"),
        ("iShares MSCI World ETF", "IE00B4L5Y983", None),
        ("Tesla Inc",              "US88160R1014", "A1CX3T"),
        ("Deutsche Telekom AG",    "DE0005557508", "555750"),
        ("Short Product XYZ",      "DE000SL0ABC1", None),  # wird gefiltert
    ]
    with sqlite3.connect(in_memory_db) as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO instruments (name, isin, wkn) VALUES (?,?,?)",
            instruments,
        )
        conn.commit()
    return in_memory_db


@pytest.fixture
def db_with_dividends(db_with_instruments: Path) -> Path:
    """
    DB mit Test-Dividendendaten für Realty Income.
    Basis für Scoring-Tests.
    """
    with sqlite3.connect(db_with_instruments) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO dividend_data
                (isin, yield_bps, frequency, last_amount_micro,
                 last_ex_date, currency, payout_ratio_bps, data_source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("US7561091049", 550, "monthly", 271000,
             "2026-03-31", "USD", 27500, "yfinance"),
        )
        conn.commit()
    return db_with_instruments


# ── Dividenden-Fixtures ───────────────────────────────────────────────────────

@pytest.fixture
def sample_snapshot() -> DividendSnapshot:
    """Standard-Snapshot für Realty Income (monatl. ~5.5%)."""
    return DividendSnapshot(
        isin="US7561091049",
        yield_bps=550,
        frequency="monthly",
        last_amount_micro=271_000,
        last_ex_date=date(2026, 3, 31),
        currency="USD",
        payout_ratio_bps=27_500,
        data_source="yfinance",
    )


@pytest.fixture
def high_yield_snapshot() -> DividendSnapshot:
    """Snapshot mit >10% Rendite — Kernziel von HYPilot."""
    return DividendSnapshot(
        isin="US1234567890",
        yield_bps=1250,
        frequency="monthly",
        last_amount_micro=500_000,
        last_ex_date=date(2026, 3, 31),
        currency="USD",
        payout_ratio_bps=6500,
        data_source="yfinance",
    )


@pytest.fixture
def sample_payments() -> list[DividendPayment]:
    """12 monatliche Zahlungen für Frequenz-Tests."""
    return [
        DividendPayment(
            isin="US7561091049",
            ex_date=date(2025, m, 15),
            amount_micro=268_000,
            currency="USD",
            data_source="yfinance",
        )
        for m in range(1, 13)
    ]
