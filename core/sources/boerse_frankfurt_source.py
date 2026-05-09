# Dateiname:     core/sources/boerse_frankfurt_source.py
# Version:       2026-05-09-stub
# Abhängigkeiten (intern): core.dividend_source
# Abhängigkeiten (extern): requests
"""
core/sources/boerse_frankfurt_source.py

Boerse Frankfurt / Deutsche Börse Datenfeed-Adapter.

STATUS: NICHT AKTIV — als Stub dokumentiert.

Untersuchungsergebnis 2026-05-09:
  Die API unter api.boerse-frankfurt.de erfordert interne IDs
  (notationId / instrumentId / listingId) statt ISIN/WKN/MIC.
  Alle getesteten öffentlichen Endpunkte liefern leere Antworten ({}):

    GET /v1/data/dividend_information?isin=DE0005557508&mic=XETR → {}
    GET /v1/data/key_data?isin=DE0005557508&mic=XETR             → {}
    GET /v1/search/instruments?searchTerms=DE0005557508           → {}
    GET /v1/search/instruments?searchTerms=DTE                    → {}
    GET /v1/data/instrument_information?isin=DE0005557508         → {}

  Der Zugang erfordert wahrscheinlich Session-Cookies oder proprietäre
  Auth-Header die der Browser automatisch setzt. Eine stabile
  Nutzung ohne Browser-Session-Reverse-Engineering ist nicht möglich.

Reaktivierung:
  Falls künftig ein offizieller API-Zugang verfügbar wird:
    1. ID-Auflösungsschritt implementieren (ISIN → notationId)
    2. Dividenden-Endpunkt mit notationId aufrufen
    3. BoerseFrankfurtSource aus _CASCADE_SOURCES in dividend_service.py
       eintragen
    4. Integrationstests mit responses-Mock ergänzen

Aktuelle Kaskade (dividend_service.py):
  1. DivvyDiary REST-API  (ISIN-nativ, API-Key erforderlich)
  2. yfinance             (Ticker-basiert, breite Abdeckung)
"""

from __future__ import annotations

from core.dividend_source import (
    DividendPayment,
    DividendSnapshot,
    DividendSource,
)


class BoerseFrankfurtSource(DividendSource):
    """
    Stub — nicht aktiv in der Produktions-Kaskade.
    Siehe Modul-Docstring für Hintergründe und Reaktivierungsanleitung.
    """

    @property
    def source_name(self) -> str:
        return "boerse_frankfurt"

    def fetch_snapshot(
        self,
        isin: str,
        ticker: str = "",
    ) -> DividendSnapshot | None:
        """Nicht implementiert — gibt immer None zurück."""
        return None

    def fetch_history(
        self,
        isin: str,
        ticker: str = "",
    ) -> list[DividendPayment]:
        """Nicht implementiert — gibt immer leere Liste zurück."""
        return []
