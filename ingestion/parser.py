import pdfplumber
import re
from pathlib import Path


PDF_PATH = Path("/home/luzy/workspace/openclaw-min/data/raw_pdfs/Instrument_Universe_DE_de.pdf")


ISIN_PATTERN = re.compile(r"\b[A-Z]{2}[A-Z0-9]{10}\b")

# WKN = genau 6 Zeichen, oft Großbuchstaben/Zahlen
WKN_PATTERN = re.compile(r"\b[A-Z0-9]{6}\b")


def extract_isin(line: str):
    match = ISIN_PATTERN.search(line)
    return match.group(0) if match else None


def extract_wkn(line: str, isin: str):
    matches = WKN_PATTERN.findall(line)

    for m in matches:
        if m != isin:  # nicht die ISIN selbst
            return m

    return None


def clean_name(line: str, isin: str, wkn: str):
    name = line

    # ISIN und WKN entfernen
    name = name.replace(isin, "")
    if wkn:
        name = name.replace(wkn, "")

    # Anführungszeichen entfernen
    name = name.replace('"', "").replace("'", "")

    # führende Sonderzeichen entfernen (z.B. $, -, etc.)
    name = re.sub(r"^[^A-Za-z0-9]+", "", name)

    # mehrere Leerzeichen reduzieren
    name = re.sub(r"\s{2,}", " ", name)

    return name.strip()


def is_valid_entry(name: str):
    # einfache Filter gegen Müll
    if len(name) < 3:
        return False

    # keine reinen Kategorien/Wörter
    blacklist = ["ETF", "Index", "Fund", "Swap"]
    if name in blacklist:
        return False

    return True


def parse_pdf():
    if not PDF_PATH.exists():
        raise FileNotFoundError(f"PDF nicht gefunden: {PDF_PATH}")

    instruments = []
    seen_isins = set()

    print("[INFO] Starte PDF-Parsing...")

    with pdfplumber.open(PDF_PATH) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text()

            if not text:
                continue

            lines = text.split("\n")

            for line in lines:
                isin = extract_isin(line)

                if not isin:
                    continue

                if isin in seen_isins:
                    continue  # Duplikate vermeiden

                wkn = extract_wkn(line, isin)
                name = clean_name(line, isin, wkn)

                if not is_valid_entry(name):
                    continue

                instruments.append({
                    "name": name,
                    "isin": isin,
                    "wkn": wkn
                })

                seen_isins.add(isin)

            if page_num % 20 == 0:
                print(f"[INFO] Seite {page_num} verarbeitet...")

    print(f"[INFO] Parsing abgeschlossen: {len(instruments)} eindeutige Einträge")

    return instruments


if __name__ == "__main__":
    data = parse_pdf()

    for item in data[:10]:
        print(item)
