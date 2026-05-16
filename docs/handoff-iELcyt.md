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

**Stand: 2026-05-15 (Sitzungsende)**

- 13.568 Instrumente im TR-Universum
- 12.486 ISINs mit Dividendendaten (92 % Abdeckung)
- 5.383 ISINs mit yield_bps > 0
- 283 High-Yield-Kandidaten >= 10 % (nach Plausibilitäts-Bereinigung)
- Quellen-Verteilung: yfinance 9.278 | divvydiary 3.410
- DIVVYDIARY_API_KEY in .env eingetragen (aktiv)
- 13.339 Ticker-Mappings
- systemd-Timer aktiv: 08:00 + 13:00, _TOTAL_PER_RUN = 3500
- CI: GitHub Actions grün, Node.js 24 aktiviert (informational warning, kein Fehler)
- Test-Suite: ~290 Tests, alle gruen (unit + integration + hypothesis)
- GUI: 5 Tabs vollstaendig implementiert (TR-Universum, High-Yield, Analyse, Watchlist, Portfolio)
- Portfolio-Tab: Positionsverwaltung mit Jahresertrag-Schaetzung
- Datenqualitaets-Monitoring: core/data_quality.py + Anzeige in Analyse-Tab

---

## Decisions Made

| Datum | Entscheidung | Begruendung |
|-------|-------------|------------|
| 2026-05-08 | CTkToplevel Timing-Fix via after(20)/after(50) | grab_set() vor Window-Manager-Mapping fuehrte zu leerem Fenster |
| 2026-05-08 | _TOTAL_PER_RUN 500 -> 3500 | Nur 15 % des faelligen Universums wurde abgedeckt |
| 2026-05-08 | Multi-Source-Kaskade: DivvyDiary -> yfinance | boerse-frankfurt.de erfordert interne IDs, kein oeffentlicher Zugang |
| 2026-05-09 | boerse-frankfurt als Stub behalten | Reaktivierung moeglich sobald offizieller API-Zugang verfuegbar |
| 2026-05-09 | ticker-Parameter in DividendSource optional (= "") | ISIN-native Quellen (DivvyDiary) benoetigen keinen Ticker |
| 2026-05-09 | _CASCADE_SOURCES-Liste als zentraler Erweiterungspunkt | Neue Quelle = 1 Zeile, kein Umbau der Orchestrierungslogik |
| 2026-05-10 | Plausibilitaets-Cap: yield_bps > 5000 (50 %) -> verwerfen | DivvyDiary liefert Sonderausschuettungen als Rendite (Leo Lithium 681 %) |
| 2026-05-10 | Bereinigung bestehender Ausreisser: yield_bps = NULL, skip_until = +7d | 170 Eintraege bereinigt |
| 2026-05-10 | CI: FORCE_JAVASCRIPT_ACTIONS_TO_NODE24 + Actions auf v4/v5 | Node.js 20 deprecated ab Juni 2026 |
| 2026-05-11 | test_engine.py: duplizierter Klassenname TestScoreInstrument behoben | Erste Klasse wurde still ueberschrieben, Tests liefen nie |
| 2026-05-11 | Analyse-Tab: 5 Sektionen (Scoring, Top-20, Wachstum, Crossings, KPIs) | Rein DB-basiert, kein Netzwerk, Canvas-Balkendiagramm |
| 2026-05-12 | Watchlist-Tab + watchlist-Tabelle in DB | Persistente ISIN-Liste mit Notizfeld |
| 2026-05-13 | CI Node.js-Warnung: informational, keine Aktion noetig | verschwindet wenn Action-Publisher node24 releasen |
| 2026-05-15 | migrations.py geloescht | Toter Code, Verwechslungsgefahr mit init_db.py |
| 2026-05-15 | Portfolio-Tab implementiert | Positionsverwaltung mit shares_micro/buy_price_micro, Jahresertrag |
| 2026-05-15 | Property-based Tests (hypothesis) fuer Konvertierungen + _is_plausible | Findet unbekannte Grenzfaelle die Parametrize uebersieht |
| 2026-05-15 | core/data_quality.py als eigenstaendiges Modul | Testbar, wiederverwendbar, von auto_dividend_update aufgerufen |
| 2026-05-15 | Datenqualitaets-Bericht in metadata-Tabelle (last_quality_report) | Kein extra Schema, GUI liest beim naechsten Start |

---

## Open Problems

| Prioritaet | Problem | Status |
|-----------|---------|--------|
| Niedrig | CI: informational warning "Node.js 20 is deprecated" | Kein Handlungsbedarf |
| Niedrig | boerse_frankfurt_source.py -- ID-Aufloesung unbekannt | Stub, Reaktivierung erfordert offiziellen Zugang |
| Niedrig | DivvyDiary Rate-Limit (Free Tier ~100 Req/Tag) | Bei 429 faellt Kaskade auf yfinance zurueck -- Paid-Tier evaluieren |

---

## Next Recommended Actions

1. Nach Deploy: ersten Auto-Lauf mit Qualitaets-Report beobachten:
   sqlite3 db/hypilot.db "SELECT value FROM metadata WHERE key='last_quality_report'"

2. Datenqualitaets-Monitoring pruefen ob Ausreisser-Zaehler > 0:
   => Eintraege mit yield_bps > 5000 manuell pruefen

3. DivvyDiary Paid-Tier evaluieren (lohnt sich bei >100 Req/Tag).

4. Portfolio-Tab: Multicurrency-Gesamtrechnung (aktuell nur bei einer Waehrung summiert).

---

## Relevant Artifacts

| Datei | Rolle |
|-------|-------|
| core/data_quality.py | Datenqualitaets-Analyse, schreibt last_quality_report in metadata |
| core/dividend_service.py | Kaskaden-Orchestrator, Plausibilitaets-Cap |
| core/sources/divvydiary_source.py | DivvyDiary REST-Adapter (aktiv) |
| core/sources/boerse_frankfurt_source.py | Stub -- inaktiv, dokumentiert |
| core/sources/yfinance_source.py | yfinance-Adapter (Fallback) |
| core/ticker_resolver.py | ISIN -> Ticker, drei Stufen |
| db/dividend_repository.py | Schreibschicht dividend_data / threshold_crossings, GrowthMetrics |
| db/portfolio_repository.py | CRUD fuer portfolio-Tabelle |
| db/watchlist_repository.py | CRUD fuer watchlist-Tabelle |
| db/init_db.py | Schema + Migrationen, portfolio-Tabelle enthalten |
| analysis/scorer.py | Scoring mit GrowthMetrics (historienbasiert) |
| gui/app.py | Hauptfenster, 5 Tabs |
| gui/tabs/universe_tab.py | TR-Universum + Watchlist-Button |
| gui/tabs/high_yield_tab.py | High-Yield >= 10 %, CSV-Export, Watchlist-Button |
| gui/tabs/analyse_tab.py | 6 Sektionen inkl. Datenqualitaets-Report |
| gui/tabs/watchlist_tab.py | Watchlist: Notizfeld, Score-Panel |
| gui/tabs/portfolio_tab.py | Portfolio: Positionen, Jahresertrag-Schaetzung |
| gui/widgets/score_detail_panel.py | 4 Teilscore-Balken bei Selektion |
| gui/widgets/threshold_crossing_popup.py | Startup-Popup fuer ungesehene Crossings |
| gui/widgets/name_edit_dialog.py | Doppelklick-Dialog, Timing-Fix 2026-05-08 |
| ingestion/auto_dividend_update.py | systemd-Einstiegspunkt, ruft data_quality auf |
| tests/test_core/test_conversions_hypothesis.py | Hypothesis-Tests Konvertierungen + _is_plausible |
| tests/test_db/test_portfolio_repository.py | Integrationstests Portfolio-Repository |
| .github/workflows/tests.yml | CI, Node.js 24, unit + integration |

---

## Risks / Caveats

- DivvyDiary Rate-Limit (Free Tier ~100 Req/Tag): Kaskade faellt bei 429 auf yfinance zurueck.
- Plausibilitaets-Cap 5.000 bps aktiv. Monitoring via Datenqualitaets-Report nach jedem Lauf.
- boerse-frankfurt.de: Keine oeffentliche API.
- yfinance-Instabilitaet: Exponential-Backoff implementiert.
- SQLite WAL-Modus: GUI-Batch + systemd-Timer koennen gleichzeitig schreiben.
- Portfolio Multicurrency: Jahresertrag-Summe nur bei einer Waehrung berechnet.

---

## Session Timeline

| Datum | Aufgabe | Ergebnis |
|-------|---------|----------|
| 2026-04-29 | Projektanalyse Chat 08 | Fehlerhafte test_engine.py identifiziert |
| 2026-04-30 | init_db.py Constraint-Fix | OK |
| 2026-04-30 | conftest.py + test_engine.py neu | 27 Tests |
| 2026-04-30 | test_ticker_resolver.py neu | Alle gruen |
| 2026-05-02 | Bulk-Ticker-Import: 10.497 ISINs | 99,5 % Hit-Rate |
| 2026-05-03 | Score-Spalte GUI + score_detail_panel.py | OK |
| 2026-05-04 | threshold_crossing_popup.py + Startup-Hook | 118 Crossings |
| 2026-05-05 | requirements.txt finalisiert | OK |
| 2026-05-07 | Dividenden-Batch (6.483 ISINs) | 92 % Abdeckung |
| 2026-05-07 | high_yield_tab.py + CSV-Export | OK |
| 2026-05-08 | NameEditDialog Timing-Fix | OK |
| 2026-05-08 | _TOTAL_PER_RUN 500 -> 3500 | OK |
| 2026-05-08 | Multi-Source-Kaskade eingefuehrt | OK |
| 2026-05-09 | boerse-frankfurt API-Analyse: leere Antworten | Stub, inaktiv |
| 2026-05-09 | Tests: divvydiary, boerse_frankfurt, email, auto_update | 242 Tests gruen |
| 2026-05-10 | Plausibilitaets-Cap 5.000 bps + DB-Bereinigung | OK |
| 2026-05-10 | CI: Node.js 24 | OK |
| 2026-05-10 | Handoff-Dokument eingerichtet | docs/handoff-iELcyt.md |
| 2026-05-11 | test_engine.py: Duplikat behoben | OK |
| 2026-05-11 | analyse_tab.py: 5 Sektionen | OK |
| 2026-05-12 | watchlist_tab.py + watchlist_repository.py | OK |
| 2026-05-13 | CI-Warnung analysiert: informational | OK |
| 2026-05-15 | migrations.py geloescht | Toter Code entfernt |
| 2026-05-15 | portfolio_repository.py + portfolio_tab.py | Positionsverwaltung |
| 2026-05-15 | test_conversions_hypothesis.py + test_portfolio_repository.py | ~70 neue Tests |
| 2026-05-15 | core/data_quality.py + Analyse-Tab Sektion 6 | Qualitaets-Monitoring |
