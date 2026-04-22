# Dateiname:     main.py
# Version:       2026-04-22
# Abhängigkeiten (intern): agent.core, tools.finance,
#                          core.dividend_service, analysis.engine
# Abhängigkeiten (extern): keine
"""
main.py

OpenClaw-Agent: Routing zwischen LLM und HYPilot-Analyse.

Analyse-Routing:
  "aktie" / "stock" / "dividende" im Prompt
    → dividend_service.update_dividend_data() + analysis.engine.score_instrument()
  alles andere
    → LLM (Ollama)
"""

from __future__ import annotations

import logging

from agent.core import query_llm
from core.dividend_service import update_dividend_data
from analysis.engine import score_instrument

logger = logging.getLogger(__name__)


def analyze_stock(isin: str) -> dict:
    """
    Vollständige Dividenden-Analyse für eine ISIN.
    Aktualisiert zuerst die Dividendendaten, dann bewertet.
    """
    snapshot = update_dividend_data(isin)
    if snapshot is None:
        return {"error": f"Keine Dividendendaten für {isin}"}

    score = score_instrument(isin)
    if score is None:
        return {"error": f"Scoring fehlgeschlagen für {isin}"}

    return {
        "isin": isin,
        "yield_bps": snapshot.yield_bps,
        "frequency": snapshot.frequency,
        "score": score.total,
        "rating": score.rating,
        "notes": score.notes,
    }


def agent(prompt: str) -> object:
    """
    Routing:
      - ISIN erkannt           → Dividenden-Analyse
      - Schlüsselwort erkannt  → Hinweis zur ISIN-Eingabe
      - alles andere           → LLM
    """
    import re
    isin_match = re.search(r"\b[A-Z]{2}[A-Z0-9]{10}\b", prompt)
    if isin_match:
        return analyze_stock(isin_match.group(0))

    keywords = ("aktie", "stock", "dividende", "analyse")
    if any(k in prompt.lower() for k in keywords):
        return "Bitte ISIN angeben, z.B.: US7561091049"

    return query_llm(prompt)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    )
    while True:
        user_input = input("\n> ").strip()
        if user_input.lower() in ("exit", "quit"):
            break
        if not user_input:
            continue
        result = agent(user_input)
        print(result)
