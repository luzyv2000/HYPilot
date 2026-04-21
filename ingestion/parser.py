# Dateiname:     ingestion/parser.py
# Version:       2026-04-20
# Abhängigkeiten (intern): keine
# Abhängigkeiten (extern): pdfplumber
"""
ingestion/parser.py

Extrahiert Instrument-Datensätze (Name, ISIN, WKN) aus dem
Trade-Republic-Instrument-Universe-PDF via pdfplumber.

Parsing-Strategie: ISIN als primärer Anker (Format: 2 Buchstaben +
10 alphanumerische Zeichen). WKN-Extraktion ist heuristisch und
liefert gelegentlich None — das ist für Phase 1 akzeptiert.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TypedDict

import pdfplumber

logger = logging.getLogger(__name__)

# ── Konfiguration ─────────────────────────────────────────────────────────────

PDF_PATH: Path = (
    Path("/home/luzy/workspace/openclaw-min")
    / "data"
    / "raw_pdfs"
    / "Instrument_Universe_DE_de.pdf"
)

ISIN_PATTERN: re.Pattern[str] = re.compile(r"\b[A-Z]{2}[A-Z0-9]{10}\b")
WKN_PATTERN: re.Pattern[str] = re.compile(r"\b[A-Z0-9]{6}\b")

_LOG_INTERVAL_PAGES: int = 20


# ── Typen ─────────────────────────────────────────────────────────────────────

class InstrumentRecord(TypedDict):
    name: str
    isin: str
    wkn: str | None


# ── Interne Hilfsfunktionen ───────────────────────────────────────────────────

def _extract_isin(line: str) -> str | None:
    match = ISIN_PATTERN.search(line)
    return match.group(0) if match else None


def _extract_wkn(line: str, isin: str) -> str | None:
    for candidate in WKN_PATTERN.findall(line):
        if candidate != isin:
            return candidate
    return None


def _clean_name(line: str, isin: str, wkn: str | None) -> str:
    name = line.replace(isin, "")
    if wkn:
        name = name.replace(wkn, "")
    name = name.replace('"', "").replace("'", "")
    name = re.sub(r"^[^A-Za-z0-9]+", "", name)
    name = re.sub(r"\s{2,}", " ", name)
    return name.strip()


_NAME_BLACKLIST: frozenset[str] = frozenset({"ETF", "Index", "Fund", "Swap"})


def _is_valid(name: str) -> bool:
    if len(name) < 3:
        return False
    if name in _NAME_BLACKLIST:
        return False
    return True


# ── Öffentliche API ───────────────────────────────────────────────────────────

def parse_pdf(pdf_path: Path = PDF_PATH) -> list[InstrumentRecord]:
    """
    Liest das TR-PDF und gibt eine Liste deduplizierter Instrument-
    Datensätze zurück.

    Args:
        pdf_path: Pfad zur PDF-Datei (Standard: PDF_PATH).

    Returns:
        Liste von InstrumentRecord-Dicts.

    Raises:
        FileNotFoundError: Wenn die PDF-Datei nicht existiert.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF nicht gefunden: {pdf_path}")

    instruments: list[InstrumentRecord] = []
    seen_isins: set[str] = set()

    logger.info("Starte PDF-Parsing: %s", pdf_path)

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text()
            if not text:
                continue

            for line in text.split("\n"):
                isin = _extract_isin(line)
                if not isin or isin in seen_isins:
                    continue

                wkn = _extract_wkn(line, isin)
                name = _clean_name(line, isin, wkn)

                if not _is_valid(name):
                    continue

                instruments.append(
                    InstrumentRecord(name=name, isin=isin, wkn=wkn)
                )
                seen_isins.add(isin)

            if page_num % _LOG_INTERVAL_PAGES == 0:
                logger.info(
                    "Seite %d/%d verarbeitet (%d Einträge bisher)",
                    page_num, total_pages, len(instruments),
                )

    logger.info(
        "Parsing abgeschlossen: %d eindeutige Einträge gefunden.",
        len(instruments),
    )
    return instruments


# ── CLI-Einstiegspunkt ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    data = parse_pdf()
    for item in data[:10]:
        print(item)
    sys.exit(0)