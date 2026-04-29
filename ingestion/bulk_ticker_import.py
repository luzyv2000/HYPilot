# Dateiname:     ingestion/bulk_ticker_import.py
# Version:       2026-04-27-improved
# Abhängigkeiten (intern): core.ticker_resolver, db.dividend_repository
# Abhängigkeiten (extern): requests, python-dotenv
"""
ingestion/bulk_ticker_import.py

Einmaliger Vorab-Import aller ISIN→Ticker-Mappings via OpenFIGI Batch-API.

Verbesserungen (v2026-04-27):
  - Intelligente Validierung: Mainstream validiert, Exotisch ungültig ok
  - Exponential Backoff bei yfinance 500er Fehlern
  - Detailliertes Monitoring mit Empfehlungen

Ablauf:
  1. Alle ISINs ohne Ticker-Mapping aus DB laden
  2. OpenFIGI Batch-API (100 ISINs/Request) abfragen
  3. Ergebnisse regional intelligent validieren
  4. Valide Mappings in ticker_mapping speichern (2 Sources: openfigi, openfigi_unvalidated)
  5. Nicht gefundene ISINs via yfinance-Sweep (optional)

Nutzung:
  # Nur OpenFIGI (schnell, ~5-10 Min für 13.000 ISINs)
  python -m ingestion.bulk_ticker_import

  # OpenFIGI + yfinance-Sweep (langsam, vollständiger)
  python -m ingestion.bulk_ticker_import --yfinance-sweep

  # Nur ISINs ohne vorhandenes Mapping
  python -m ingestion.bulk_ticker_import --missing-only

  # Trockenlauf (kein Schreiben, nur Statistik)
  python -m ingestion.bulk_ticker_import --dry-run

Rate-Limits:
  Ohne API-Key: 25 Requests/Min → 0.5s Pause → ~1 Min pro 120 ISINs
  Mit API-Key:  250 Requests/Min → keine Pause nötig
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

_PROJECT = Path(__file__).parent.parent
if str(_PROJECT) not in sys.path:
    sys.path.insert(0, str(_PROJECT))

load_dotenv(dotenv_path=_PROJECT / ".env")

from core.ticker_resolver import (
    _apply_suffix,
    _get_preferred_exchanges,
    _select_best_figi,
    _store_mapping,
    _store_unresolvable,
    _validate_ticker_with_retry,
    _ISIN_PREFIXES_REQUIRE_YF_VALIDATION,
    UNRESOLVABLE_TTL_DAYS,
    DB_PATH,
)

logger = logging.getLogger(__name__)

# ── Konfiguration ─────────────────────────────────────────────────────────

_OPENFIGI_URL    = "https://api.openfigi.com/v3/mapping"
_OPENFIGI_APIKEY = os.getenv("OPENFIGI_API_KEY", "").strip()

# OpenFIGI erlaubt max. 100 ISINs pro Batch-Request
_BATCH_SIZE = 100

# Pause zwischen Batch-Requests (Sekunden)
# Ohne Key: 25 req/min → 2.5s; mit Key: 250 req/min → 0.25s
_REQUEST_PAUSE = 0.3 if _OPENFIGI_APIKEY else 2.5

# Pause zwischen yfinance-Calls im Sweep
_YF_PAUSE = 0.5


# ── DB-Abfragen ──────────────────────────────────────────────────────────

def _get_all_isins(db_path: Path = DB_PATH) -> list[str]:
    """Alle ISINs aus instruments."""
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT isin FROM instruments ORDER BY isin"
        ).fetchall()
    return [row[0] for row in rows]


def _get_isins_without_mapping(db_path: Path = DB_PATH) -> list[str]:
    """
    ISINs ohne gültiges Ticker-Mapping.
    Schließt 'unresolvable'-Einträge aus — die wurden bereits versucht.
    """
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT i.isin
            FROM instruments i
            LEFT JOIN ticker_mapping tm ON i.isin = tm.isin
            WHERE tm.isin IS NULL
               OR tm.source = 'unresolvable'
            ORDER BY
                CASE SUBSTR(i.isin, 1, 2)
                    WHEN 'US' THEN 1 WHEN 'CA' THEN 1
                    WHEN 'DE' THEN 2 WHEN 'GB' THEN 2
                    WHEN 'FR' THEN 2 WHEN 'CH' THEN 2
                    WHEN 'NL' THEN 2 WHEN 'SE' THEN 2
                    ELSE 3
                END ASC,
                i.isin ASC
            """
        ).fetchall()
    return [row[0] for row in rows]


def _count_mappings(db_path: Path = DB_PATH) -> dict[str, int]:
    """Statistik über vorhandene Mappings."""
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT source, COUNT(*) AS cnt
            FROM ticker_mapping
            GROUP BY source
            """
        ).fetchall()
    return {row[0]: row[1] for row in rows}


# ── OpenFIGI Batch ─────────────────────────────────────────────────────────

def _openfigi_batch(isins: list[str]) -> dict[str, dict | None]:
    """
    Fragt bis zu 100 ISINs in einem einzigen OpenFIGI-Request ab.

    Returns:
        Dict ISIN → bestes Ergebnis-Dict (oder None wenn nicht gefunden).
    """
    assert len(isins) <= _BATCH_SIZE, "Max. 100 ISINs pro Batch"

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if _OPENFIGI_APIKEY:
        headers["X-OPENFIGI-APIKEY"] = _OPENFIGI_APIKEY

    payload = [{"idType": "ID_ISIN", "idValue": isin} for isin in isins]

    try:
        response = requests.post(
            _OPENFIGI_URL,
            json=payload,
            headers=headers,
            timeout=30,
        )

        if response.status_code == 429:
            logger.warning("OpenFIGI Rate-Limit — warte 60s ...")
            time.sleep(60)
            return {isin: None for isin in isins}

        if response.status_code != 200:
            logger.warning("OpenFIGI HTTP %s", response.status_code)
            return {isin: None for isin in isins}

        data = response.json()

    except requests.RequestException as exc:
        logger.warning("OpenFIGI-Anfrage fehlgeschlagen: %s", exc)
        return {isin: None for isin in isins}

    results: dict[str, dict | None] = {}
    for isin, entry in zip(isins, data):
        if "warning" in entry or not entry.get("data"):
            results[isin] = None
            continue
        results[isin] = _select_best_figi(entry["data"], isin)

    return results


# ── Hauptlogik ──────────────────────────────────────────────────────────

def run_openfigi_import(
    isins: list[str],
    dry_run: bool = False,
    db_path: Path = DB_PATH,
) -> dict[str, int]:
    """
    Verarbeitet alle ISINs via OpenFIGI Batch-API mit intelligenter Validierung.

    Returns:
        {'found': N, 'not_found': N, 'validated': N, 'unvalidated': N, 'invalid': N}
    """
    stats = {
        "found": 0,
        "not_found": 0,
        "validated": 0,      # Validiert & gespeichert (source='openfigi')
        "unvalidated": 0,    # Unvalidiert aber gespeichert (source='openfigi_unvalidated')
        "invalid": 0,        # Validierung fehlgeschlagen, aber nicht exotisch genug
    }
    total = len(isins)

    logger.info(
        "OpenFIGI Batch-Import: %d ISINs in %d Batches à %d.",
        total,
        (total + _BATCH_SIZE - 1) // _BATCH_SIZE,
        _BATCH_SIZE,
    )
    if _OPENFIGI_APIKEY:
        logger.info("API-Key vorhanden — erhöhtes Rate-Limit aktiv.")
    else:
        logger.warning(
            "Kein API-Key — Rate-Limit 25 req/min, Pause %.1fs zwischen Batches.",
            _REQUEST_PAUSE,
        )

    for batch_start in range(0, total, _BATCH_SIZE):
        batch = isins[batch_start: batch_start + _BATCH_SIZE]
        batch_num = batch_start // _BATCH_SIZE + 1
        total_batches = (total + _BATCH_SIZE - 1) // _BATCH_SIZE

        logger.info(
            "Batch %d/%d (%d ISINs) ...",
            batch_num, total_batches, len(batch),
        )

        results = _openfigi_batch(batch)
        time.sleep(_REQUEST_PAUSE)

        for isin, best in results.items():
            if best is None:
                stats["not_found"] += 1
                continue

            stats["found"] += 1
            raw_ticker = best.get("ticker")
            exchange   = best.get("exchCode")

            if not raw_ticker:
                stats["not_found"] += 1
                continue

            isin_prefix = isin[:2].upper()

            # Validierung versuchen
            validated = _validate_ticker_with_retry(raw_ticker, exchange)
            
            if validated:
                # Erfolgreich validiert
                stats["validated"] += 1
                if not dry_run:
                    _store_mapping(
                        isin, validated,
                        source="openfigi",
                        exchange=exchange,
                        db_path=db_path,
                    )
                logger.debug("  openfigi (validiert): %s → %s", isin, validated)
            
            elif isin_prefix not in _ISIN_PREFIXES_REQUIRE_YF_VALIDATION:
                # Exotischer Markt: ohne yfinance-Validierung akzeptieren
                stats["unvalidated"] += 1
                if not dry_run:
                    _store_mapping(
                        isin, raw_ticker,
                        source="openfigi_unvalidated",
                        exchange=exchange,
                        db_path=db_path,
                    )
                logger.debug("  openfigi (unvalidiert): %s → %s (%s)", 
                           isin, raw_ticker, exchange)
            
            else:
                # Mainstream-Markt: Validierung erforderlich
                logger.debug(
                    "Ticker %s für %s nicht validiert (mainstream).",
                    raw_ticker, isin
                )
                stats["invalid"] += 1

        # Fortschritt alle 10 Batches
        if batch_num % 10 == 0 or batch_num == total_batches:
            logger.info(
                "Fortschritt: %d/%d ISINs | gefunden: %d | "
                "validiert: %d | unvalidiert: %d | ungültig: %d | "
                "nicht gefunden: %d",
                min(batch_start + _BATCH_SIZE, total), total,
                stats["found"], stats["validated"], stats["unvalidated"],
                stats["invalid"], stats["not_found"],
            )

    return stats


def run_yfinance_sweep(
    db_path: Path = DB_PATH,
    dry_run: bool = False,
) -> dict[str, int]:
    """
    Versucht alle noch nicht aufgelösten ISINs via yfinance direkt.
    Nur für US/CA-ISINs sinnvoll — andere werden schnell übersprungen.

    Returns:
        {'resolved': N, 'failed': N, 'skipped': N}
    """
    from core.ticker_resolver import (
        _ISIN_PREFIXES_SKIP_YF_DIRECT,
        _resolve_via_yfinance,
    )

    isins = _get_isins_without_mapping(db_path)
    stats = {"resolved": 0, "failed": 0, "skipped": 0}

    logger.info("yfinance-Sweep: %d ISINs ohne Mapping.", len(isins))

    for i, isin in enumerate(isins, 1):
        prefix = isin[:2].upper()
        if prefix in _ISIN_PREFIXES_SKIP_YF_DIRECT:
            stats["skipped"] += 1
            continue

        ticker = _resolve_via_yfinance(isin, db_path=db_path) if not dry_run else None
        if ticker:
            stats["resolved"] += 1
        else:
            stats["failed"] += 1

        time.sleep(_YF_PAUSE)

        if i % 100 == 0:
            logger.info(
                "yfinance-Sweep: %d/%d | resolved: %d | failed: %d | skipped: %d",
                i, len(isins),
                stats["resolved"], stats["failed"], stats["skipped"],
            )

    return stats


# ── CLI ────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Einmaliger Bulk-Import aller ISIN→Ticker-Mappings."
    )
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="Nur ISINs ohne vorhandenes Mapping verarbeiten (Standard: alle).",
    )
    parser.add_argument(
        "--yfinance-sweep",
        action="store_true",
        help="Nach OpenFIGI-Lauf yfinance-Sweep für verbleibende ISINs.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Kein Schreiben in DB — nur Statistik ausgeben.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max. ISINs verarbeiten (0 = alle). Für Tests.",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(
                _PROJECT / "logs" / "bulk_ticker_import.log",
                encoding="utf-8",
            ),
        ],
    )
    (_PROJECT / "logs").mkdir(exist_ok=True)

    args = _parse_args()

    # Vorher: aktueller Stand
    before = _count_mappings()
    logger.info("Mappings vor Import: %s", before)

    # ISINs laden
    if args.missing_only:
        isins = _get_isins_without_mapping()
        logger.info("%d ISINs ohne Mapping gefunden.", len(isins))
    else:
        isins = _get_all_isins()
        logger.info("%d ISINs gesamt.", len(isins))

        if args.limit:
        isins = isins[: args.limit]
        logger.info("Limitiert auf %d ISINs.", len(isins))

    total = len(isins)  # ← NEUE ZEILE HINZUFÜGEN!

    if args.dry_run:
        logger.warning("DRY-RUN aktiv — keine Datenbankänderungen.")

    # OpenFIGI Batch-Import
    logger.info("=" * 70)
    logger.info("PHASE 1: OpenFIGI Batch-Import (mit intelligenter Validierung)")
    logger.info("=" * 70)
    figi_stats = run_openfigi_import(isins, dry_run=args.dry_run)

    logger.info(
        "OpenFIGI abgeschlossen: %d gefunden, %d validiert, "
        "%d unvalidiert, %d ungültig, %d nicht gefunden.",
        figi_stats["found"], figi_stats["validated"], figi_stats["unvalidated"],
        figi_stats["invalid"], figi_stats["not_found"],
    )

    # Optional: yfinance-Sweep
    if args.yfinance_sweep:
        logger.info("=" * 70)
        logger.info("PHASE 2: yfinance-Sweep für verbleibende ISINs")
        logger.info("=" * 70)
        yf_stats = run_yfinance_sweep(dry_run=args.dry_run)
        logger.info(
            "yfinance-Sweep: %d aufgelöst, %d fehlgeschlagen, %d übersprungen.",
            yf_stats["resolved"], yf_stats["failed"], yf_stats["skipped"],
        )

    # Nachher: Differenz
    after = _count_mappings()
    logger.info("Mappings nach Import: %s", after)

    total_new = sum(after.values()) - sum(before.values())
    logger.info("Neu hinzugefügte Mappings: %d", total_new)

    # Detailliertes Monitoring
    logger.info("=" * 70)
    logger.info("DETAILLIERTE ANALYSE:")
    logger.info("=" * 70)
    if figi_stats["found"] > 0:
        val_rate = figi_stats["validated"] / figi_stats["found"] * 100
        unval_rate = figi_stats["unvalidated"] / figi_stats["found"] * 100
        inv_rate = figi_stats["invalid"] / figi_stats["found"] * 100
        logger.info("OpenFIGI-Hit-Rate:           %.1f%% (%d von %d)",
                   figi_stats["found"] / (total or 1) * 100,
                   figi_stats["found"], total or 1)
        logger.info("  ↳ Validiert (mainstream):   %.1f%% (%d gespeichert)",
                   val_rate, figi_stats["validated"])
        logger.info("  ↳ Unvalidiert (exotisch):   %.1f%% (%d gespeichert)",
                   unval_rate, figi_stats["unvalidated"])
        logger.info("  ↳ Ungültig (mainstream):    %.1f%% (%d verworfen)",
                   inv_rate, figi_stats["invalid"])
        
        if inv_rate > 30:
            logger.warning("  ⚠️  >30%% Validierungsverlust in Mainstream-Märkten!")
            logger.warning("      Evtl. yfinance-API Instabilität oder API-Key Probleme")
        else:
            logger.info("  ✅ Validierungsverlust im Normalbereich")
    
    logger.info("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
