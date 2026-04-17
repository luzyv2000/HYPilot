import yfinance as yf
from typing import Dict

from core.data_requirements import collect_required_fields


FIELD_MAPPING = {
    "pe_ratio": "trailingPE",
    "forward_pe": "forwardPE",
    "dividend_yield": "dividendYield",
    "profit_margin": "profitMargins",
}


def get_stock_data(symbol: str) -> Dict:
    stock = yf.Ticker(symbol)
    info = stock.info

    required_fields = collect_required_fields()

    data = {}

    for field in required_fields:
        yahoo_key = FIELD_MAPPING.get(field)

        if yahoo_key:
            data[field] = info.get(yahoo_key)
        else:
            data[field] = None  # bewusst sichtbar

    return data
