# Dateiname:     core/email_service.py
# Version:       2026-05-16-freq
# Abhängigkeiten (intern): keine
# Abhängigkeiten (extern): python-dotenv
"""
core/email_service.py

SMTP-E-Mail-Versand für HYPilot-Benachrichtigungen.

Neu 2026-05-16:
  Crossings-Tabelle enthält jetzt Spalte "Frequenz"
  (monatlich, quartalsweise, etc.) aus dividend_data.frequency.

Credentials ausschließlich via .env — niemals im Code.
Unterstützt STARTTLS (Port 587) und SSL (Port 465).
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)

# ── Frequenz-Anzeigenamen ─────────────────────────────────────────────────────

_FREQ_DISPLAY: dict[str, str] = {
    "monthly":     "monatlich",
    "quarterly":   "quartalsweise",
    "semi_annual": "halbjährlich",
    "annual":      "jährlich",
    "irregular":   "unregelmäßig",
}


def _get_recipients() -> list[str]:
    recipients = []
    for key in ("SMTP_TO_1", "SMTP_TO_2"):
        val = os.getenv(key, "").strip()
        if val:
            recipients.append(val)
    return recipients


def send_batch_summary(
    stats: dict[str, int],
    crossings: list[dict],
    run_label: str = "Automatischer Lauf",
) -> bool:
    """
    Sendet eine Zusammenfassung nach einem Batch-Lauf an beide Empfänger.

    Args:
        stats:      {'processed': N, 'updated': N, 'skipped': N}
        crossings:  Liste von Schwellwert-Überschreitungen
        run_label:  Bezeichnung des Laufs (z.B. "08:00 Lauf")

    Returns:
        True bei Erfolg, False bei Fehler.
    """
    host      = os.getenv("SMTP_HOST", "")
    port      = int(os.getenv("SMTP_PORT", "587"))
    user      = os.getenv("SMTP_USER", "")
    password  = os.getenv("SMTP_PASSWORD", "")
    from_addr = os.getenv("SMTP_FROM", user)
    recipients = _get_recipients()

    if not all([host, user, password, recipients]):
        logger.warning(
            "E-Mail nicht konfiguriert — "
            "SMTP_HOST, SMTP_USER, SMTP_PASSWORD, SMTP_TO_* prüfen."
        )
        return False

    subject = f"HYPilot — Dividenden-Update: {run_label}"
    body    = _build_body(stats, crossings, run_label)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = from_addr
    msg["To"]      = ", ".join(recipients)
    msg.attach(MIMEText(body, "html", "utf-8"))

    try:
        context = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=context) as server:
                server.login(user, password)
                server.sendmail(from_addr, recipients, msg.as_string())
        else:
            with smtplib.SMTP(host, port) as server:
                server.ehlo()
                server.starttls(context=context)
                server.login(user, password)
                server.sendmail(from_addr, recipients, msg.as_string())

        logger.info(
            "E-Mail gesendet an %d Empfänger: %s",
            len(recipients), run_label,
        )
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP-Authentifizierung fehlgeschlagen.")
        return False
    except Exception:
        logger.exception("E-Mail-Versand fehlgeschlagen.")
        return False


def _build_body(
    stats: dict[str, int],
    crossings: list[dict],
    run_label: str,
) -> str:
    """Erstellt HTML-Body der Zusammenfassung."""
    from datetime import datetime
    now = datetime.now().strftime("%d.%m.%Y %H:%M")

    crossing_rows = ""
    if crossings:
        for c in crossings:
            old_pct = f"{c['yield_bps_old']/100:.2f}%" if c["yield_bps_old"] else "—"
            new_pct = f"{c['yield_bps_new']/100:.2f}%"
            arrow   = "▲" if c["direction"] == "up" else "▼"
            color   = "#2e7d32" if c["direction"] == "up" else "#c62828"
            freq    = _FREQ_DISPLAY.get(c.get("frequency") or "", "—")
            crossing_rows += f"""
            <tr>
              <td>{c['isin']}</td>
              <td>{c['display_name']}</td>
              <td>{old_pct}</td>
              <td style="color:{color};font-weight:bold">{arrow} {new_pct}</td>
              <td>{freq}</td>
            </tr>"""
    else:
        crossing_rows = (
            '<tr><td colspan="5" style="color:gray">'
            'Keine Schwellwert-Überschreitungen</td></tr>'
        )

    return f"""
    <html><body style="font-family:sans-serif;max-width:700px">
    <h2>HYPilot — Dividenden-Update</h2>
    <p><strong>{run_label}</strong> — {now}</p>

    <h3>Statistik</h3>
    <table border="1" cellpadding="6" cellspacing="0"
           style="border-collapse:collapse">
      <tr><th>Verarbeitet</th><th>Aktualisiert</th><th>Übersprungen</th></tr>
      <tr>
        <td>{stats.get('processed',0)}</td>
        <td>{stats.get('updated',0)}</td>
        <td>{stats.get('skipped',0)}</td>
      </tr>
    </table>

    <h3>10%-Schwellwert-Überschreitungen</h3>
    <table border="1" cellpadding="6" cellspacing="0"
           style="border-collapse:collapse">
      <tr>
        <th>ISIN</th><th>Name</th>
        <th>Alt</th><th>Neu</th><th>Frequenz</th>
      </tr>
      {crossing_rows}
    </table>
    </body></html>
    """
