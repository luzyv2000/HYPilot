Exkurs 3 (geplant)

HYPilot Logging 

Hallo Claude, 

1. fasse noch einmal den aktuellen Stand beim Logging zusammen, inklusive aller Funktionen.

2. benenne alle angepassten oder neu entwickelten Dateien inklusive Pfadangabe.

Anmerkung:

​Für HYPilot ist eine effektive Logging-Strategie entscheidend, um Fehler zu beheben, die Leistung zu überwachen und das Benutzerverhalten zu verstehen. Hier sind meine Gedanken für eine umfassende Logging-Strategie.

​Welche Daten sollen geloggt werden?
​Es ist wichtig, eine Balance zwischen nützlichen Informationen und der Vermeidung von zu vielen unwichtigen Daten zu finden. Hier sind die wichtigsten Kategorien von Daten, die geloggt werden sollten:
System- und Anwendungsinformationen:
​Start und Ende der Anwendung: 
Wann wurde die Software gestartet und wann beendet? Das hilft, die Verfügbarkeit zu verfolgen.
​Konfigurationsparameter: 
Welche Einstellungen wurden beim Start verwendet? (z.B. der Pfad, in dem die PDFs gespeichert werden). Das ist nützlich, um Konfigurationsfehler zu finden.
Versionsnummer: 
Die Version der Software. So können wir Fehler bestimmten Softwareversionen zuordnen.
Download-Prozess:
​Download-Status: 
Erfolgreich, fehlgeschlagen, abgebrochen.
Dateiname und URL: 
Von welcher URL wurde welche Datei heruntergeladen?
Fehlercodes: 
Wenn ein Download fehlschlägt, warum? (z.B. HTTP-Statuscode 404 für "Nicht gefunden").
Dauer: 
Wie lange hat der Download gedauert? 
Verarbeitung der PDF-Dateien:
Dateiname: 
Welche Datei wird gerade verarbeitet?
Status der Verarbeitung: 
Start der Verarbeitung, erfolgreiches Ende, Fehlschlag.
​Extraktionsergebnisse: 
Welche Daten wurden aus dem PDF extrahiert? 
Fehler und Warnungen: 
Fehler beim Parsen des PDFs (z.B. ungültiges Format) oder Warnungen (z.B. fehlende Datenfelder).
Dauer der Verarbeitung: 
Wie lange hat die Verarbeitung einer einzelnen Datei gedauert? Das hilft, langsame Dateien zu identifizieren.
Anzeige- und Benutzereingaben
​Anzeige-Fehler: 
Probleme beim Rendern der Daten.
​Benutzeraktionen (optional): 
Welche Daten wurden angezeigt? Welche Filter wurden gesetzt? Dies kann nützlich sein, um das Nutzerverhalten zu verstehen und die Benutzeroberfläche zu optimieren. 
​Wann soll geloggt werden?
​Eine differenzierte Logging-Strategie mit verschiedenen Log-Levels ist hier am effektivsten. Das Standardmodul logging in Python bietet dafür die folgenden Stufen:
​DEBUG: Sehr detaillierte Informationen, die nur bei der Fehlerbehebung relevant sind (z.B. "Start der Funktion parse_pdf").
​INFO: Bestätigung, dass die Anwendung wie erwartet funktioniert (z.B. "Download von Datei 'report.pdf' abgeschlossen").
​WARNING: Ein unerwartetes Ereignis, das die Software aber nicht blockiert (z.B. "Ein optionales Feld konnte in 'invoice.pdf' nicht gefunden werden").
​ERROR: Ein Fehler, der einen Teil der Funktionalität verhindert (z.B. "Verarbeitung von 'corrupt.pdf' fehlgeschlagen").
​CRITICAL: Ein schwerwiegender Fehler, der die gesamte Anwendung stoppen könnte (z.B. "Datenbankverbindung nicht möglich, Anwendung wird beendet").
​Ideale Zeitpunkte zum Loggen:
​Start/Ende von Prozessen: Setze Log-Einträge auf INFO-Level, wenn ein wichtiger Prozess (Download, Verarbeitung) beginnt und endet.
​Fehler- und Ausnahmesituationen: Verwende ERROR oder CRITICAL, wenn etwas Unerwartetes passiert und die Software nicht wie geplant fortfahren kann.
​Warnungen: Verwende WARNING, wenn ein Problem auftritt, das die Anwendung aber handhaben kann.
​Debugging: Aktiviere DEBUG während der Entwicklung oder wenn aktiv nach einem Fehler gesucht wird. Im Produktivbetrieb soll dieses Level deaktiviert sein, um die Logdateien klein zu halten.
​Wo und wie lange sollen die Logs gespeichert werden?
​Speicherort:

Hast du noch Rückfragen oder Vorschläge zum Ausbau des Logging?

Hinweis: Wenn du noch den Code zusätzlicher Dateien benötigst, fordere diese an bevor du mit der Analyse weiter machst. 
