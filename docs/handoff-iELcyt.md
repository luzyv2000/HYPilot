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

**Stand: 2026-05-13 (Sitzungsende)**

- 13.568 Instrumente im TR-Universum
- 12.486 ISINs mit Dividendendaten (92 % Abdeckung)
- 5.383 ISINs mit yield_bps > 0
- 283 High-Yield-Kandidaten >= 10 % (nach Plausibilitäts-Bereinigung)
- Quellen-Verteilung: yfinance 9.278 | divvydiary 3.410
- DIVVYDIARY_API_KEY in .env eingetragen (aktiv seit dieser Sitzung)
- 13.339 Ticker-Mappings (openfigi 10.955 | yfinance 1.413 | openfigi_unvalidated 874 | unresolvable 97)
- systemd-Timer aktiv: 08:00 + 13:00, _TOTAL_PER_RUN = 3500
- CI: GitHub Actions grün, Node.js 24 aktiviert (informational warning, kein Fehler)
- Test-Suite: 242 Tests, alle grün (unit + integration)
- GUI: 5 Tabs vollständig implementiert (TR-Universum, High-Yield, Analyse, Watchlist, Portfolio-Platzhalter)

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
| 2026-05-11 | test_engine.py: duplizierter Klassenname TestScoreInstrument behoben | Erste Klasse wurde still ueberschrieben, Tests liefen nie |
| 2026-05-11 | Analyse-Tab: 5 Sektionen (Scoring, Top-20, Wachstum, Crossings, KPIs) | Rein DB-basiert, kein Netzwerk, Canvas-Balkendiagramm |
| 2026-05-12 | Watchlist-Tab + watchlist-Tabelle in DB | Persistente ISIN-Liste mit Notizfeld, set_watchlist_tab()-Kopplung |
| 2026-05-12 | CI Node.js-Warnung: informational, keine Aktion noetig | actions/checkout@v4 etc. werden automatisch aktualisiert |

---

## Open Problems

| Prioritaet | Problem | Status |
|-----------|---------|--------|
| Niedrig | CI: informational warning "Node.js 20 is deprecated" | Kein Handlungsbedarf -- verschwindet wenn Action-Publisher node24 releasen |
| Niedrig | boerse_frankfurt_source.py -- ID-Aufloesung unbekannt | Stub, Reaktivierung erfordert offiziellen Zugang |
| Niedrig | migrations.py -- unfertiger Stub ohne gueltiges SQL | Nicht aktiv eingebunden, kann geloescht werden |
| Niedrig | DivvyDiary Rate-Limit (Free Tier ~100 Req/Tag) | Bei 429 faellt Kaskade still auf yfinance zurueck -- Paid-Tier evaluieren |

---

## Next Recommended Actions

1. Ersten vollstaendigen Auto-Lauf mit aktivem DIVVYDIARY_API_KEY beobachten:
   sqlite3 db/hypilot.db "SELECT data_source, COUNT(*) FROM dividend_data GROUP BY data_source"

2. Datenqualitaets-Monitoring nach jedem Auto-Lauf:
   sqlite3 db/hypilot.db "SELECT COUNT(*) FROM dividend_data WHERE yield_bps > 5000"

3. Property-based Tests (hypothesis) fuer _is_plausible() und float_to_bps() ergaenzen.

4. Portfolio-Tab implementieren (aktuell Platzhalter in gui/app.py).

5. migrations.py aufraemen: entweder vollstaendig implementieren oder loeschen.
   Aktuell toter Code der Verwechslungsgefahr mit init_db.py birgt.

---

## Relevant Artifacts

| Datei | Rolle |
|-------|-------|
| core/dividend_service.py | Kaskaden-Orchestrator, Plausibilitaets-Cap |
| core/sources/divvydiary_source.py | DivvyDiary REST-Adapter (aktiv) |
| core/sources/boerse_frankfurt_source.py | Stub -- inaktiv, dokumentiert |
| core/sources/yfinance_source.py | yfinance-Adapter (Fallback) |
| core/ticker_resolver.py | ISIN -> Ticker, drei Stufen (DB -> OpenFIGI -> yfinance) |
| db/dividend_repository.py | Schreibschicht dividend_data / threshold_crossings, GrowthMetrics |
| db/watchlist_repository.py | CRUD fuer watchlist-Tabelle |
| db/init_db.py | Schema + Migrationen, idempotent, watchlist-Tabelle enthalten |
| analysis/scorer.py | Scoring mit GrowthMetrics (historienbasiert) |
| gui/app.py | Hauptfenster, 5 Tabs, set_watchlist_tab()-Verdrahtung |
| gui/tabs/universe_tab.py | TR-Universum + Watchlist-Button |
| gui/tabs/high_yield_tab.py | High-Yield >= 10 %, CSV-Export, Watchlist-Button |
| gui/tabs/analyse_tab.py | Analyse: Scoring-Verteilung, Top-20, Wachstum, Crossings, KPIs |
| gui/tabs/watchlist_tab.py | Watchlist: Notizfeld, Score-Panel, Entfernen-Button |
| gui/widgets/score_detail_panel.py | 4 Teilscore-Balken bei Selektion |
| gui/widgets/threshold_crossing_popup.py | Startup-Popup fuer ungesehene Crossings |
| gui/widgets/name_edit_dialog.py | Doppelklick-Dialog, Timing-Fix 2026-05-08 |
| ingestion/auto_dividend_update.py | systemd-Einstiegspunkt, 3500 ISINs/Lauf |
| tests/test_analysis/test_engine.py | Duplikat-Klassenname behoben 2026-05-11 |
| .github/workflows/tests.yml | CI, Node.js 24, unit + integration |

---

## Risks / Caveats

- DivvyDiary Rate-Limit (Free Tier ~100 Req/Tag): Bei 3.500 ISINs/Lauf weit ueber dem Limit.
  DivvyDiary faellt bei 429 still auf yfinance zurueck. Paid-Tier evaluieren.
- Plausibilitaets-Cap 5.000 bps (50 %) aktiv. Weitere Ausreisser koennen entstehen
  wenn DivvyDiary neue Sonderausschuettungen meldet -- Monitoring nach jedem Lauf.
- boerse-frankfurt.de: Keine oeffentliche API. Reaktivierung erfordert offiziellen Zugang.
- yfinance-Instabilitaet: Kein SLA, gelegentliche HTTP-500. Exponential-Backoff implementiert.
- SQLite WAL-Modus: GUI-Batch + systemd-Timer koennen gleichzeitig schreiben (selten getestet).
- Watchlist-Tab: set_watchlist_tab() wird in app.py nach Tab-Erstellung aufgerufen.
  Reihenfolge in _build_tab_view() ist zwingend: WatchlistTab muss vor den Aufrufen existieren.

---

## Suggested Capabilities For Next Session

- Portfolio-Tab: Manuelle Positionsverwaltung (ISIN, Stueckzahl, Kaufkurs)
- Property-based Tests (hypothesis) fuer _is_plausible() und float_to_bps()
- Datenqualitaets-Dashboard: Automatische Ausreisser-Erkennung nach jedem Lauf
- DivvyDiary Paid-Tier evaluieren: Lohnt sich bei >100 Req/Tag?
- migrations.py: loeschen oder vollstaendig implementieren

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
| 2026-05-11 | test_engine.py: TestScoreInstrument-Duplikat behoben | Stille Testluecke geschlossen |
| 2026-05-11 | analyse_tab.py: 5 Sektionen implementiert | Canvas-Chart, GrowthMetrics integriert |
| 2026-05-12 | watchlist_tab.py vollstaendig | notes-NULL-Fix, reload()-API |
| 2026-05-12 | watchlist_repository.py, init_db.py: watchlist-Tabelle | Schema migriert |
| 2026-05-12 | universe_tab.py + high_yield_tab.py: Watchlist-Button | set_watchlist_tab()-Kopplung |
| 2026-05-13 | CI-Warnung analysiert: informational, kein Handlungsbedarf | OK |
| 2026-05-13 | Handoff-Dokument aktualisiert | docs/handoff-iELcyt.md |
