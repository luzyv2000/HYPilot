import yfinance as yf


def get_stock_price(symbol: str) -> float:
    stock = yf.Ticker(symbol)
    data = stock.history(period="1d")

    if data.empty:
        raise ValueError("Keine Daten gefunden")

    return float(data["Close"].iloc[-1])


def get_stock_info(symbol: str) -> dict:
    stock = yf.Ticker(symbol)
    info = stock.info

    return {
        "name": info.get("longName"),
        "sector": info.get("sector"),
        "marketCap": info.get("marketCap"),
        "forwardPE": info.get("forwardPE"),
    }
