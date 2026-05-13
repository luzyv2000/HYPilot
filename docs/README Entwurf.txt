README - Entwurf -
Das Projekt HYPilot zielt darauf ab, eine automatisierte Lösung zur Identifizierung und Analyse
von Wertpapieren mit hoher Dividendenrendite zu entwickeln. Das Programm soll auf einem
Laptop ausgeführt werden und den Anwender täglich mit Kauf- und Verkaufsvorschlägen
unterstützen.
Infrage kommen alle bei Trade Republic handelbaren Wertpapiere, welche im PDF "Trade Republic
Handelsuniversum" aufgeführt sind, bevorzugt solche mit einer Dividendenrendite >10%. Ebenfalls
wichtig ist eine regelmäßige Dividendenausschüttung (monatlich oder quartalsweise).
ZIELE
1. Etablierung eines stabilen, modular aufgebauten Systems zur automatisierten Aktienanalyse
und Empfehlungen
2. Nutzung kostenfreier APIs und lokal gespeicherter Daten zur vollständigen Offline-
Verarbeitung
3. Morning-Routine: Empfehlungen um 09:00 Uhr, optional auch 16:30 Uhr
4. Transparenz und Anpassbarkeit: GUI mit Anfängermodus, manuelle Datenpflege möglich
5. Sicherung aller erhobenen Daten über ein automatisiertes 3-2-1-Backup-System
6. Möglichkeit zum parallelen Abruf großer Datenmengen (Langfristziel)
7. Permanente Prüfung auf Änderungen externer Quellen (robots.txt, Layoutänderungen)
SPEZIFIKATIONEN
Lokales Hauptverzeichnis: E:\HYPilot
Unterverzeichnisse: data (mit weiteren Unterordnern, konfigurierbar), logs, config
Datenstruktur in data:
○ trade_republic_pdf
○ broker_documents
○ manual_data
○ Weitere Unterordner erlaubt (konfigurierbar)
Logging:
○ Fehlerprotokoll
○ Abrufprotokoll mit Zeit, Quelle, URL
○ ZIP-Export aller Logs
GUI: Tabs (TR-Universum, Depot, Empfehlungen, Sparplan, Aristokraten, Info)
Anfängermodus ein-/ausschaltbar
Konfigurationsdatei: config/config.json (zentral)
Unterstützung von API-Schlüsseln (optional verschlüsselt speicherbar)
Backup: Täglich (30 Tage), monatlich (15 Monate), im Hintergrund
API-Nutzung: DivvyDiary, yfinance, OpenFIGI, optional Bavest, Marketstack und andere
Optionaler PYTR-Modus (separat startbar)
Mapping-Button in GUI zur manuellen Aktualisierung
Fehler bei ISIN-Mapping werden visuell hervorgehobenMEILENSTEINE V.1
Anzeige einer GUI
HYPilot soll eine GUI mit sortierbaren und wahlweise aktivierbaren bzw. deaktivierbaren Reitern
und einem Menü im Windows-Style haben. Entwerfe mir also eine GUI, welche zunächst folgende
Reiter aufweist:
TR-Universum (filterbar)
Synchronisation mit GitHub
Initialisiere lokales Git-Repo im Projektverzeichnis
Verknüpfe mit GitHub: https://github.com/DoerhageKiel/HYPilot
Automatischer Abgleich bei jedem Programmstart.
Import des TR Handelsuniversum
Download-Link:
https://assets.traderepublic.com/assets/files/DE/Instrument_Universe_DE_de.pdf
Automatische Prüfung auf Aktualität
Bei neuer Version: Nur neue ISINs extrahieren und speichern
Manuelles Re-Mapping via GUI-Button
Abruf Ticker mit Yahoo Finance
ISIN → Ticker via yfinance (Paketweise, 100er Blöcke, Pause zwischen Aufrufen)
Fehlermeldung bei nicht auflösbarer ISIN
Optional: Mapping mit OpenFIGI (pyopenfigi oder openfigipy)
Nehme beim Abrufen des Tickers immer die Heimatbörse des Wertpapiers. Sollte diese nicht
feststellbar sein, nehme für Wertpapiere aus:
USA NYSE oder NASDAQ
Deutschland Xetra
Großbritannien London Stock Exchange
Frankreich Euronext Paris
Schweiz SIX Swiss
Anzeige Dividendenrendite
Automatischer Abruf der aktu
