from agent.core import query_llm
from tools.finance import resolve_symbol, get_stock_data
from core.feature_engine import run_features


def analyze_stock(query: str):
    """
    Führt eine vollständige Aktienanalyse durch:
    - Symbol auflösen
    - Daten laden (Feature-basiert)
    - Feature-Engine ausführen
    """
    symbol = resolve_symbol(query)
    data = get_stock_data(symbol)
    analysis = run_features(data)

    return {
        "symbol": symbol,
        "data": data,
        "analysis": analysis
    }


def agent(prompt: str):
    """
    Routing:
    - Aktienanfragen → Analyse
    - alles andere → LLM
    """
    if "aktie" in prompt.lower() or "stock" in prompt.lower():
        return analyze_stock(prompt)

    return query_llm(prompt)


if __name__ == "__main__":
    while True:
        user_input = input("\n> ")

        if user_input.lower() in ["exit", "quit"]:
            break

        result = agent(user_input)
        print(result)
