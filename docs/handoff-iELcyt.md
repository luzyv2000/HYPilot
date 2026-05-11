# Session Handoff — HYPilot

> Persistente Übergabedatei. Pfad: `docs/handoff-iELcyt.md`
> Nicht löschen. Inkrementell ergänzen. Vor jeder Änderung vollständig lesen.

---

## Current Objective

HYPilot ist ein dividenden-fokussiertes Wertpapier-Screening-Desktop-Tool
(CustomTkinter, SQLite, Python 3.12) auf einem NucBox K8 Plus (Ubuntu 24.04).
Aktuelles Ziel: Produktiven Betrieb stabilisieren, Datenqualität sichern,
Test-Suite vollständig halten.

---

## Current State

**Stand: 2026-05-10 (Sitzungsende)**

- 13.568 Instrumente im TR-Universum
- 12.486 ISINs mit Dividendendaten (92 % Abdeckung)
- 5.383 ISINs mit yield_bps > 0
- 283 High-Yield-Kandidaten >= 10 % (nach Plausibilitäts-Bereinigung)
- Quellen-Verteilung: yfinance 9.278 | divvydiary 3.410
- 13.339 Ticker-Mappings (openfigi 10.955 | yfinance 1.413 | openfigi_unvalidated 874 | unresolvable 97)
- systemd-Timer aktiv: 08:00 + 13:00, _TOTAL_PER_RUN = 3500
- CI: GitHub Actions grün, Node.js 24 aktiviert
- Test-Suite: 242 Tests, alle grün (unit + integration)

---

## Decisions Made

| Datum | Entscheidung | Begründung |
|-------|-------------|------------|
| 2026-05-08 | CTkToplevel Timing-Fix via after(20)/after(50) | grab_set() vor Window-Manager-Mapping fuehrte zu leerem Fenster |
| 2026-05-08 | _TOTAL_PER_RUN 500 -> 3500 | Nur 15 % des faelligen Universums wurde abgedeckt |
| 2026-05-08 | Multi-Source-Kaskade: DivvyDiary -> yfinance | boerse-frankfurt.de erfordert interne IDs, kein oeffentlicher Zugang |
| 2026-05-09 | boerse-frankfurt als Stub behalten | Reaktivierung moeglich sobald offizieller API-Zugang verfuegbar |
| 2026-05-09 | ticker-Parameter in DividendSource optional (= "") | ISIN-native Quellen (DivvyDiary) benoetigen keinen Ticker |
| 2026-05-09 | _CASCADE_SOURCES-Liste als zentraler Erweiterungspunkt | Neue Quelle = 1 Zeile, kein Umbau der Orchestrierungslogik |
| 2026-05-10 | Plausibilitaets-Cap: yield_bps > 5000 (50 %) -> verwerfen | DivvyDiary liefert Sonderausschuettungen als Rendite (Leo Lithium 681 %) |
| 2026-05-10 | Bereinigung bestehender Ausreisser: yield_bps = NULL, skip_until = +7d | 170 Eintraege bereinigt, werden beim naechsten Lauf neu abgefragt |
| 2026-05-10 | CI: FORCE_JAVASCRIPT_ACTIONS_TO_NODE24 + Actions auf v4/v5 | Node.js 20 deprecated ab Juni 2026 |

---

## Open Problems

| Prioritaet | Problem | Status |
|-----------|---------|--------|
| Mittel | DIVVYDIARY_API_KEY in .env eintragen | Offen -- ohne Key wird DivvyDiary uebersprungen |
| Niedrig | boerse_frankfurt_source.py -- ID-Aufloesung unbekannt | Stub, Reaktivierung erfordert offiziellen Zugang |
| Niedrig | migrations.py -- unfertiger Stub ohne gueltiges SQL | Nicht aktiv eingebunden |

---

## Next Recommended Actions

1. DIVVYDIARY_API_KEY in .env eintragen und ersten Batch-Lauf beobachten:
   sqlite3 db/hypilot.db "SELECT data_source, COUNT(*) FROM dividend_data GROUP BY data_source"

2. Ersten vollstaendigen Auto-Lauf mit _TOTAL_PER_RUN = 3500 beobachten.

3. Datenqualitaets-Monitoring nach jedem Auto-Lauf:
   sqlite3 db/hypilot.db "SELECT COUNT(*) FROM dividend_data WHERE yield_bps > 5000"

4. Analyse-Tab implementieren (aktuell Platzhalter in gui/app.py):
   Scoring-Verteilung, Top-Movers, Threshold-Crossing-Historie.

5. Watchlist-Tab implementieren (aktuell Platzhalter):
   Persistente ISIN-Liste mit manuellem Tracking.

---

## Relevant Artifacts

| Datei | Rolle |
|-------|-------|
| core/dividend_service.py | Kaskaden-Orchestrator, Plausibilitaets-Cap |
| core/sources/divvydiary_source.py | DivvyDiary REST-Adapter (aktiv) |
| core/sources/boerse_frankfurt_source.py | Stub -- inaktiv, dokumentiert |
| core/sources/yfinance_source.py | yfinance-Adapter (Fallback) |
| core/ticker_resolver.py | ISIN -> Ticker, drei Stufen (DB -> OpenFIGI -> yfinance) |
| db/dividend_repository.py | Einzige Schreibschicht auf dividend_data / threshold_crossings |
| db/init_db.py | Schema + Migrationen, idempotent |
| gui/app.py | Hauptfenster, Startup-Checks, Tab-Verwaltung |
| gui/tabs/universe_tab.py | TR-Universum-Tab mit Score-Spalte + Batch-Update |
| gui/tabs/high_yield_tab.py | High-Yield-Tab >= 10 %, CSV-Export |
| gui/widgets/score_detail_panel.py | 4 Teilscore-Balken bei Selektion |
| gui/widgets/threshold_crossing_popup.py | Startup-Popup fuer ungesehene Crossings |
| gui/widgets/name_edit_dialog.py | Doppelklick-Dialog, Timing-Fix 2026-05-08 |
| ingestion/auto_dividend_update.py | systemd-Einstiegspunkt, 3500 ISINs/Lauf |
| .github/workflows/tests.yml | CI, Node.js 24, unit + integration |

---

## Risks / Caveats

- DivvyDiary Rate-Limit (Free Tier ~100 Req/Tag): Bei 3.500 ISINs/Lauf weit ueber dem Limit.
  DivvyDiary faellt bei 429 still auf yfinance zurueck. Paid-Tier evaluieren.
- Plausibilitaets-Cap 5.000 bps laesst 10.000-bps-Eintraege durch wenn sie plausibel erscheinen.
  Konami/MSCI-Eintraege mit 10.000 bps wurden manuell bereinigt.
- boerse-frankfurt.de: Keine oeffentliche API. Reaktivierung erfordert offiziellen Zugang.
- yfinance-Instabilitaet: Kein SLA, gelegentliche HTTP-500. Exponential-Backoff implementiert.
- SQLite WAL-Modus: GUI-Batch + systemd-Timer koennen gleichzeitig schreiben (selten getestet).

---

## Suggested Capabilities For Next Session

- Analyse-Tab: Scoring-Verteilung als Balkendiagramm
- Watchlist-Tab: Persistente ISIN-Liste, manuell gepflegt
- DivvyDiary Paid-Tier evaluieren
- Property-based Tests (hypothesis) fuer _is_plausible() und float_to_bps()
- Datenqualitaets-Dashboard: Automatische Ausreisser-Erkennung nach jedem Lauf

---

## Session Timeline

| Datum | Aufgabe | Ergebnis |
|-------|---------|----------|
| 2026-04-29 | Projektanalyse Chat 08 | Fehlerhafte test_engine.py identifiziert |
| 2026-04-30 | init_db.py Constraint-Fix (openfigi_unvalidated) | OK |
| 2026-04-30 | conftest.py + test_engine.py neu | 27 Tests |
| 2026-04-30 | test_ticker_resolver.py neu | Alle gruen |
| 2026-05-02 | Bulk-Ticker-Import: 10.497 ISINs | 99,5 % Hit-Rate |
| 2026-05-02 | get_isins_due_for_update -- unresolvable ausschliessen | Fix |
| 2026-05-03 | Score-Spalte GUI + score_detail_panel.py | OK |
| 2026-05-04 | threshold_crossing_popup.py + Startup-Hook | 118 Crossings |
| 2026-05-05 | requirements.txt finalisiert | P6 dokumentiert, P7 entfernt |
| 2026-05-07 | Vollstaendiger Dividenden-Batch (6.483 ISINs, 39,9 %) | 92 % Abdeckung |
| 2026-05-07 | high_yield_tab.py + CSV-Export | OK |
| 2026-05-08 | NameEditDialog Timing-Fix | OK |
| 2026-05-08 | _TOTAL_PER_RUN 500 -> 3500 | E-Mail zeigt reale Zahlen |
| 2026-05-08 | Multi-Source-Kaskade eingefuehrt | OK |
| 2026-05-09 | boerse-frankfurt API-Analyse: leere Antworten | Stub, inaktiv |
| 2026-05-09 | Kaskade bereinigt: DivvyDiary -> yfinance | OK |
| 2026-05-09 | Tests: divvydiary, boerse_frankfurt, email_service, auto_dividend_update | 242 Tests gruen |
| 2026-05-10 | Plausibilitaets-Cap 5.000 bps + DB-Bereinigung (170 Ausreisser) | OK |
| 2026-05-10 | CI: Node.js 24, Actions-Versionen aktualisiert | OK |
| 2026-05-10 | Handoff-Dokument eingerichtet | docs/handoff-iELcyt.md |
