import subprocess
from datetime import datetime
from pathlib import Path


BASE_PATH = Path("/home/luzy/workspace/openclaw-min")
LOG_PATH = BASE_PATH / "logs"
LOG_FILE = LOG_PATH / "update.log"


def ensure_log_dir():
    LOG_PATH.mkdir(parents=True, exist_ok=True)


def log(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"

    print(line)

    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def run_command(cmd: list):
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )

        log(f"CMD: {' '.join(cmd)}")

        if result.stdout:
            log(result.stdout.strip())

        if result.stderr:
            log(f"[STDERR] {result.stderr.strip()}")

        return result.returncode == 0

    except Exception as e:
        log(f"[ERROR] Exception: {e}")
        return False

def main():
    ensure_log_dir()

    log("=== START UPDATE ===")

    # Schritt 1: Download
    success_download = run_command([
        "python",
        "-m",
        "ingestion.downloader"
    ])

    pdf_path = BASE_PATH / "data" / "instrument_universe.pdf"

    if not success_download:
        if pdf_path.exists():
            log("[WARN] Download fehlgeschlagen → verwende vorhandenes PDF")
        else:
            log("[FATAL] Kein PDF vorhanden → Abbruch")
            return

    # Schritt 2: Update
    success_update = run_command([
        "python",
        "-m",
        "ingestion.updater"
    ])

    if not success_update:
        log("[ERROR] DB Update fehlgeschlagen")
        return

    log("=== UPDATE COMPLETE ===\n")

if __name__ == "__main__":
    main()
