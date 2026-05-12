Exkurs 5 (geplant)

Einbindung der comdirect 

Kurz gesagt: comdirect stellt eine allgemeine REST‑API zur Verfügung, mit der man depot- und tradingbezogene Funktionen unabhängig nutzen kannst. 

comdirect bietet dazu ein REST API an, über das u. a. möglich ist: Depotübersicht abrufen, Orders aufgeben/ändern/stornieren, LiveTrading nutzen, Kontosalden und Umsätze abrufen, Postbox-Dokumente laden.

Eine Dokumentation und eine JSON-Datei habe ich im Projektwissen hinterlegt. 

Diese REST‑API ist explizit auch für Privatkunden freigeschaltet, d. h. man kann eigene Anwendungen schreiben, die auf ein echtes Konto oder Depot zugreifen und Orders ausführen. 

Geplant ist es nun, mittels vorhandener Zugangsdaten ein Depot bei comdirect aufzurufen, die Wertpapier-Daten herunterzuladen und übersichtlich anzuzeigen – über verschlüsselt abgespeicherte Zugangsdaten, nutzerfreundlich zu bedienen und die Daten so abgespeichert, dass sie lokal weiterverarbeitet werden können.
 
Einstiegspunkt und Doku: Die comdirect‑Seite zur REST‑API mit Beschreibung der Endpunkte (Depot, Order, LiveTrading etc.) und Hinweisen zur Registrierung.
In der Praxis nutzen viele die API z.B. über Postman oder eigene Skripte (Python, etc.), um Orders zu platzieren oder Depotdaten auszulesen.

Entwerfe mir in diesem Exkurs ein grobes Gerüst in Python oder eine Ablaufskizze, wie man so ein Depot der comdirect Bank inklusive der oben beschriebenen Funktionen als separaten Tab in HYPilot einbinden kann. 

➡️ Frage: Den Code welcher Dateien benötigst du zusätzlich, um konkrete Rückfragen zu stellen oder Vorschläge zu machen?

➡️ Sag mir einfach, womit wir loslegen sollen um die bestehende Struktur zu ergänzen – dann geht’s weiter!