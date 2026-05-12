Exkurs 2 (geplant)

HYPilot Backup 

Implementierung eines Backup-Systems für HYPilot

​Projektziel: Die Einführung einer automatisierten, zuverlässigen und mehrstufigen Backup-Strategie, um Datenverlust bei der Wertpapier-Analyse Software HYPilot zu verhindern und eine schnelle Wiederherstellung zu ermöglichen.

1. Bestandsaufnahme der zu sichernden Daten.
A. ​Aufgabe: Identifizierung aller kritischen Daten, die für den Betrieb und die Analyse wichtig sind.

2. Festlegung der Backup-Strategie.
A. ​Aufgabe: Konzeption der Backup-Methodik (was, wann, wo).
B. ​Aktivitäten: 
* Definition der Backup-Frequenz (täglich, monatlich, quartalsweise).
* ​Entscheidung über Backup-Typen (inkrementell, vollständig).
* ​Auswahl der Speichermedien und -orte (lokal, NAS, Cloud-Speicher).
* Festlegung der Aufbewahrungsfristen (Retention Policy) für die verschiedenen Backups.

3. Entwicklung des Backup-Skripts.
A. ​Aufgabe: Erstellung eines Python-Skripts zur Automatisierung des Backup-Prozesses.
B. ​Aktivitäten: 
* ​Programmierung der Logik zum Sammeln und Komprimieren der Daten.
* ​Implementierung der Verschlüsselung der Backup-Dateien.
* ​Hinzufügen von Funktionen zum Kopieren der Backups an die definierten Speicherorte (lokal und Cloud).

4. Automatisierung der Backups.
​A. Aufgabe: Planung und Automatisierung der regelmäßigen Backup-Läufe.
B. ​Aktivitäten: ​
* Start eines Python-Skript zur festgelegten Zeit.
* ​Konfiguration von Benachrichtigungen (z. B. per E-Mail), die bei Erfolg oder Fehlschlag des Backups verschickt werden.

5. Regelmäßige Überprüfung und Anpassung.
A. ​Aufgabe: Das Backupsystem auf dem neuesten Stand halten.
B. ​Aktivitäten:
* ​Regelmäßige Überprüfung der Strategie bei Änderungen in der Software oder den Anforderungen.
* ​Durchführung von Wiederherstellungstests in regelmäßigen Abständen (z. B. halbjährlich).
* ​Anpassung der Richtlinien zur Datenaufbewahrung bei Bedarf.

Hast du noch Rückfragen oder Vorschläge?
