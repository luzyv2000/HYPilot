Fahrplan — priorisiert nach Anlageentscheidungs-Relevanz

Stufe 1: Stabiles Fundament (diese Woche)
S1.1 — _resolve_via_yfinance Präfix-Check ergänzen (30 Min)
Python:
def _resolve_via_yfinance(isin: str, db_path: Path = DB_PATH) -> str | None:
    if isin[:2].upper() in _ISIN_PREFIXES_SKIP_YF_DIRECT:
        logger.debug("yfinance übersprungen für Präfix %s", isin[:2])
        return None
    # ... Rest wie bisher

S1.2 — Zentrale config.py (45 Min)
Python:
# config.py
from pathlib import Path
import os
from dotenv import load_dotenv
load_dotenv()

DB_PATH = Path(os.getenv("HYPILOT_DB_PATH",
               "/home/luzy/workspace/openclaw-min/db/hypilot.db"))
OPENFIGI_API_KEY = os.getenv("OPENFIGI_API_KEY", "")

Alle Module importieren aus config statt je eigenen Konstanten zu deklarieren.

S1.3 — _validate_ticker Mock verbessern (15 Min)
In TestOpenFIGIMocked.test_successful_resolution:
Python:
with patch("core.ticker_resolver._validate_ticker",
           side_effect=lambda t, e=None: t):

S1.4 — bulk_ticker_import Minimal-Tests (1h)
Code:
tests/test_ingestion/test_bulk_ticker_import.py
  - test_batch_split_100(): 250 ISINs → 3 Batches (100+100+50)
  - test_priority_order(): US/CA vor DE/GB vor Rest
  - test_dry_run_no_writes(): --dry-run verändert keine DB

Stufe 2: Analyse-Engine absichern (nächste Woche)
S2.1 — tests/test_analysis/test_scorer.py — Das ist die wichtigste fehlende Komponente für ein Investitionswerkzeug:
Code:
- test_yield_bps_calculation(): 2,5% → 250 bps
- test_threshold_crossing_detected(): 900 bps → 1000 bps = Crossing
- test_18_month_rule_applies(): yield=0 + >18M keine Zahlung → skip
- test_score_ranking_order(): höherer Yield → höherer Score
- test_zero_yield_handling(): kein Division-by-Zero

S2.2 — tests/test_analysis/test_engine.py
Code:
- test_universe_scan_returns_list()
- test_filter_excludes_skip_until()
- test_results_sorted_by_score()

S2.3 — Logging-Audit (1h)
Alle Funktionen in ticker_resolver.py erhalten einheitliches Logging:
DEBUG: Cache-Hit, Skip-Entscheidungen
INFO: Erfolgreiches Mapping
WARNING: API-Fehler, RATE_LIMIT
ERROR: Unerwartete Exceptions

Stufe 3: Erster Produktionslauf (nach Stufe 1+2)
S3.1 — bulk_ticker_import --missing-only --limit 500
Testlauf mit 500 ISINs, Ergebnis auswerten:
Wie viele lösen sich via OpenFIGI auf?
Wie viele fallen durch zu yfinance?
Wie viele bleiben unresolvable?

S3.2 — Vollimport über Nacht
Bash:
nohup python ingestion/bulk_ticker_import.py \
    --missing-only \
    >> logs/bulk_import_$(date +%Y%m%d).log 2>&1 &

S3.3 — Qualitätsprüfung Ticker-Mappings
Nach dem Import:
SQL:
SELECT source, COUNT(*) FROM ticker_mapping GROUP BY source;
SELECT COUNT(*) FROM ticker_mapping WHERE source='unresolvable';
-- Welche ISINs blieben offen?
SELECT i.name, i.isin FROM instruments i
LEFT JOIN ticker_mapping tm ON i.isin = tm.isin
WHERE tm.isin IS NULL;

Stufe 4: HYPilot als Investitionswerkzeug (mittelfristig)
S4.1 — Dividenden-Datenpipeline validieren
Vor echten Anlageentscheidungen muss die Datenqualität geprüft sein:
Stichprobe: 20 bekannte Dividendenzahler manuell gegen Quelle verifizieren
Yield-Berechnung nachrechnen (bps → Prozentwert anzeigen)
S4.2 — GUI-Scoring-Anzeige
Aktuell zeigt die GUI Instrumente — aber der Score aus analysis/scorer.py muss sichtbar sein: Spalte mit Yield in %, Score, letztes Zahlungsdatum, nächste erwartete Zahlung.
S4.3 — Schwellwert-Konfiguration aus GUI
10% (1000 bps) als Hardcode ist keine gute Produktionslösung. Ein einfacher Settings-Dialog oder .env-Variable YIELD_THRESHOLD_BPS=1000.
S4.4 — Export-Funktion
Für Anlageentscheidungen ist ein CSV/Excel-Export der Top-N-Instrumente nach Score sinnvoller als ein GUI-Popup.