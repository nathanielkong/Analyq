import re
from app.api.schema.stock import StockSearchResultResponse


def instrument_context(stock: StockSearchResultResponse) -> dict[str, object]:
    is_fund = stock.type.upper() in {"ETF", "ETN", "FUND"} or bool(
        re.search(r"\b(?:ETF|ETN|exchange.traded fund)\b", stock.name, re.I)
    )
    leverage = re.search(r"\b([2-9])x\b", stock.name, re.I) if is_fund else None
    return {
        "kind": "fund" if is_fund else "company",
        "classification_source": "Provider instrument type and listed security name",
        "leverage_in_name": int(leverage.group(1)) if leverage else None,
        "daily_in_name": bool(re.search(r"\bdaily\b", stock.name, re.I))
        if is_fund
        else False,
        "note": (
            "This is a fund, not an operating company. Company financial statements, "
            "revenue growth and company quality scores do not apply. Fund holdings, "
            "fees, prospectus, benchmark and NAV are not collected by this pipeline. "
            "For leveraged funds, daily-reset compounding can make multi-day returns "
            "differ substantially from a simple multiple. Confirm specific objectives "
            "in the issuer's prospectus; do not infer the benchmark from the ticker."
            if is_fund
            else "Company fundamentals are requested where the provider supplies them."
        ),
    }
