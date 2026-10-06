from datetime import date
from math import isfinite
from statistics import mean, pstdev

from app.api.schema.financial_quality import (
    AnnualFinancials,
    CompositeScore,
    FinancialQualityResponse,
    ScoreComponent,
)


def number(value: object) -> float | None:
    try:
        parsed = float(value)
        return parsed if isfinite(parsed) else None
    except (TypeError, ValueError, OverflowError):
        return None


def ratio(
    numerator: float | None, denominator: float | None, scale: float = 1
) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return round(numerator / denominator * scale, 4)


def align_annual_statements(
    statements: dict[str, list[dict]],
) -> list[AnnualFinancials]:
    indexed: dict[str, dict[str, dict]] = {}
    for kind, rows in statements.items():
        indexed[kind] = {}
        for row in rows:
            fiscal_date = row.get("fiscalDateEnding")
            try:
                date.fromisoformat(fiscal_date)
            except (TypeError, ValueError):
                continue
            indexed[kind].setdefault(fiscal_date, row)
    result = []
    for fiscal_date in sorted(indexed.get("INCOME_STATEMENT", {}))[-6:]:
        income = indexed["INCOME_STATEMENT"][fiscal_date]
        balance = indexed.get("BALANCE_SHEET", {}).get(fiscal_date, {})
        cashflow = indexed.get("CASH_FLOW", {}).get(fiscal_date, {})
        earnings = indexed.get("EARNINGS", {}).get(fiscal_date, {})
        currency = income.get("reportedCurrency")
        # Never divide or add statement amounts expressed in different currencies.
        if balance.get("reportedCurrency") != currency:
            balance = {}
        if cashflow.get("reportedCurrency") != currency:
            cashflow = {}
        revenue = number(income.get("totalRevenue"))
        gross = number(income.get("grossProfit"))
        operating = number(income.get("operatingIncome"))
        net = number(income.get("netIncome"))
        ocf = number(cashflow.get("operatingCashflow"))
        capex = number(cashflow.get("capitalExpenditures"))
        fcf = ocf - abs(capex) if ocf is not None and capex is not None else None
        equity = number(balance.get("totalShareholderEquity"))
        assets = number(balance.get("totalAssets"))
        debt = number(balance.get("shortLongTermDebtTotal"))
        if debt is None:
            short = number(balance.get("shortTermDebt"))
            long = number(balance.get("longTermDebtNoncurrent"))
            debt = short + long if short is not None and long is not None else None
        cash = number(balance.get("cashAndShortTermInvestments"))
        if cash is None:
            cash = number(balance.get("cashAndCashEquivalentsAtCarryingValue"))
        current_assets = number(balance.get("totalCurrentAssets"))
        current_liabilities = number(balance.get("totalCurrentLiabilities"))
        result.append(
            AnnualFinancials(
                fiscal_date=fiscal_date,
                currency=currency,
                revenue=revenue,
                gross_profit=gross,
                operating_income=operating,
                net_income=net,
                eps=number(earnings.get("reportedEPS")),
                operating_cash_flow=ocf,
                capital_expenditures=capex,
                free_cash_flow=fcf,
                equity=equity,
                total_assets=assets,
                total_debt=debt,
                cash=cash,
                current_assets=current_assets,
                current_liabilities=current_liabilities,
                gross_margin_pct=ratio(gross, revenue, 100),
                operating_margin_pct=ratio(operating, revenue, 100),
                net_margin_pct=ratio(net, revenue, 100),
                fcf_margin_pct=ratio(fcf, revenue, 100),
                roe_pct=ratio(net, equity, 100),
                roa_pct=ratio(net, assets, 100),
                debt_equity=ratio(debt, equity),
                current_ratio=ratio(current_assets, current_liabilities),
                cash_conversion=ratio(ocf, net),
            )
        )
    return result


def cagr(rows: list[AnnualFinancials], field: str, years: int) -> float | None:
    if len(rows) < years + 1:
        return None
    window = rows[-years - 1 :]
    if (
        not _consecutive(window)
        or not window[-1].currency
        or len({row.currency for row in window}) != 1
    ):
        return None
    first, last = getattr(window[0], field), getattr(window[-1], field)
    if first is None or last is None or first <= 0 or last <= 0:
        return None
    elapsed = (
        date.fromisoformat(window[-1].fiscal_date)
        - date.fromisoformat(window[0].fiscal_date)
    ).days / 365.25
    return round(((last / first) ** (1 / elapsed) - 1) * 100, 2)


def _consecutive(rows: list[AnnualFinancials]) -> bool:
    return all(
        300
        <= (date.fromisoformat(b.fiscal_date) - date.fromisoformat(a.fiscal_date)).days
        <= 430
        for a, b in zip(rows, rows[1:])
    )


def _scaled(value: float | None, low: float, high: float) -> float | None:
    return (
        round(max(0, min(100, (value - low) / (high - low) * 100)), 2)
        if value is not None
        else None
    )


def _average(values: list[float | None]) -> float | None:
    available = [value for value in values if value is not None]
    return (
        round(mean(available), 2)
        if len(available) == len(values) and available
        else None
    )


def _composite(
    parts: list[tuple[str, float | None, str]], allowed: bool
) -> CompositeScore:
    weight = 1 / len(parts)
    components = [
        ScoreComponent(name=name, score=score, weight=weight, method=method)
        for name, score, method in parts
    ]
    coverage = sum(part.weight for part in components if part.score is not None)
    # Missing dimensions do not silently receive a neutral score or shift weights.
    score = (
        round(sum(part.score * part.weight for part in components), 1)
        if allowed and all(part.score is not None for part in components)
        else None
    )
    return CompositeScore(
        score=score, coverage_pct=round(coverage * 100), components=components
    )


def build_financial_quality(
    rows: list[AnnualFinancials], sector: str | None
) -> FinancialQualityResponse:
    rows = sorted(rows, key=lambda row: row.fiscal_date)
    last = rows[-1] if rows else None
    recent = rows[-3:]
    valid_history = (
        len(recent) == 3
        and _consecutive(recent)
        and bool(last.currency)
        and len({row.currency for row in recent}) == 1
    )
    unsupported_sector = bool(
        sector and any(word in sector.lower() for word in ("financial", "real estate"))
    )
    allowed = valid_history and not unsupported_sector
    revenue_growth = []
    for a, b in zip(rows, rows[1:]):
        if (
            _consecutive([a, b])
            and a.currency == b.currency
            and a.revenue is not None
            and a.revenue > 0
            and b.revenue is not None
        ):
            revenue_growth.append((b.revenue / a.revenue - 1) * 100)
    growth_consistency = (
        sum(value > 0 for value in revenue_growth) / len(revenue_growth) * 100
        if len(revenue_growth) >= 2
        else None
    )
    margin_change = (
        last.operating_margin_pct - recent[0].operating_margin_pct
        if valid_history
        and last.operating_margin_pct is not None
        and recent[0].operating_margin_pct is not None
        else None
    )
    margins = [row.gross_margin_pct for row in recent]
    margin_std = (
        pstdev(margins)
        if valid_history and all(value is not None for value in margins)
        else None
    )
    net_debt_change = None
    if valid_history and all(
        value is not None
        for row in (recent[0], last)
        for value in (row.total_debt, row.cash)
    ):
        net_debt_change = (last.total_debt - last.cash) - (
            recent[0].total_debt - recent[0].cash
        )
    revenue3, revenue5 = cagr(rows, "revenue", 3), cagr(rows, "revenue", 5)
    eps3, eps5 = cagr(rows, "eps", 3), cagr(rows, "eps", 5)
    profitability = (
        _average(
            [
                _scaled(last.net_margin_pct, 0, 20),
                _scaled(last.roe_pct, 0, 20),
                _scaled(last.roa_pct, 0, 10),
            ]
        )
        if last
        else None
    )
    balance = (
        _average([_scaled(last.debt_equity, 2, 0), _scaled(last.current_ratio, 0.5, 2)])
        if last
        else None
    )
    cash = (
        _average(
            [_scaled(last.fcf_margin_pct, 0, 20), _scaled(last.cash_conversion, 0, 1)]
        )
        if last
        else None
    )
    consistent = (
        mean(
            [
                100 if row.net_income > 0 and row.free_cash_flow > 0 else 0
                for row in recent
            ]
        )
        if valid_history
        and all(
            row.net_income is not None and row.free_cash_flow is not None
            for row in recent
        )
        else None
    )
    quality = _composite(
        [
            (
                "Profitability",
                profitability,
                "Mean of annual net margin /20%, ROE /20%, ROA /10%, clipped 0-100.",
            ),
            (
                "Balance sheet",
                balance,
                "Mean of debt/equity (2 to 0) and current ratio (0.5 to 2), clipped 0-100.",
            ),
            (
                "Cash generation",
                cash,
                "Mean of FCF margin /20% and operating cash flow/net income /1, clipped 0-100.",
            ),
            (
                "Consistency",
                consistent,
                "Percentage of last three fiscal years with positive profit AND free cash flow.",
            ),
        ],
        allowed,
    )
    growth = _composite(
        [
            (
                "Revenue growth",
                _scaled(revenue3, 0, 20),
                "Three-year revenue CAGR, 0% to 20%, clipped 0-100.",
            ),
            (
                "EPS growth",
                _scaled(eps3, 0, 20),
                "Three-year reported EPS CAGR, positive endpoints only, 0% to 20%.",
            ),
            (
                "Margin trend",
                _scaled(margin_change, -5, 5),
                "Operating margin change across last three years, -5 to +5 percentage points.",
            ),
            (
                "Growth consistency",
                growth_consistency,
                "Percentage of valid annual transitions with positive revenue growth.",
            ),
        ],
        allowed,
    )
    moat_evidence = []
    moat = "insufficient_evidence"
    if (
        valid_history
        and margin_std is not None
        and all(row.roe_pct is not None for row in recent)
        and not unsupported_sector
    ):
        supportive = (
            mean(margins) >= 40
            and margin_std <= 5
            and all(row.roe_pct >= 15 for row in recent)
        )
        moat = "supportive_proxies" if supportive else "mixed_proxies"
        moat_evidence = [
            f"Three-year average gross margin: {mean(margins):.2f}%.",
            f"Gross-margin standard deviation: {margin_std:.2f} percentage points.",
            f"Three-year minimum ROE: {min(row.roe_pct for row in recent):.2f}%.",
        ]
    warnings = [
        "Quality/growth scores are unvalidated absolute-threshold heuristics, not probabilities or proven return predictors.",
        "Reported annual statements may be restated; these are not point-in-time backtest datasets. ROE/ROA use year-end balances.",
        "Moat proxies cannot establish switching costs, brand strength or a durable competitive advantage. No filings were retrieved.",
        "EPS growth uses provider reported EPS; historical share splits and restatements should be checked before relying on it.",
    ]
    if not valid_history:
        warnings.append(
            "At least three consecutive same-currency annual statements are required for scores; three-year CAGR needs four annual observations."
        )
    if unsupported_sector:
        warnings.append(
            "Financial/real-estate companies are not scored by this general industrial-company formula."
        )
    return FinancialQualityResponse(
        years_available=len(rows),
        quality=quality,
        growth=growth,
        revenue_cagr_3y_pct=revenue3,
        revenue_cagr_5y_pct=revenue5,
        eps_cagr_3y_pct=eps3,
        eps_cagr_5y_pct=eps5,
        operating_margin_change_pp=round(margin_change, 2)
        if margin_change is not None
        else None,
        net_debt_change=net_debt_change,
        positive_revenue_growth_pct=growth_consistency,
        gross_margin_std_pp=round(margin_std, 2) if margin_std is not None else None,
        moat_label=moat,
        moat_evidence=moat_evidence,
        warnings=warnings,
    )
