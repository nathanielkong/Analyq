import json
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.core.config import settings
from app.clients.errors import (
    MarketDataError,
    MarketDataRateLimitError,
    StockSymbolNotFoundError,
)


@dataclass(frozen=True)
class AlphaVantageQuote:
    symbol: str
    price: float
    change: float | None
    change_percent: float | None
    volume: int | None
    latest_trading_day: str | None
    previous_close: float | None
    open: float | None
    high: float | None
    low: float | None


@dataclass(frozen=True)
class AlphaVantageSearchResult:
    symbol: str
    name: str
    type: str
    region: str
    currency: str
    match_score: float | None


@dataclass(frozen=True)
class AlphaVantageDailyBar:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True)
class AlphaVantageNewsTopic:
    name: str
    relevance_score: float | None


@dataclass(frozen=True)
class AlphaVantageNewsArticle:
    title: str
    summary: str
    url: str
    source: str
    source_domain: str | None
    published_at: str
    authors: list[str]
    topics: list[AlphaVantageNewsTopic]
    overall_sentiment_score: float | None
    overall_sentiment_label: str | None
    ticker_relevance_score: float | None
    ticker_sentiment_score: float | None
    ticker_sentiment_label: str | None


@dataclass(frozen=True)
class AlphaVantageTickerSentiment:
    ticker: str
    relevance_score: float | None
    sentiment_score: float | None
    sentiment_label: str | None


@dataclass(frozen=True)
class AlphaVantageMarketNewsArticle:
    title: str
    url: str
    source: str
    published_at: str
    ticker_sentiments: list[AlphaVantageTickerSentiment]


@dataclass(frozen=True)
class AlphaVantageMarketMover:
    ticker: str
    price: float | None
    change_amount: float | None
    change_percentage: float | None
    volume: int | None


@dataclass(frozen=True)
class AlphaVantageMarketMovers:
    last_updated: str | None
    top_gainers: list[AlphaVantageMarketMover]
    top_losers: list[AlphaVantageMarketMover]
    most_actively_traded: list[AlphaVantageMarketMover]


@dataclass(frozen=True)
class AlphaVantageCompanyOverview:
    symbol: str
    asset_type: str | None
    name: str | None
    description: str | None
    exchange: str | None
    currency: str | None
    country: str | None
    sector: str | None
    industry: str | None
    fiscal_year_end: str | None
    latest_quarter: str | None
    market_capitalization: int | None
    ebitda: int | None
    pe_ratio: float | None
    trailing_pe: float | None
    forward_pe: float | None
    peg_ratio: float | None
    price_to_sales_ttm: float | None
    price_to_book: float | None
    ev_to_revenue: float | None
    ev_to_ebitda: float | None
    eps: float | None
    diluted_eps_ttm: float | None
    dividend_yield: float | None
    profit_margin: float | None
    operating_margin_ttm: float | None
    return_on_assets_ttm: float | None
    return_on_equity_ttm: float | None
    revenue_ttm: int | None
    gross_profit_ttm: int | None
    quarterly_earnings_growth_yoy: float | None
    quarterly_revenue_growth_yoy: float | None
    analyst_target_price: float | None
    beta: float | None
    high_52_week: float | None
    low_52_week: float | None


@dataclass(frozen=True)
class AlphaVantageBalanceSheetSnapshot:
    fiscal_date_ending: str
    reported_currency: str | None
    total_assets: int | None
    total_current_assets: int | None
    cash_and_short_term_investments: int | None
    total_current_liabilities: int | None
    total_liabilities: int | None
    short_term_debt: int | None
    long_term_debt: int | None
    long_term_debt_noncurrent: int | None
    total_shareholder_equity: int | None


@dataclass(frozen=True)
class AlphaVantageCashFlowSnapshot:
    fiscal_date_ending: str
    reported_currency: str | None
    operating_cash_flow: int | None
    capital_expenditures: int | None
    dividend_payout: int | None
    share_repurchases: int | None


class AlphaVantageClient:
    base_url = "https://www.alphavantage.co/query"
    minimum_request_interval_seconds = 1.5
    _request_lock = Lock()
    _last_request_started_at = 0.0

    def get_quote(self, symbol: str) -> AlphaVantageQuote:
        normalized_symbol = symbol.strip().upper()
        payload = self._get_json(
            {
                "function": "GLOBAL_QUOTE",
                "symbol": normalized_symbol,
            }
        )

        if "Error Message" in payload:
            raise StockSymbolNotFoundError(f"Stock symbol {normalized_symbol} was not found.")

        if "Note" in payload or "Information" in payload:
            message = payload.get("Note") or payload.get("Information")
            raise _build_provider_message_error(str(message))

        quote = payload.get("Global Quote", {})

        if not quote or not quote.get("05. price"):
            raise StockSymbolNotFoundError(f"Stock symbol {normalized_symbol} was not found.")

        return AlphaVantageQuote(
            symbol=quote.get("01. symbol", normalized_symbol),
            open=_parse_float(quote.get("02. open")),
            high=_parse_float(quote.get("03. high")),
            low=_parse_float(quote.get("04. low")),
            price=_parse_required_float(quote.get("05. price")),
            volume=_parse_int(quote.get("06. volume")),
            latest_trading_day=quote.get("07. latest trading day"),
            previous_close=_parse_float(quote.get("08. previous close")),
            change=_parse_float(quote.get("09. change")),
            change_percent=_parse_percent(quote.get("10. change percent")),
        )

    def search_symbols(self, keywords: str) -> list[AlphaVantageSearchResult]:
        normalized_keywords = keywords.strip()

        if not normalized_keywords:
            return []

        payload = self._get_json(
            {
                "function": "SYMBOL_SEARCH",
                "keywords": normalized_keywords,
            }
        )

        if "Error Message" in payload:
            return []

        if "Note" in payload or "Information" in payload:
            message = payload.get("Note") or payload.get("Information")
            raise _build_provider_message_error(str(message))

        matches = payload.get("bestMatches", [])

        if not isinstance(matches, list):
            raise MarketDataError("Alpha Vantage returned invalid search results.")

        return [
            AlphaVantageSearchResult(
                symbol=match.get("1. symbol", ""),
                name=match.get("2. name", ""),
                type=match.get("3. type", ""),
                region=match.get("4. region", ""),
                currency=match.get("8. currency", ""),
                match_score=_parse_float(match.get("9. matchScore")),
            )
            for match in matches
            if match.get("1. symbol") and match.get("2. name")
        ]

    def get_daily_bars(self, symbol: str, limit: int) -> list[AlphaVantageDailyBar]:
        normalized_symbol = symbol.strip().upper()
        payload = self._get_json(
            {
                "function": "TIME_SERIES_DAILY",
                "symbol": normalized_symbol,
                "outputsize": "compact",
            }
        )

        if "Error Message" in payload:
            raise StockSymbolNotFoundError(f"Stock symbol {normalized_symbol} was not found.")

        if "Note" in payload or "Information" in payload:
            message = payload.get("Note") or payload.get("Information")
            raise _build_provider_message_error(str(message))

        time_series = payload.get("Time Series (Daily)")

        if not isinstance(time_series, dict) or not time_series:
            raise StockSymbolNotFoundError(f"Stock symbol {normalized_symbol} was not found.")

        bars = [
            AlphaVantageDailyBar(
                timestamp=date,
                open=_parse_required_float(bar.get("1. open")),
                high=_parse_required_float(bar.get("2. high")),
                low=_parse_required_float(bar.get("3. low")),
                close=_parse_required_float(bar.get("4. close")),
                volume=_parse_required_int(bar.get("5. volume")),
            )
            for date, bar in time_series.items()
            if isinstance(bar, dict)
        ]

        bars.sort(key=lambda bar: bar.timestamp)

        return bars[-limit:]

    def get_news_sentiment(
        self,
        symbol: str,
        time_from: str,
        time_to: str,
        limit: int,
    ) -> list[AlphaVantageNewsArticle]:
        normalized_symbol = symbol.strip().upper()
        payload = self._get_json(
            {
                "function": "NEWS_SENTIMENT",
                "tickers": normalized_symbol,
                "time_from": time_from,
                "time_to": time_to,
                "sort": "LATEST",
                "limit": str(limit),
            }
        )

        if "Error Message" in payload:
            raise StockSymbolNotFoundError(
                f"News for stock symbol {normalized_symbol} was not found."
            )

        if "Note" in payload or "Information" in payload:
            message = payload.get("Note") or payload.get("Information")
            raise _build_provider_message_error(str(message))

        feed = payload.get("feed", [])

        if not isinstance(feed, list):
            raise MarketDataError("Alpha Vantage returned invalid news data.")

        articles: list[AlphaVantageNewsArticle] = []

        for item in feed:
            if not isinstance(item, dict):
                continue

            title = item.get("title")
            url = item.get("url")
            published_at = _parse_news_timestamp(item.get("time_published"))

            if not isinstance(title, str) or not title.strip():
                continue

            if not isinstance(url, str) or not url.strip() or published_at is None:
                continue

            ticker_data = _find_ticker_sentiment(
                item.get("ticker_sentiment"),
                normalized_symbol,
            )
            topics = _parse_news_topics(item.get("topics"))
            authors = item.get("authors", [])

            articles.append(
                AlphaVantageNewsArticle(
                    title=title.strip(),
                    summary=_string_or_empty(item.get("summary")),
                    url=url.strip(),
                    source=_string_or_default(item.get("source"), "Unknown source"),
                    source_domain=_optional_string(item.get("source_domain")),
                    published_at=published_at,
                    authors=[
                        author.strip()
                        for author in authors
                        if isinstance(author, str) and author.strip()
                    ]
                    if isinstance(authors, list)
                    else [],
                    topics=topics,
                    overall_sentiment_score=_parse_float(
                        item.get("overall_sentiment_score")
                    ),
                    overall_sentiment_label=_optional_string(
                        item.get("overall_sentiment_label")
                    ),
                    ticker_relevance_score=_parse_float(
                        ticker_data.get("relevance_score")
                    ),
                    ticker_sentiment_score=_parse_float(
                        ticker_data.get("ticker_sentiment_score")
                    ),
                    ticker_sentiment_label=_optional_string(
                        ticker_data.get("ticker_sentiment_label")
                    ),
                )
            )

        return articles

    def get_market_news(
        self,
        time_from: str,
        time_to: str,
        limit: int,
    ) -> list[AlphaVantageMarketNewsArticle]:
        payload = self._get_json(
            {
                "function": "NEWS_SENTIMENT",
                "time_from": time_from,
                "time_to": time_to,
                "sort": "LATEST",
                "limit": str(limit),
            }
        )
        _raise_for_provider_message(payload)
        feed = payload.get("feed", [])

        if not isinstance(feed, list):
            raise MarketDataError("Alpha Vantage returned invalid market news data.")

        articles: list[AlphaVantageMarketNewsArticle] = []

        for item in feed:
            if not isinstance(item, dict):
                continue

            title = _optional_string(item.get("title"))
            url = _optional_string(item.get("url"))
            published_at = _parse_news_timestamp(item.get("time_published"))

            if title is None or url is None or published_at is None:
                continue

            ticker_sentiments = _parse_ticker_sentiments(
                item.get("ticker_sentiment")
            )

            if not ticker_sentiments:
                continue

            articles.append(
                AlphaVantageMarketNewsArticle(
                    title=title,
                    url=url,
                    source=_string_or_default(item.get("source"), "Unknown source"),
                    published_at=published_at,
                    ticker_sentiments=ticker_sentiments,
                )
            )

        return articles

    def get_top_movers(self) -> AlphaVantageMarketMovers:
        payload = self._get_json({"function": "TOP_GAINERS_LOSERS"})
        _raise_for_provider_message(payload)

        return AlphaVantageMarketMovers(
            last_updated=_optional_string(payload.get("last_updated")),
            top_gainers=_parse_market_movers(payload.get("top_gainers")),
            top_losers=_parse_market_movers(payload.get("top_losers")),
            most_actively_traded=_parse_market_movers(
                payload.get("most_actively_traded")
            ),
        )

    def get_company_overview(self, symbol: str) -> AlphaVantageCompanyOverview:
        normalized_symbol = symbol.strip().upper()
        payload = self._get_json(
            {
                "function": "OVERVIEW",
                "symbol": normalized_symbol,
            }
        )
        _raise_for_provider_message(payload)
        response_symbol = _optional_string(payload.get("Symbol"))

        if response_symbol is None:
            raise StockSymbolNotFoundError(
                f"Fundamentals for stock symbol {normalized_symbol} were not found."
            )

        return AlphaVantageCompanyOverview(
            symbol=response_symbol.upper(),
            asset_type=_optional_string(payload.get("AssetType")),
            name=_optional_string(payload.get("Name")),
            description=_optional_string(payload.get("Description")),
            exchange=_optional_string(payload.get("Exchange")),
            currency=_optional_string(payload.get("Currency")),
            country=_optional_string(payload.get("Country")),
            sector=_optional_string(payload.get("Sector")),
            industry=_optional_string(payload.get("Industry")),
            fiscal_year_end=_optional_string(payload.get("FiscalYearEnd")),
            latest_quarter=_optional_string(payload.get("LatestQuarter")),
            market_capitalization=_parse_int(payload.get("MarketCapitalization")),
            ebitda=_parse_int(payload.get("EBITDA")),
            pe_ratio=_parse_float(payload.get("PERatio")),
            trailing_pe=_parse_float(payload.get("TrailingPE")),
            forward_pe=_parse_float(payload.get("ForwardPE")),
            peg_ratio=_parse_float(payload.get("PEGRatio")),
            price_to_sales_ttm=_parse_float(payload.get("PriceToSalesRatioTTM")),
            price_to_book=_parse_float(payload.get("PriceToBookRatio")),
            ev_to_revenue=_parse_float(payload.get("EVToRevenue")),
            ev_to_ebitda=_parse_float(payload.get("EVToEBITDA")),
            eps=_parse_float(payload.get("EPS")),
            diluted_eps_ttm=_parse_float(payload.get("DilutedEPSTTM")),
            dividend_yield=_parse_float(payload.get("DividendYield")),
            profit_margin=_parse_float(payload.get("ProfitMargin")),
            operating_margin_ttm=_parse_float(payload.get("OperatingMarginTTM")),
            return_on_assets_ttm=_parse_float(payload.get("ReturnOnAssetsTTM")),
            return_on_equity_ttm=_parse_float(payload.get("ReturnOnEquityTTM")),
            revenue_ttm=_parse_int(payload.get("RevenueTTM")),
            gross_profit_ttm=_parse_int(payload.get("GrossProfitTTM")),
            quarterly_earnings_growth_yoy=_parse_float(
                payload.get("QuarterlyEarningsGrowthYOY")
            ),
            quarterly_revenue_growth_yoy=_parse_float(
                payload.get("QuarterlyRevenueGrowthYOY")
            ),
            analyst_target_price=_parse_float(payload.get("AnalystTargetPrice")),
            beta=_parse_float(payload.get("Beta")),
            high_52_week=_parse_float(payload.get("52WeekHigh")),
            low_52_week=_parse_float(payload.get("52WeekLow")),
        )

    def get_latest_balance_sheet(
        self,
        symbol: str,
    ) -> AlphaVantageBalanceSheetSnapshot | None:
        normalized_symbol = symbol.strip().upper()
        payload = self._statement_payload("BALANCE_SHEET", normalized_symbol)
        _raise_for_provider_message(payload)
        reports = payload.get("quarterlyReports", [])

        if not isinstance(reports, list) or not reports:
            return None

        report = reports[0]

        if not isinstance(report, dict):
            return None

        fiscal_date_ending = _optional_string(report.get("fiscalDateEnding"))

        if fiscal_date_ending is None:
            return None

        return AlphaVantageBalanceSheetSnapshot(
            fiscal_date_ending=fiscal_date_ending,
            reported_currency=_optional_string(report.get("reportedCurrency")),
            total_assets=_parse_int(report.get("totalAssets")),
            total_current_assets=_parse_int(report.get("totalCurrentAssets")),
            cash_and_short_term_investments=_first_int(
                report.get("cashAndShortTermInvestments"),
                report.get("cashAndCashEquivalentsAtCarryingValue"),
            ),
            total_current_liabilities=_parse_int(
                report.get("totalCurrentLiabilities")
            ),
            total_liabilities=_parse_int(report.get("totalLiabilities")),
            short_term_debt=_first_int(
                report.get("shortTermDebt"),
                report.get("currentDebt"),
            ),
            long_term_debt=_parse_int(report.get("longTermDebt")),
            long_term_debt_noncurrent=_parse_int(
                report.get("longTermDebtNoncurrent")
            ),
            total_shareholder_equity=_parse_int(
                report.get("totalShareholderEquity")
            ),
        )

    def get_latest_annual_cash_flow(
        self,
        symbol: str,
    ) -> AlphaVantageCashFlowSnapshot | None:
        normalized_symbol = symbol.strip().upper()
        payload = self._statement_payload("CASH_FLOW", normalized_symbol)
        _raise_for_provider_message(payload)
        reports = payload.get("annualReports", [])

        if not isinstance(reports, list) or not reports:
            return None

        report = reports[0]

        if not isinstance(report, dict):
            return None

        fiscal_date_ending = _optional_string(report.get("fiscalDateEnding"))

        if fiscal_date_ending is None:
            return None

        return AlphaVantageCashFlowSnapshot(
            fiscal_date_ending=fiscal_date_ending,
            reported_currency=_optional_string(report.get("reportedCurrency")),
            operating_cash_flow=_parse_int(report.get("operatingCashflow")),
            capital_expenditures=_parse_int(report.get("capitalExpenditures")),
            dividend_payout=_parse_int(report.get("dividendPayout")),
            share_repurchases=_parse_int(
                report.get("paymentsForRepurchaseOfCommonStock")
            ),
        )

    def _statement_payload(self, function: str, symbol: str) -> dict:
        if not hasattr(self, "_statements"):
            self._statements: dict[tuple[str, str], dict] = {}
        key = (function, symbol.strip().upper())
        if key not in self._statements:
            payload = self._get_json({"function": key[0], "symbol": key[1]})
            _raise_for_provider_message(payload)
            self._statements[key] = payload
        return self._statements[key]

    def get_annual_statements(self, symbol: str) -> tuple[dict[str, list[dict]], list[str]]:
        statements: dict[str, list[dict]] = {}
        warnings: list[str] = []
        for function in ("INCOME_STATEMENT", "BALANCE_SHEET", "CASH_FLOW", "EARNINGS"):
            try:
                payload = self._statement_payload(function, symbol)
                rows = payload.get("annualEarnings" if function == "EARNINGS" else "annualReports", [])
                if not isinstance(rows, list):
                    raise MarketDataError(f"Invalid {function} annual statements.")
                statements[function] = [row for row in rows if isinstance(row, dict)]
                if not statements[function]:
                    warnings.append(f"No annual {function} data available.")
            except MarketDataRateLimitError as error:
                warnings.append(f"Annual financial collection stopped: {error}")
                break
            except MarketDataError as error:
                warnings.append(f"{function}: {error}")
        return statements, warnings

    def _get_json(self, params: dict[str, str]) -> dict:
        api_key = settings.market_data_api_key

        if not api_key:
            raise MarketDataError("MARKET_DATA_API_KEY is not configured.")

        query_params = urlencode({**params, "apikey": api_key})
        request = Request(
            f"{self.base_url}?{query_params}",
            headers={"User-Agent": "ai-stock-intelligence-platform"},
        )

        try:
            with self._request_lock:
                elapsed = monotonic() - type(self)._last_request_started_at
                remaining_delay = self.minimum_request_interval_seconds - elapsed

                if remaining_delay > 0:
                    sleep(remaining_delay)

                type(self)._last_request_started_at = monotonic()

                with urlopen(request, timeout=10) as response:
                    payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as error:
            raise MarketDataError("Unable to reach Alpha Vantage.") from error
        except json.JSONDecodeError as error:
            raise MarketDataError("Alpha Vantage returned invalid JSON.") from error

        if not isinstance(payload, dict):
            raise MarketDataError("Alpha Vantage returned invalid JSON.")

        return payload


def _parse_required_float(value: str | None) -> float:
    parsed_value = _parse_float(value)

    if parsed_value is None:
        raise MarketDataError("Alpha Vantage returned a quote without a price.")

    return parsed_value


def _parse_required_int(value: str | None) -> int:
    parsed_value = _parse_int(value)

    if parsed_value is None:
        raise MarketDataError("Alpha Vantage returned a bar without volume.")

    return parsed_value


def _parse_float(value: object) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_int(value: object) -> int | None:
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_int(*values: object) -> int | None:
    for value in values:
        parsed_value = _parse_int(value)

        if parsed_value is not None:
            return parsed_value

    return None


def _parse_percent(value: str | None) -> float | None:
    if value is None:
        return None

    return _parse_float(value.rstrip("%"))


def _parse_news_timestamp(value: object) -> str | None:
    if not isinstance(value, str):
        return None

    try:
        timestamp = datetime.strptime(value, "%Y%m%dT%H%M%S").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None

    return timestamp.isoformat().replace("+00:00", "Z")


def _find_ticker_sentiment(value: object, symbol: str) -> dict:
    if not isinstance(value, list):
        return {}

    for ticker_item in value:
        if not isinstance(ticker_item, dict):
            continue

        ticker = ticker_item.get("ticker")

        if isinstance(ticker, str) and ticker.upper() == symbol:
            return ticker_item

    return {}


def _parse_news_topics(value: object) -> list[AlphaVantageNewsTopic]:
    if not isinstance(value, list):
        return []

    topics: list[AlphaVantageNewsTopic] = []

    for item in value:
        if not isinstance(item, dict):
            continue

        name = item.get("topic")

        if isinstance(name, str) and name.strip():
            topics.append(
                AlphaVantageNewsTopic(
                    name=name.strip(),
                    relevance_score=_parse_float(item.get("relevance_score")),
                )
            )

    return topics


def _parse_ticker_sentiments(value: object) -> list[AlphaVantageTickerSentiment]:
    if not isinstance(value, list):
        return []

    sentiments: list[AlphaVantageTickerSentiment] = []

    for item in value:
        if not isinstance(item, dict):
            continue

        ticker = _optional_string(item.get("ticker"))

        if ticker is None:
            continue

        sentiments.append(
            AlphaVantageTickerSentiment(
                ticker=ticker.upper(),
                relevance_score=_parse_float(item.get("relevance_score")),
                sentiment_score=_parse_float(item.get("ticker_sentiment_score")),
                sentiment_label=_optional_string(
                    item.get("ticker_sentiment_label")
                ),
            )
        )

    return sentiments


def _parse_market_movers(value: object) -> list[AlphaVantageMarketMover]:
    if not isinstance(value, list):
        return []

    movers: list[AlphaVantageMarketMover] = []

    for item in value:
        if not isinstance(item, dict):
            continue

        ticker = _optional_string(item.get("ticker"))

        if ticker is None:
            continue

        movers.append(
            AlphaVantageMarketMover(
                ticker=ticker.upper(),
                price=_parse_float(item.get("price")),
                change_amount=_parse_float(item.get("change_amount")),
                change_percentage=_parse_percent(
                    _optional_string(item.get("change_percentage"))
                ),
                volume=_parse_int(item.get("volume")),
            )
        )

    return movers


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None

    return value.strip()


def _string_or_empty(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _string_or_default(value: object, default: str) -> str:
    parsed_value = _optional_string(value)
    return parsed_value if parsed_value is not None else default


def _build_provider_message_error(message: str) -> MarketDataError:
    normalized_message = message.lower()
    rate_limit_markers = ("rate limit", "call frequency", "requests per day")

    if any(marker in normalized_message for marker in rate_limit_markers):
        return MarketDataRateLimitError("Alpha Vantage rate limit reached.")

    api_key = settings.market_data_api_key
    safe_message = message.replace(api_key, "[redacted]") if api_key else message
    return MarketDataError(safe_message)


def _raise_for_provider_message(payload: dict) -> None:
    if "Error Message" in payload:
        raise MarketDataError(str(payload["Error Message"]))

    if "Note" in payload or "Information" in payload:
        message = payload.get("Note") or payload.get("Information")
        raise _build_provider_message_error(str(message))
