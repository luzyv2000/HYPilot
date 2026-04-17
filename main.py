from agent.core import query_llm
from tools.finance import resolve_symbol, get_stock_data
from tools.analysis import score_stock


def analyze_stock(query: str):
    symbol = resolve_symbol(query)
    data = get_stock_data(symbol)
    analysis = score_stock(data)

    return {
        "data": data,
        "analysis": analysis
    }


def agent(prompt: str):
    if "aktie" in prompt.lower() or "stock" in prompt.lower():
        result = analyze_stock(prompt)
        return result

    return query_llm(prompt)


if __name__ == "__main__":
    while True:
        user_input = input("\n> ")

        if user_input.lower() in ["exit", "quit"]:
            break

        result = agent(user_input)
        print(result)
