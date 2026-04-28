# config.py
# Datum: 2026-04-28

from pathlib import Path
import os
from dotenv import load_dotenv
load_dotenv()

DB_PATH = Path(os.getenv("HYPILOT_DB_PATH",
               "/home/luzy/workspace/openclaw-min/db/hypilot.db"))
OPENFIGI_API_KEY = os.getenv("OPENFIGI_API_KEY", "")
