# **Feature- & Optimierungsliste   
(sortiert, konsolidiert)**

### ✅ = bereits umgesetzt

### 🟡 = teilweise vorbereitet

### ❌ = noch offen

## **A. Datenbeschaffung & -quellen**

1. Download TR-Handelsuniversum als PDF 

2. Hash-basierte PDF-Änderungserkennung (Delta) 

3. Archivierung alter PDFs 

4. Extraktion aller ISINs aus PDF 

5. Extraktion der **Wertpapiernamen aus PDF** 

6. CSV-basierte lokale Persistenz ISIN→Name 

7. Delta-Update nur für neue ISINs 

8. ISIN→Ticker über yfinance 

9. Optionales ISIN-Mapping über OpenFIGI 

10. Heimatbörsenlogik (NYSE/NASDAQ/Xetra etc.) 

11. Dividendenhistorie abrufen 

12. Dividendenrendite berechnen 

13. Zahlungsrhythmus automatisch erkennen 


## **B. GUI / Usability**

14. Tkinter-GUI Grundgerüst 

15. Notebook-Tabsystem 

16. TR-Universum Tab 

17. Dynamische Tabellenanzeige 

18. Spalten:

- Leer 

- Wertpapiername 

- ISIN/Ticker 

- Dividendenrendite 

- Zahlungsrhythmus 

19. Rote Fehler-Markierung bei fehlendem Name oder Ticker 

20. Sortierbare Spalten 

21. Filter (z. B. Rendite \>10 %) 

22. Button „nur fehlerhafte Datensätze anzeigen“ 

23. Anfänger-Modus 

24. Mapping-Button (manuelle Korrektur) 


## **C. Datenpersistenz & Verwaltung**

25. Zentrales config.json vorgesehen 

26. CSV-Speicherformat für Stammdaten 

27. Ticker-Mapping-Caching 

28. Fehler-Logs 

29. Abruf-Logs mit Quelle/URL 

30. ZIP-Export aller Logs 


## **D. System & Sicherheit**

31. 3-2-1-Backup-System (täglich/monatlich) 

32. API-Key-Verschlüsselung 

33. Automatischer GitHub-Sync beim Start 

34. Prüfungen auf robots.txt / Layoutänderungen 


## **E. Analyse & Empfehlungssystem**

35. Dividendenscreener \>10 % 

36. Aristokraten-Erkennung 

37. Kauf-/Verkaufssignale 

38. Morning-Routine 09:00 / 16:30 

39. Sparplan-Modul 

40. Depot-Modul 

41. Historische Performanceanalyse 



# 2. **Priorisierte Optimierungsvorschläge**

## 🔴 **Kritische Fehler / Risiken**

1. Kein Caching der Ticker → extreme API-Belastung

2. Kein Fallback bei yfinance-Ausfällen

3. Kein Backup-System → Datenverlust möglich

4. Keine Validierung bei fehlerhaften CSV-Einträgen


## 🟠 **Performance**

1. Ticker-Ergebnisse persistent zwischenspeichern

2. Multithreading beim yfinance-Abruf

3. Nur Delta auch bei Ticker-Daten

4. Lazy-Loading in der GUI bei großen Datenmengen


## 🟡 **Usability**

1. Spalten sortierbar machen

2. Filter nach:

   - Dividendenrendite

   - Zahlungsrhythmus

   - Fehlerstatus

3. Kontextmenü (Rechtsklick: manuell mappen)

4. Statusleiste mit Fortschritt

5. „Nur Fehler anzeigen“-Toggle


## 🟢 **Erweiterbarkeit**

1. Saubere Modul-Trennung:

   - data\_import

   - dividend\_engine

   - recommendation\_engine

2. Plugin-System für zusätzliche APIs

3. CLI-Modus für Headless-Betrieb

4. Python-Packaging als Desktop-App
