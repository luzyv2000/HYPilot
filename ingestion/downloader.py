import requests
import hashlib
import time
from pathlib import Path
from datetime import datetime

# === Konfiguration ===
URL = "https://assets.traderepublic.com/assets/files/DE/Instrument_Universe_DE_de.pdf"

BASE_PATH = Path("/home/luzy/workspace/openclaw-min")
DATA_PATH = BASE_PATH / "data"
PDF_PATH = DATA_PATH / "instrument_universe.pdf"
HASH_PATH = DATA_PATH / "instrument_universe.hash"


# === Hilfsfunktionen ===

def ensure_data_dir():
    DATA_PATH.mkdir(parents=True, exist_ok=True)


def calculate_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def load_existing_hash():
    if not HASH_PATH.exists():
        return None

    with open(HASH_PATH, "r") as f:
        return f.read().strip()


def save_hash(hash_value: str):
    with open(HASH_PATH, "w") as f:
        f.write(hash_value)


def archive_old_pdf():
    if not PDF_PATH.exists():
        return

    timestamp = datetime.now().strftime("%Y-%m-%d")
    archive_name = f"{timestamp}_Instrument_Universe_DE_de.pdf"
    archive_path = DATA_PATH / archive_name

    PDF_PATH.rename(archive_path)


# === Download mit Retry ===

def download_with_retry(url, retries=3, timeout=20):
    for attempt in range(retries):
        try:
            response = requests.get(url, timeout=timeout)

            if response.status_code == 200:
                return response.content

            print(f"[WARN] HTTP {response.status_code}")

        except Exception as e:
            print(f"[WARN] Versuch {attempt + 1} fehlgeschlagen: {e}")

        time.sleep(2)

    return None


# === Hauptlogik ===

def main():
    print("[INFO] Starte Download-Check...")
    ensure_data_dir()

    content = download_with_retry(URL)

    if not content:
        print("[ERROR] Download endgültig fehlgeschlagen")
        return False

    new_hash = calculate_hash(content)
    old_hash = load_existing_hash()

    if new_hash == old_hash:
        print("[INFO] PDF unverändert – kein Download nötig")
        return True

    print("[INFO] Neue Version erkannt – archiviere alte Datei")

    archive_old_pdf()

    with open(PDF_PATH, "wb") as f:
        f.write(content)

    save_hash(new_hash)

    print("[INFO] Neues PDF gespeichert")

    return True


if __name__ == "__main__":
    success = main()

    # wichtig für Runner (Return-Code)
    if not success:
        exit(1)
