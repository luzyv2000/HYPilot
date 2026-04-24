luzy@luzy-NucBox-K8-Plus:~/workspace/openclaw-min$ cd /home/luzy/workspace/openclaw-min
source venv/bin/activate

# python-dateutil installieren (für 18-Monats-Berechnung)
pip install python-dateutil

# requirements.txt ergänzen
echo "python-dateutil>=2.9" >> requirements.txt

# Schema migrieren
python -m db.init_db

# Manueller Test-Lauf (5 ISINs)
python - <<'EOF'
import logging
logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s")
from core.dividend_service import update_batch_due
stats = update_batch_due(limit=5)
print(stats)
EOF

# Timer-Status prüfen
sudo systemctl status hypilot-dividends.timer

# GUI starten
python hypilot.py
Requirement already satisfied: python-dateutil in ./venv/lib/python3.12/site-packages (2.9.0.post0)
Requirement already satisfied: six>=1.5 in ./venv/lib/python3.12/site-packages (from python-dateutil) (1.17.0)
2026-04-24 09:34:49,112 [INFO] __main__: Initialisiere Datenbank: /home/luzy/workspace/openclaw-min/db/hypilot.db
Traceback (most recent call last):
  File "<frozen runpy>", line 198, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "/home/luzy/workspace/openclaw-min/db/init_db.py", line 199, in <module>
    init_database()
  File "/home/luzy/workspace/openclaw-min/db/init_db.py", line 179, in init_database
    conn.execute(ddl)
sqlite3.OperationalError: no such column: skip_until
Traceback (most recent call last):
  File "<stdin>", line 5, in <module>
  File "/home/luzy/workspace/openclaw-min/core/dividend_service.py", line 176, in update_batch_due
    isins = dividend_repository.get_isins_due_for_update(
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/luzy/workspace/openclaw-min/db/dividend_repository.py", line 234, in get_isins_due_for_update
    rows = conn.execute(
           ^^^^^^^^^^^^^
sqlite3.OperationalError: no such column: d.skip_until
[sudo] Passwort für luzy: 
● hypilot-dividends.timer - HYPilot Dividenden-Abruf Timer (08:00 + 13:00)
     Loaded: loaded (/etc/systemd/system/hypilot-dividends.timer; enabled; pres>
     Active: active (waiting) since Fri 2026-04-24 09:23:58 CEST; 10min ago
    Trigger: Fri 2026-04-24 13:03:13 CEST; 3h 28min left
   Triggers: ● hypilot-dividends.service

Apr 24 09:23:58 luzy-NucBox-K8-Plus systemd[1]: Started hypilot-dividends.timer>
lines 1-7/7 (END)
2026-04-24 09:35:43 [INFO    ] gui.tabs.universe_tab: Universe geladen: 13568 Instrumente.
2026-04-24 09:35:56 [INFO    ] gui.tabs.universe_tab: Universe geladen: 13568 Instrumente.
2026-04-24 09:35:57 [INFO    ] gui.tabs.universe_tab: Universe geladen: 13568 Instrumente.
2026-04-24 09:36:07 [INFO    ] gui.tabs.universe_tab: Universe geladen: 13568 Instrumente.
2026-04-24 09:36:08 [INFO    ] gui.tabs.universe_tab: Universe geladen: 13568 Instrumente.
(venv) luzy@luzy-NucBox-K8-Plus:~/workspace/openclaw-min$ cd /home/luzy/workspace/openclaw-min
source venv/bin/activate

# python-dateutil installieren (für 18-Monats-Berechnung)
pip install python-dateutil

# requirements.txt ergänzen
echo "python-dateutil>=2.9" >> requirements.txt

# Schema migrieren
python -m db.init_db

# Manueller Test-Lauf (5 ISINs)
python - <<'EOF'
import logging
logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s")
from core.dividend_service import update_batch_due
stats = update_batch_due(limit=5)
print(stats)
EOF

# Timer-Status prüfen
sudo systemctl status hypilot-dividends.timer

# GUI starten
python hypilot.py
Requirement already satisfied: python-dateutil in ./venv/lib/python3.12/site-packages (2.9.0.post0)
Requirement already satisfied: six>=1.5 in ./venv/lib/python3.12/site-packages (from python-dateutil) (1.17.0)
2026-04-24 09:36:21,672 [INFO] __main__: Initialisiere Datenbank: /home/luzy/workspace/openclaw-min/db/hypilot.db
Traceback (most recent call last):
  File "<frozen runpy>", line 198, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "/home/luzy/workspace/openclaw-min/db/init_db.py", line 199, in <module>
    init_database()
  File "/home/luzy/workspace/openclaw-min/db/init_db.py", line 179, in init_database
    conn.execute(ddl)
sqlite3.OperationalError: no such column: skip_until
Traceback (most recent call last):
  File "<stdin>", line 5, in <module>
  File "/home/luzy/workspace/openclaw-min/core/dividend_service.py", line 176, in update_batch_due
    isins = dividend_repository.get_isins_due_for_update(
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/luzy/workspace/openclaw-min/db/dividend_repository.py", line 234, in get_isins_due_for_update
    rows = conn.execute(
           ^^^^^^^^^^^^^
sqlite3.OperationalError: no such column: d.skip_until
● hypilot-dividends.timer - HYPilot Dividenden-Abruf Timer (08:00 + 13:00)
     Loaded: loaded (/etc/systemd/system/hypilot-dividends.timer; enabled; pres>
     Active: active (waiting) since Fri 2026-04-24 09:23:58 CEST; 12min ago
    Trigger: Fri 2026-04-24 13:03:13 CEST; 3h 26min left
   Triggers: ● hypilot-dividends.service

Apr 24 09:23:58 luzy-NucBox-K8-Plus systemd[1]: Started hypilot-dividends.timer>

2026-04-24 09:36:27 [INFO    ] gui.tabs.universe_tab: Universe geladen: 13568 Instrumente.
2026-04-24 09:36:33 [INFO    ] core.dividend_service: Dividenden-Update: AT0000A38M45
2026-04-24 09:36:35 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: CLEN"}}}
2026-04-24 09:36:35 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker CLEN für AT0000A38M45 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:36:35 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für AT0000A38M45: Invalid ISIN number: AT0000A38M45
2026-04-24 09:36:35 [WARNING ] core.dividend_service: Kein Ticker für AT0000A38M45 — übersprungen.
2026-04-24 09:36:35 [INFO    ] core.dividend_service: Dividenden-Update: AU0000009771
2026-04-24 09:36:36 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: UNIRF"}}}
2026-04-24 09:36:37 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker UNIRF für AU0000009771 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:36:37 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für AU0000009771: Invalid ISIN number: AU0000009771
2026-04-24 09:36:37 [WARNING ] core.dividend_service: Kein Ticker für AU0000009771 — übersprungen.
2026-04-24 09:36:37 [INFO    ] core.dividend_service: Dividenden-Update: AU000000CDD7
2026-04-24 09:36:38 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: COLDF"}}}
2026-04-24 09:36:38 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker COLDF für AU000000CDD7 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:36:38 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für AU000000CDD7: Invalid ISIN number: AU000000CDD7
2026-04-24 09:36:38 [WARNING ] core.dividend_service: Kein Ticker für AU000000CDD7 — übersprungen.
2026-04-24 09:36:38 [INFO    ] core.dividend_service: Dividenden-Update: AU000000GBZ5
2026-04-24 09:36:39 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für AU000000GBZ5: Invalid ISIN number: AU000000GBZ5
2026-04-24 09:36:39 [WARNING ] core.dividend_service: Kein Ticker für AU000000GBZ5 — übersprungen.
2026-04-24 09:36:39 [INFO    ] core.dividend_service: Dividenden-Update: AU000000MRC8
2026-04-24 09:36:40 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: 58M"}}}
2026-04-24 09:36:41 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker 58M für AU000000MRC8 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:36:41 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für AU000000MRC8: Invalid ISIN number: AU000000MRC8
2026-04-24 09:36:41 [WARNING ] core.dividend_service: Kein Ticker für AU000000MRC8 — übersprungen.
2026-04-24 09:36:41 [INFO    ] core.dividend_service: Dividenden-Update: AU000000PGH3
2026-04-24 09:36:42 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: PTTCF"}}}
2026-04-24 09:36:42 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker PTTCF für AU000000PGH3 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:36:42 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für AU000000PGH3: Invalid ISIN number: AU000000PGH3
2026-04-24 09:36:42 [WARNING ] core.dividend_service: Kein Ticker für AU000000PGH3 — übersprungen.
2026-04-24 09:36:42 [INFO    ] core.dividend_service: Dividenden-Update: AU000000TDO8
2026-04-24 09:36:44 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: TOILF"}}}
2026-04-24 09:36:44 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker TOILF für AU000000TDO8 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:36:44 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für AU000000TDO8: Invalid ISIN number: AU000000TDO8
2026-04-24 09:36:44 [WARNING ] core.dividend_service: Kein Ticker für AU000000TDO8 — übersprungen.
2026-04-24 09:36:44 [INFO    ] core.dividend_service: Dividenden-Update: AU0000111395
2026-04-24 09:36:45 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für AU0000111395: Invalid ISIN number: AU0000111395
2026-04-24 09:36:45 [WARNING ] core.dividend_service: Kein Ticker für AU0000111395 — übersprungen.
2026-04-24 09:36:45 [INFO    ] core.dividend_service: Dividenden-Update: AU0000114522
2026-04-24 09:36:46 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: N9F"}}}
2026-04-24 09:36:46 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker N9F für AU0000114522 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:36:46 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für AU0000114522: Invalid ISIN number: AU0000114522
2026-04-24 09:36:46 [WARNING ] core.dividend_service: Kein Ticker für AU0000114522 — übersprungen.
2026-04-24 09:36:46 [INFO    ] core.dividend_service: Dividenden-Update: AU0000114977
2026-04-24 09:36:47 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: BK4"}}}
2026-04-24 09:36:48 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker BK4 für AU0000114977 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:36:48 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für AU0000114977: Invalid ISIN number: AU0000114977
2026-04-24 09:36:48 [WARNING ] core.dividend_service: Kein Ticker für AU0000114977 — übersprungen.
2026-04-24 09:36:48 [INFO    ] core.dividend_service: Dividenden-Update: AU0000221251
2026-04-24 09:36:49 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: LLLAF"}}}
2026-04-24 09:36:49 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker LLLAF für AU0000221251 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:36:49 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für AU0000221251: Invalid ISIN number: AU0000221251
2026-04-24 09:36:49 [WARNING ] core.dividend_service: Kein Ticker für AU0000221251 — übersprungen.
2026-04-24 09:36:49 [INFO    ] core.dividend_service: Dividenden-Update: AU0000272072
2026-04-24 09:36:51 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: AOUEUR"}}}
2026-04-24 09:36:51 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker AOUEUR für AU0000272072 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:36:51 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für AU0000272072: Invalid ISIN number: AU0000272072
2026-04-24 09:36:51 [WARNING ] core.dividend_service: Kein Ticker für AU0000272072 — übersprungen.
2026-04-24 09:36:51 [INFO    ] core.dividend_service: Dividenden-Update: AU0000294233
2026-04-24 09:36:52 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: 6G40"}}}
2026-04-24 09:36:53 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker 6G40 für AU0000294233 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:36:53 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für AU0000294233: Invalid ISIN number: AU0000294233
2026-04-24 09:36:53 [WARNING ] core.dividend_service: Kein Ticker für AU0000294233 — übersprungen.
2026-04-24 09:36:53 [INFO    ] core.dividend_service: Dividenden-Update: AU0000327504
2026-04-24 09:36:54 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für AU0000327504: Invalid ISIN number: AU0000327504
2026-04-24 09:36:54 [WARNING ] core.dividend_service: Kein Ticker für AU0000327504 — übersprungen.
2026-04-24 09:36:54 [INFO    ] core.dividend_service: Dividenden-Update: BE0003215143
2026-04-24 09:36:55 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: FLOB"}}}
2026-04-24 09:36:55 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker FLOB für BE0003215143 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:36:55 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für BE0003215143: Invalid ISIN number: BE0003215143
2026-04-24 09:36:55 [WARNING ] core.dividend_service: Kein Ticker für BE0003215143 — übersprungen.
2026-04-24 09:36:55 [INFO    ] core.dividend_service: Dividenden-Update: BE0003723377
2026-04-24 09:36:56 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: IZ2"}}}
2026-04-24 09:36:57 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker IZ2 für BE0003723377 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:36:57 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für BE0003723377: Invalid ISIN number: BE0003723377
2026-04-24 09:36:57 [WARNING ] core.dividend_service: Kein Ticker für BE0003723377 — übersprungen.
2026-04-24 09:36:57 [INFO    ] core.dividend_service: Dividenden-Update: BE0003836534
2026-04-24 09:36:58 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: OPTIB"}}}
2026-04-24 09:36:58 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker OPTIB für BE0003836534 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:36:58 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für BE0003836534: Invalid ISIN number: BE0003836534
2026-04-24 09:36:58 [WARNING ] core.dividend_service: Kein Ticker für BE0003836534 — übersprungen.
2026-04-24 09:36:58 [INFO    ] core.dividend_service: Dividenden-Update: BMG053845019
2026-04-24 09:36:59 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: 8ZV"}}}
2026-04-24 09:37:00 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker 8ZV für BMG053845019 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:37:00 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für BMG053845019: Invalid ISIN number: BMG053845019
2026-04-24 09:37:00 [WARNING ] core.dividend_service: Kein Ticker für BMG053845019 — übersprungen.
2026-04-24 09:37:00 [INFO    ] core.dividend_service: Dividenden-Update: BMG1146K1018
2026-04-24 09:37:01 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: 686EUR"}}}
2026-04-24 09:37:01 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker 686EUR für BMG1146K1018 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:37:01 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für BMG1146K1018: Invalid ISIN number: BMG1146K1018
2026-04-24 09:37:01 [WARNING ] core.dividend_service: Kein Ticker für BMG1146K1018 — übersprungen.
2026-04-24 09:37:01 [INFO    ] core.dividend_service: Dividenden-Update: BMG2415A1137
2026-04-24 09:37:03 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: CLCO"}}}
2026-04-24 09:37:03 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker CLCO für BMG2415A1137 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:37:03 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für BMG2415A1137: Invalid ISIN number: BMG2415A1137
2026-04-24 09:37:03 [WARNING ] core.dividend_service: Kein Ticker für BMG2415A1137 — übersprungen.
2026-04-24 09:37:03 [INFO    ] core.dividend_service: Dividenden-Update: BMG464011086
2026-04-24 09:37:04 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für BMG464011086: Invalid ISIN number: BMG464011086
2026-04-24 09:37:04 [WARNING ] core.dividend_service: Kein Ticker für BMG464011086 — übersprungen.
2026-04-24 09:37:04 [INFO    ] core.dividend_service: Dividenden-Update: BMG5370A1018
2026-04-24 09:37:05 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: 8G7"}}}
2026-04-24 09:37:05 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker 8G7 für BMG5370A1018 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:37:06 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für BMG5370A1018: Invalid ISIN number: BMG5370A1018
2026-04-24 09:37:06 [WARNING ] core.dividend_service: Kein Ticker für BMG5370A1018 — übersprungen.
2026-04-24 09:37:06 [INFO    ] core.dividend_service: Dividenden-Update: BMG6144P1014
2026-04-24 09:37:07 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: 230"}}}
2026-04-24 09:37:07 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker 230 für BMG6144P1014 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:37:07 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für BMG6144P1014: Invalid ISIN number: BMG6144P1014
2026-04-24 09:37:07 [WARNING ] core.dividend_service: Kein Ticker für BMG6144P1014 — übersprungen.
2026-04-24 09:37:07 [INFO    ] core.dividend_service: Dividenden-Update: BMG6389N1002
2026-04-24 09:37:08 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: SO7"}}}
2026-04-24 09:37:09 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker SO7 für BMG6389N1002 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:37:09 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für BMG6389N1002: Invalid ISIN number: BMG6389N1002
2026-04-24 09:37:09 [WARNING ] core.dividend_service: Kein Ticker für BMG6389N1002 — übersprungen.
2026-04-24 09:37:09 [INFO    ] core.dividend_service: Dividenden-Update: CA00149L1058
2026-04-24 09:37:10 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: AJNEUR"}}}
2026-04-24 09:37:10 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker AJNEUR für CA00149L1058 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:37:10 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für CA00149L1058: Invalid ISIN number: CA00149L1058
2026-04-24 09:37:10 [WARNING ] core.dividend_service: Kein Ticker für CA00149L1058 — übersprungen.
2026-04-24 09:37:10 [INFO    ] core.dividend_service: Dividenden-Update: CA00165X1087
2026-04-24 09:37:11 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für CA00165X1087: Invalid ISIN number: CA00165X1087
2026-04-24 09:37:11 [WARNING ] core.dividend_service: Kein Ticker für CA00165X1087 — übersprungen.
2026-04-24 09:37:11 [INFO    ] core.dividend_service: Dividenden-Update: CA00829Q1019
2026-04-24 09:37:12 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: AOI1EUR"}}}
2026-04-24 09:37:13 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker AOI1EUR für CA00829Q1019 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:37:13 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für CA00829Q1019: Invalid ISIN number: CA00829Q1019
2026-04-24 09:37:13 [WARNING ] core.dividend_service: Kein Ticker für CA00829Q1019 — übersprungen.
2026-04-24 09:37:13 [INFO    ] core.dividend_service: Dividenden-Update: CA02137W2004
2026-04-24 09:37:14 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: 90AA"}}}
2026-04-24 09:37:14 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker 90AA für CA02137W2004 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:37:15 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für CA02137W2004: Invalid ISIN number: CA02137W2004
2026-04-24 09:37:15 [WARNING ] core.dividend_service: Kein Ticker für CA02137W2004 — übersprungen.
2026-04-24 09:37:15 [INFO    ] core.dividend_service: Dividenden-Update: CA03990C1095
2026-04-24 09:37:16 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: RRSFF"}}}
2026-04-24 09:37:16 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker RRSFF für CA03990C1095 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:37:16 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für CA03990C1095: Invalid ISIN number: CA03990C1095
2026-04-24 09:37:16 [WARNING ] core.dividend_service: Kein Ticker für CA03990C1095 — übersprungen.
2026-04-24 09:37:16 [INFO    ] core.dividend_service: Dividenden-Update: CA04315L1058
2026-04-24 09:37:17 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: ARESF"}}}
2026-04-24 09:37:18 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker ARESF für CA04315L1058 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:37:18 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für CA04315L1058: Invalid ISIN number: CA04315L1058
2026-04-24 09:37:18 [WARNING ] core.dividend_service: Kein Ticker für CA04315L1058 — übersprungen.
2026-04-24 09:37:18 [INFO    ] core.dividend_service: Dividenden-Update: CA04364G1063
2026-04-24 09:37:19 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: AOT1EUR"}}}
2026-04-24 09:37:20 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker AOT1EUR für CA04364G1063 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:37:20 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für CA04364G1063: Invalid ISIN number: CA04364G1063
2026-04-24 09:37:20 [WARNING ] core.dividend_service: Kein Ticker für CA04364G1063 — übersprungen.
2026-04-24 09:37:20 [INFO    ] core.dividend_service: Dividenden-Update: CA0467971069
2026-04-24 09:37:21 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für CA0467971069: Invalid ISIN number: CA0467971069
2026-04-24 09:37:21 [WARNING ] core.dividend_service: Kein Ticker für CA0467971069 — übersprungen.
2026-04-24 09:37:21 [INFO    ] core.dividend_service: Dividenden-Update: CA06683R1010
2026-04-24 09:37:22 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: BNXAF"}}}
2026-04-24 09:37:22 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker BNXAF für CA06683R1010 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:37:22 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für CA06683R1010: Invalid ISIN number: CA06683R1010
2026-04-24 09:37:22 [WARNING ] core.dividend_service: Kein Ticker für CA06683R1010 — übersprungen.
2026-04-24 09:37:22 [INFO    ] core.dividend_service: Dividenden-Update: CA09173B1076
2026-04-24 09:37:24 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: 1B2"}}}
2026-04-24 09:37:24 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker 1B2 für CA09173B1076 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:37:24 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für CA09173B1076: Invalid ISIN number: CA09173B1076
2026-04-24 09:37:24 [WARNING ] core.dividend_service: Kein Ticker für CA09173B1076 — übersprungen.
2026-04-24 09:37:24 [INFO    ] core.dividend_service: Dividenden-Update: CA09237D1078
2026-04-24 09:37:25 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für CA09237D1078: Invalid ISIN number: CA09237D1078
2026-04-24 09:37:25 [WARNING ] core.dividend_service: Kein Ticker für CA09237D1078 — übersprungen.
2026-04-24 09:37:25 [INFO    ] core.dividend_service: Dividenden-Update: CA09353K3073
2026-04-24 09:37:26 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: JL4"}}}
2026-04-24 09:37:26 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker JL4 für CA09353K3073 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:37:26 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für CA09353K3073: Invalid ISIN number: CA09353K3073
2026-04-24 09:37:26 [WARNING ] core.dividend_service: Kein Ticker für CA09353K3073 — übersprungen.
2026-04-24 09:37:26 [INFO    ] core.dividend_service: Dividenden-Update: CA1352081063
2026-04-24 09:37:28 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: P4XA"}}}
2026-04-24 09:37:28 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker P4XA für CA1352081063 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:37:28 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für CA1352081063: Invalid ISIN number: CA1352081063
2026-04-24 09:37:28 [WARNING ] core.dividend_service: Kein Ticker für CA1352081063 — übersprungen.
2026-04-24 09:37:28 [INFO    ] core.dividend_service: Dividenden-Update: CA1375842079
2026-04-24 09:37:29 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für CA1375842079: Invalid ISIN number: CA1375842079
2026-04-24 09:37:29 [WARNING ] core.dividend_service: Kein Ticker für CA1375842079 — übersprungen.
2026-04-24 09:37:29 [INFO    ] core.dividend_service: Dividenden-Update: CA1377991023
2026-04-24 09:37:30 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: TBF1"}}}
2026-04-24 09:37:30 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker TBF1 für CA1377991023 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:37:30 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für CA1377991023: Invalid ISIN number: CA1377991023
2026-04-24 09:37:30 [WARNING ] core.dividend_service: Kein Ticker für CA1377991023 — übersprungen.
2026-04-24 09:37:30 [INFO    ] core.dividend_service: Dividenden-Update: CA1389093040
2026-04-24 09:37:32 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: CDAEUR"}}}
2026-04-24 09:37:32 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker CDAEUR für CA1389093040 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:37:32 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für CA1389093040: Invalid ISIN number: CA1389093040
2026-04-24 09:37:32 [WARNING ] core.dividend_service: Kein Ticker für CA1389093040 — übersprungen.
2026-04-24 09:37:32 [INFO    ] core.dividend_service: Dividenden-Update: CA1850534027
2026-04-24 09:37:33 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für CA1850534027: Invalid ISIN number: CA1850534027
2026-04-24 09:37:33 [WARNING ] core.dividend_service: Kein Ticker für CA1850534027 — übersprungen.
2026-04-24 09:37:33 [INFO    ] core.dividend_service: Dividenden-Update: CA21948L1040
2026-04-24 09:37:33 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für CA21948L1040: Invalid ISIN number: CA21948L1040
2026-04-24 09:37:33 [WARNING ] core.dividend_service: Kein Ticker für CA21948L1040 — übersprungen.
2026-04-24 09:37:33 [INFO    ] core.dividend_service: Dividenden-Update: CA22675G1028
2026-04-24 09:37:35 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: GREEUR"}}}
2026-04-24 09:37:35 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker GREEUR für CA22675G1028 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:37:35 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für CA22675G1028: Invalid ISIN number: CA22675G1028
2026-04-24 09:37:35 [WARNING ] core.dividend_service: Kein Ticker für CA22675G1028 — übersprungen.
2026-04-24 09:37:35 [INFO    ] core.dividend_service: Dividenden-Update: CA24380K4028
2026-04-24 09:37:36 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: MKTEUR"}}}
2026-04-24 09:37:36 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker MKTEUR für CA24380K4028 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:37:37 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für CA24380K4028: Invalid ISIN number: CA24380K4028
2026-04-24 09:37:37 [WARNING ] core.dividend_service: Kein Ticker für CA24380K4028 — übersprungen.
2026-04-24 09:37:37 [INFO    ] core.dividend_service: Dividenden-Update: CA24874B1085
2026-04-24 09:37:38 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: DNTCF"}}}
2026-04-24 09:37:38 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker DNTCF für CA24874B1085 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:37:38 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für CA24874B1085: Invalid ISIN number: CA24874B1085
2026-04-24 09:37:38 [WARNING ] core.dividend_service: Kein Ticker für CA24874B1085 — übersprungen.
2026-04-24 09:37:38 [INFO    ] core.dividend_service: Dividenden-Update: CA25381D2068
2026-04-24 09:37:39 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: KASHEUR"}}}
2026-04-24 09:37:39 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker KASHEUR für CA25381D2068 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:37:40 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für CA25381D2068: Invalid ISIN number: CA25381D2068
2026-04-24 09:37:40 [WARNING ] core.dividend_service: Kein Ticker für CA25381D2068 — übersprungen.
2026-04-24 09:37:40 [INFO    ] core.dividend_service: Dividenden-Update: CA29480N2068
2026-04-24 09:37:41 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: ERDEUR"}}}
2026-04-24 09:37:41 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker ERDEUR für CA29480N2068 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:37:41 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für CA29480N2068: Invalid ISIN number: CA29480N2068
2026-04-24 09:37:41 [WARNING ] core.dividend_service: Kein Ticker für CA29480N2068 — übersprungen.
2026-04-24 09:37:41 [INFO    ] core.dividend_service: Dividenden-Update: CA29877A2056
2026-04-24 09:37:42 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: TXXEUR"}}}
2026-04-24 09:37:43 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker TXXEUR für CA29877A2056 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:37:43 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für CA29877A2056: Invalid ISIN number: CA29877A2056
2026-04-24 09:37:43 [WARNING ] core.dividend_service: Kein Ticker für CA29877A2056 — übersprungen.
2026-04-24 09:37:43 [INFO    ] core.dividend_service: Dividenden-Update: CA30219M1059
2026-04-24 09:37:44 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: NFLDUSD"}}}
2026-04-24 09:37:44 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker NFLDUSD für CA30219M1059 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:37:45 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für CA30219M1059: Invalid ISIN number: CA30219M1059
2026-04-24 09:37:45 [WARNING ] core.dividend_service: Kein Ticker für CA30219M1059 — übersprungen.
2026-04-24 09:37:45 [INFO    ] core.dividend_service: Dividenden-Update: CA36150R1029
2026-04-24 09:37:46 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: 4G9"}}}
2026-04-24 09:37:46 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker 4G9 für CA36150R1029 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:37:46 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für CA36150R1029: Invalid ISIN number: CA36150R1029
2026-04-24 09:37:46 [WARNING ] core.dividend_service: Kein Ticker für CA36150R1029 — übersprungen.
2026-04-24 09:37:46 [INFO    ] core.dividend_service: Dividenden-Update: CA38018L2021
2026-04-24 09:37:48 [ERROR   ] yfinance: HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: GOCO1EUR"}}}
2026-04-24 09:37:48 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker GOCO1EUR für CA38018L2021 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:37:48 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für CA38018L2021: Invalid ISIN number: CA38018L2021
2026-04-24 09:37:48 [WARNING ] core.dividend_service: Kein Ticker für CA38018L2021 — übersprungen.
2026-04-24 09:37:48 [INFO    ] core.dividend_service: Dividenden-Update: CA4013393042
2026-04-24 09:37:49 [WARNING ] core.ticker_resolver: yfinance-Auflösung fehlgeschlagen für CA4013393042: Invalid ISIN number: CA4013393042
2026-04-24 09:37:49 [WARNING ] core.dividend_service: Kein Ticker für CA4013393042 — übersprungen.
2026-04-24 09:37:49 [INFO    ] core.dividend_service: Dividenden-Update: CA4104991076
2026-04-24 09:37:50 [ERROR   ] yfinance: HTTP Error 500: <!DOCTYPE html>
<html lang="en-us">
  <head>
    <meta http-equiv="content-type" content="text/html; charset=UTF-8">
    <meta charset="utf-8">
    <title>Yahoo</title>
    <meta name="viewport" content="width=device-width,initial-scale=1,minimal-ui">
    <meta http-equiv="X-UA-Compatible" content="IE=edge,chrome=1">
    <style>
      html {
          height: 100%;
      }
      body {
          background: #fafafc url(https://s.yimg.com/nn/img/sad-panda-201402200631.png) 50% 50%;
          background-size: cover;
          height: 100%;
          text-align: center;
          font: 300 18px "helvetica neue", helvetica, verdana, tahoma, arial, sans-serif;
          margin: 0;
      }
      table {
          height: 100%;
          width: 100%;
          table-layout: fixed;
          border-collapse: collapse;
          border-spacing: 0;
          border: none;
      }
      h1 {
          font-size: 42px;
          font-weight: 400;
          color: #400090;
      }
      p {
          color: #1A1A1A;
      }
      #message-1 {
          font-weight: bold;
          margin: 0;
      }
      #message-2 {
          display: inline-block;
          *display: inline;
          zoom: 1;
          max-width: 17em;
          _width: 17em;
      }
      </style>
      <script>
      
      </script>
  </head>
  <body>
  <!-- status code : 500 -->
  <!-- Unknown Host -->
  <!-- host machine: ats-ncache-api--production-ir2-5457b98f6c-n67vn -->
  <!-- timestamp: 1777016270.184 -->
  <!-- url: https://default.finance-yql-production.finance-k8s.omega.yahoo.com/v10/finance/quoteSummary/HCC/H?modules=financialData%2CquoteType%2CdefaultKeyStatistics%2CassetProfile%2CsummaryDetail&corsDomain=finance.yahoo.com&formatted=false&symbol=HCC%2FH&crumb=Rsv5G2H8P0h-->
  <script type="text/javascript">
    function buildUrl(url, parameters){
      var qs = [];
      for(var key in parameters) {
        var value = parameters[key];
        qs.push(encodeURIComponent(key) + "=" + encodeURIComponent(value));
      }
      url = url + "?" + qs.join('&');
      return url;
    }

    function generateBRBMarkup(site) {
      params.source = 'brb';
      generateBeaconMarkup(params);
      var englishHeader = 'Will be right back...';
      var englishMessage1 = 'Thank you for your patience.';
      var englishMessage2 = 'Our engineers are working quickly to resolve the issue.';
      var defaultLogoStyle = '';
      var siteDataMap = {
        'default': {
          logo: 'https://s.yimg.com/rz/p/yahoo_frontpage_en-US_s_f_p_205x58_frontpage.png',
          logoAlt: 'Yahoo Logo',
          logoStyle: defaultLogoStyle,
          header: englishHeader,
          message1: englishMessage1,
          message2: englishMessage2
        }
      };

      var siteDetails = siteDataMap['default'];

      document.write('<table><tbody><tr><td>');
      document.write('<div id="content">');
      document.write('<img src="' + siteDetails['logo'] + '" alt="' + siteDetails['logoAlt'] + '" style="' + siteDetails['logoStyle'] + '">');
      document.write('<h1 style="margin-top:20px;">' + siteDetails['header'] + '</h1>');
      document.write('<p id="message-1">' + siteDetails['message1'] + '</p>');
      document.write('<p id="message-2">' + siteDetails['message2'] + '</p>');
      document.write('</div>');
      document.write('</td></tr></tbody></table>');
    }

    function generateBeaconMarkup(params) {
        document.write('<img src="' + buildUrl('//geo.yahoo.com/b', params) + '" style="display:none;" width="0px" height="0px"/>');
        var beacon = new Image();
        beacon.src = buildUrl('//bcn.fp.yahoo.com/p', params);
    }

    var hostname = window.location.hostname;
    var device = 'desktop';
    var ynet = ('-' === '1');
    var time = new Date().getTime();
    var params = {
        s: '1197757129',
        t: time,
        err_url: document.URL,
        err: '500',
        test: '-',
        ats_host: 'ats-ncache-api--production-ir2-5457b98f6c-n67vn',
        rid: '-',
        message: 'Unknown Host'
    };

    if(ynet) {
        document.write('<div style="height: 5px; background-color: red;"></div>');
    }
    generateBRBMarkup(hostname, params);

  </script>
  <noscript>
  <table>
    <tbody>
      <tr>
        <td>
          <div id="englishContent">
            <h1 style="margin-top:20px;">Will be right back...</h1>
            <p id="message-1">Thank you for your patience.</p>
            <p id="message-2">Our engineers are working quickly to resolve the issue.</p>
          </div>
        </td>
      </tr>
    </tbody>
  </table>
  </noscript>
  </body>
</html>

2026-04-24 09:37:50 [WARNING ] core.ticker_resolver: OpenFIGI-Ticker HCC/H für CA4104991076 von yfinance nicht erkannt — verwerfe und versuche yfinance-Direktauflösung.
2026-04-24 09:37:51 [INFO    ] core.ticker_resolver: yfinance (Fallback): CA4104991076 → HCC-H.V (Börse: VAN)
2026-04-24 09:37:51 [INFO    ] core.sources.yfinance_source: Snapshot: CA4104991076 → Rendite None bps (0.00%), Frequenz None
2026-04-24 09:37:51 [INFO    ] core.dividend_service: CA4104991076: keine Dividende in 18 Monaten → yield=0, Abruf pausiert für 7 Tage.
2026-04-24 09:37:51 [ERROR   ] gui.tabs.universe_tab: Fehler im Batch-Worker.
Traceback (most recent call last):
  File "/home/luzy/workspace/openclaw-min/gui/tabs/universe_tab.py", line 269, in _batch_worker
    stats = update_batch(
            ^^^^^^^^^^^^^
  File "/home/luzy/workspace/openclaw-min/core/dividend_service.py", line 153, in update_batch
    return _run_batch(
           ^^^^^^^^^^^
  File "/home/luzy/workspace/openclaw-min/core/dividend_service.py", line 214, in _run_batch
    result = update_dividend_data(isin, db_path=db_path)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/luzy/workspace/openclaw-min/core/dividend_service.py", line 117, in update_dividend_data
    dividend_repository.set_skip_until(isin, db_path=db_path)
  File "/home/luzy/workspace/openclaw-min/db/dividend_repository.py", line 100, in set_skip_until
    conn.execute(
sqlite3.OperationalError: table dividend_data has no column named skip_until
(venv) luzy@luzy-NucBox-K8-Plus:~/workspace/openclaw-min$ 

