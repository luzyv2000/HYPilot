# Dateiname:     ingestion/downloader.py
# Version:       2026-04-20
# Abhängigkeiten (intern): keine
# Abhängigkeiten (extern): requests
"""
ingestion/downloader.py

Lädt das Trade-Republic-Instrument-Universe-PDF herunter und prüft
via SHA-256-Hash, ob eine neue Version vorliegt.
Archiviert die bisherige Datei bei Änderung.
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# ── Konfiguration ────────────────────────────────────────────────────────────

PDF_URL: str = (
    "https://assets.traderepublic.com/assets/files/DE/"
    "Instrument_Universe_DE_de.pdf"
)

BASE_PATH: Path = Path("/home/luzy/workspace/openclaw-min")
RAW_PDF_DIR: Path = BASE_PATH / "data" / "raw_pdfs"
PDF_PATH: Path = RAW_PDF_DIR / "Instrument_Universe_DE_de.pdf"
HASH_PATH: Path = RAW_PDF_DIR / "Instrument_Universe_DE_de.hash"

_RETRY_COUNT: int = 3
_RETRY_DELAY_SEC: int = 5
_TIMEOUT_SEC: int = 30


# ── Interne Hilfsfunktionen ───────────────────────────────────────────────────

def _ensure_dirs() -> None:
    RAW_PDF_DIR.mkdir(parents=True, exist_ok=True)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_stored_hash() -> str | None:
    if not HASH_PATH.exists():
        return None
    return HASH_PATH.read_text(encoding="utf-8").strip() or None


def _save_hash(hash_value: str) -> None:
    HASH_PATH.write_text(hash_value, encoding="utf-8")


def _archive_current_pdf() -> None:
    """Benennt das aktuelle PDF mit Datumspräfix um."""
    if not PDF_PATH.exists():
        return
    timestamp = datetime.now().strftime("%Y-%m-%d")
    archive_path = RAW_PDF_DIR / f"{timestamp}_Instrument_Universe_DE_de.pdf"
    if archive_path.exists():
        # Selber Tag: altes Archiv überschreiben (kein Datenverlust, da Hash gleich)
        archive_path.unlink()
    PDF_PATH.rename(archive_path)
    logger.info("Alte PDF archiviert: %s", archive_path.name)


def _download_with_retry() -> bytes | None:
    """Führt bis zu _RETRY_COUNT Download-Versuche durch."""
    for attempt in range(1, _RETRY_COUNT + 1):
        try:
            response = requests.get(PDF_URL, timeout=_TIMEOUT_SEC)
            if response.status_code == 200:
                return response.content
            logger.warning(
                "HTTP %s beim Download (Versuch %d/%d)",
                response.status_code, attempt, _RETRY_COUNT,
            )
        except requests.RequestException as exc:
            logger.warning(
                "Download-Fehler Versuch %d/%d: %s",
                attempt, _RETRY_COUNT, exc,
            )
        if attempt < _RETRY_COUNT:
            time.sleep(_RETRY_DELAY_SEC)
    return None


# ── Öffentliche API ───────────────────────────────────────────────────────────

def run() -> bool:
    """
    Prüft auf neue PDF-Version und lädt sie bei Änderung herunter.

    Returns:
        True  — PDF vorhanden und verwendbar (neu oder unverändert)
        False — Download fehlgeschlagen UND kein lokales PDF vorhanden
    """
    _ensure_dirs()
    logger.info("Starte Download-Check: %s", PDF_URL)

    content = _download_with_retry()

    if content is None:
        if PDF_PATH.exists():
            logger.warning(
                "Download fehlgeschlagen — verwende vorhandenes PDF: %s",
                PDF_PATH,
            )
            return True
        logger.error("Download fehlgeschlagen und kein lokales PDF vorhanden.")
        return False

    new_hash = _sha256(content)
    old_hash = _load_stored_hash()

    if new_hash == old_hash:
        logger.info("PDF unverändert (Hash identisch) — kein Download nötig.")
        return True

    logger.info("Neue PDF-Version erkannt.")
    _archive_current_pdf()

    PDF_PATH.write_bytes(content)
    _save_hash(new_hash)
    logger.info("Neue PDF gespeichert: %s", PDF_PATH)
    return True


# ── CLI-Einstiegspunkt ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    sys.exit(0 if run() else 1)
