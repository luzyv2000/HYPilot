import yfinance as yf


TICKER_MAP = {
    "tesla": "TSLA",
    "apple": "AAPL",
    "microsoft": "MSFT",
    "amazon": "AMZN",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "meta": "META",
    "nvidia": "NVDA",
}


def resolve_symbol(query: str) -> str:
    q = query.lower()

    for name, ticker in TICKER_MAP.items():
        if name in q:
            return ticker

    words = query.upper().split()
    for w in words:
        if len(w) <= 5 and w.isalpha():
            return w

    raise ValueError("Kein gültiger Ticker erkannt")


def get_stock_data(symbol: str) -> dict:
    stock = yf.Ticker(symbol)
    info = stock.info

    return {
        "name": info.get("longName"),
        "symbol": symbol,
        "price": info.get("currentPrice"),
        "pe_ratio": info.get("trailingPE"),
        "revenue_growth": info.get("revenueGrowth"),
        "profit_margin": info.get("profitMargins"),
        "debt_to_equity": info.get("debtToEquity"),
    }


def score_stock(data: dict) -> dict:
    score = 0
    reasons = []

    pe = data.get("forwardPE")
    growth = data.get("revenueGrowth")
    margin = data.get("profitMargins")

    # 🔹 Bewertung
    if pe:
        if pe < 15:
            score += 25
            reasons.append("günstige Bewertung")
        elif pe < 30:
            score += 15
            reasons.append("moderate Bewertung")
        else:
            score += 5
            reasons.append("hohe Bewertung")

    # 🔹 Wachstum
    if growth:
        if growth > 0.2:
            score += 25
            reasons.append("starkes Wachstum")
        elif growth > 0.05:
            score += 15
            reasons.append("solides Wachstum")
        else:
            score += 5
            reasons.append("schwaches Wachstum")

    # 🔹 Profitabilität
    if margin:
        if margin > 0.2:
            score += 25
            reasons.append("hohe Marge")
        elif margin > 0.1:
            score += 15
            reasons.append("mittlere Marge")
        else:
            score += 5
            reasons.append("niedrige Marge")

    # 🔹 Datenverfügbarkeit
    if data.get("price"):
        score += 10

    return {
        "score": score,
        "reasons": reasons
    }


def classify(score: int) -> str:
    if score >= 70:
        return "🟢 Attraktiv"
    elif score >= 50:
        return "🟡 Neutral"
    else:
        return "🔴 Riskant"


def analyze_stock(query: str) -> str:
    symbol = resolve_symbol(query)
    data = get_stock_data(symbol)

    if not data["price"]:
        return f"Keine Daten für {symbol} verfügbar"

    scoring = score_stock(data)
    label = classify(scoring["score"])

    return (
        f"Aktie: {data['name']} ({symbol})\n"
        f"Preis: {data['price']} USD\n"
        f"Sektor: {data['sector']}\n\n"
        f"Score: {scoring['score']}/100 → {label}\n"
        f"Gründe: {', '.join(scoring['reasons'])}\n\n"
        f"Kennzahlen:\n"
        f"- KGV (forward): {data['forwardPE']}\n"
        f"- Wachstum: {data['revenueGrowth']}\n"
        f"- Marge: {data['profitMargins']}"
    )
