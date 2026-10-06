from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from math import log, log1p
from statistics import fmean, pstdev, stdev
from zoneinfo import ZoneInfo

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.api.schema.stock_direction import (
    DirectionConfidence,
    DirectionCalibrationBinResponse,
    DirectionConfusionMatrixResponse,
    DirectionFeatureStabilityResponse,
    DirectionFoldValidationResponse,
    DirectionLean,
    StockDirectionResponse,
    StockOutlookResponse,
    ValidationStatus,
)
from app.api.schema.stock_history import StockHistoryBarResponse, StockHistoryResponse
from app.api.schema.stock_news import StockNewsArticleResponse, StockNewsResponse
from app.api.services.stock_history_services import (
    get_stock_history,
    normalize_stock_symbol,
)
from app.api.services.stock_news_services import get_stock_news


MODEL_VERSION = "1.2.0"
MODEL_REGULARIZATION_C = 0.1
MIN_TRAINING_SAMPLES = 60
MIN_NEWS_ARTICLES_FOR_MODEL = 5
FEATURE_LOOKBACK = 20
UP_THRESHOLD = 0.55
DOWN_THRESHOLD = 0.45
MIN_VALIDATED_ACCURACY_EDGE = 0.02
MIN_VALIDATED_ROC_AUC = 0.52
MARKET_TIME_ZONE = ZoneInfo("America/New_York")
OUTLOOK_ARTICLE_DISPLAY_LIMIT = 10

BASE_FEATURE_NAMES = [
    "return_1d",
    "return_5d",
    "intraday_return",
    "daily_range_pct",
    "volatility_5d",
    "volatility_20d",
    "sma_gap_5d",
    "sma_gap_20d",
    "rsi_14",
    "atr_14_pct",
    "volume_ratio_20d",
    "benchmark_return_1d",
    "benchmark_return_5d",
    "excess_return_1d",
]
NEWS_FEATURE_NAMES = [
    "news_vader_compound",
    "news_provider_sentiment",
    "news_log_article_count",
]


class DirectionModelError(Exception):
    pass


@dataclass(frozen=True)
class ModelRow:
    observation_date: str
    features: list[float]
    target: int | None


@dataclass(frozen=True)
class WalkForwardValidation:
    labels: list[int]
    probabilities: list[float]
    predictions: list[int]
    majority_predictions: list[int]
    momentum_predictions: list[int]
    benchmark_predictions: list[int]
    prior_probabilities: list[float]
    folds: list[DirectionFoldValidationResponse]
    fold_coefficients: list[list[float]]


def get_stock_outlook(
    symbol: str,
    benchmark_symbol: str,
    history_limit: int,
    news_days: int,
    news_limit: int,
) -> StockOutlookResponse:
    normalized_symbol = normalize_stock_symbol(symbol)
    normalized_benchmark = normalize_stock_symbol(benchmark_symbol)
    news = get_stock_news(
        symbol=normalized_symbol,
        days=news_days,
        limit=news_limit,
    )
    stock_history = get_stock_history(
        symbol=normalized_symbol,
        provider="alpaca",
        timeframe="1Day",
        limit=history_limit,
    )
    benchmark_history = get_stock_history(
        symbol=normalized_benchmark,
        provider="alpaca",
        timeframe="1Day",
        limit=history_limit,
    )
    direction = build_direction_model(
        stock_history=stock_history,
        benchmark_history=benchmark_history,
        news=news,
    )
    additional_horizons = []
    horizon_errors = []
    for horizon in (3, 5):
        try:
            additional_horizons.append(
                build_direction_model(
                    stock_history,
                    benchmark_history,
                    news,
                    horizon_sessions=horizon,
                )
            )
        except DirectionModelError as error:
            horizon_errors.append(f"{horizon}-session model unavailable: {error}")

    return StockOutlookResponse(
        additional_horizons=additional_horizons,
        horizon_errors=horizon_errors,
        symbol=normalized_symbol,
        benchmark_symbol=normalized_benchmark,
        news=news.model_copy(
            update={"articles": news.articles[:OUTLOOK_ARTICLE_DISPLAY_LIMIT]}
        ),
        direction=direction,
    )


def build_direction_model(
    stock_history: StockHistoryResponse,
    benchmark_history: StockHistoryResponse,
    news: StockNewsResponse,
    generated_at: str | None = None,
    horizon_sessions: int = 1,
) -> StockDirectionResponse:
    if horizon_sessions not in (1, 3, 5):
        raise DirectionModelError(
            "Supported horizons are 1, 3 and 5 completed sessions."
        )
    if len(stock_history.bars) < MIN_TRAINING_SAMPLES + FEATURE_LOOKBACK + 1:
        raise DirectionModelError(
            f"At least {MIN_TRAINING_SAMPLES + FEATURE_LOOKBACK + 1} adjusted daily "
            "bars are required for the direction baseline."
        )

    warnings = [
        "This is an experimental probability baseline, not a trading signal or financial advice."
    ]
    if horizon_sessions > 1:
        warnings.append(
            "Multi-session validation outcomes overlap; accuracy observations are correlated, not independent proof of an edge."
        )
    news_features_requested = (
        news.summary.article_count >= MIN_NEWS_ARTICLES_FOR_MODEL
        and not news.result_limit_reached
    )
    rows = _build_model_rows(
        stock_history=stock_history,
        benchmark_history=benchmark_history,
        news=news if news_features_requested else None,
        horizon_sessions=horizon_sessions,
    )
    training_rows = [row for row in rows if row.target is not None]
    news_features_used = news_features_requested

    if news_features_used and len(training_rows) < MIN_TRAINING_SAMPLES:
        warnings.append(
            "News coverage did not overlap enough market sessions, so the model fell "
            "back to price, volume, and benchmark features."
        )
        rows = _build_model_rows(
            stock_history=stock_history,
            benchmark_history=benchmark_history,
            news=None,
            horizon_sessions=horizon_sessions,
        )
        training_rows = [row for row in rows if row.target is not None]
        news_features_used = False
    elif not news_features_requested:
        if news.result_limit_reached:
            warnings.append(
                "News features were excluded because the provider limit made the period incomplete."
            )
        else:
            warnings.append(
                f"News features require at least {MIN_NEWS_ARTICLES_FOR_MODEL} valid articles; "
                "this model used price, volume, and benchmark data only."
            )

    if len(training_rows) < MIN_TRAINING_SAMPLES or not rows:
        raise DirectionModelError(
            "There are not enough aligned stock and benchmark observations to train the model."
        )

    latest_stock_date = _bar_date(stock_history.bars[-1]).isoformat()

    if rows[-1].observation_date != latest_stock_date:
        raise DirectionModelError(
            "The latest stock and benchmark sessions do not align, so a current "
            "direction probability cannot be produced."
        )

    labels = [int(row.target) for row in training_rows if row.target is not None]

    if len(set(labels)) < 2:
        raise DirectionModelError(
            "The training period needs both up and down days for logistic regression."
        )

    features = [row.features for row in training_rows]
    feature_names = BASE_FEATURE_NAMES + (
        NEWS_FEATURE_NAMES if news_features_used else []
    )
    fold_count = min(5, max(2, len(training_rows) // 30))
    validation = _walk_forward_validate(
        training_rows=training_rows,
        feature_names=feature_names,
        fold_count=fold_count,
        horizon_sessions=horizon_sessions,
    )

    if not validation.labels:
        raise DirectionModelError(
            "Chronological validation could not create a fold containing both outcomes."
        )

    final_model = _create_pipeline()
    final_model.fit(features, labels)
    latest_row = rows[-1]
    up_probability = float(final_model.predict_proba([latest_row.features])[0][1])
    validation_accuracy = float(
        accuracy_score(validation.labels, validation.predictions)
    )
    validation_balanced_accuracy = float(
        balanced_accuracy_score(validation.labels, validation.predictions)
    )
    validation_precision = float(
        precision_score(validation.labels, validation.predictions, zero_division=0)
    )
    validation_recall = float(
        recall_score(validation.labels, validation.predictions, zero_division=0)
    )
    validation_f1 = float(
        f1_score(validation.labels, validation.predictions, zero_division=0)
    )
    validation_roc_auc = _safe_roc_auc(
        validation.labels,
        validation.probabilities,
    )
    baseline_accuracy = float(
        accuracy_score(validation.labels, validation.majority_predictions)
    )
    momentum_baseline_accuracy = float(
        accuracy_score(validation.labels, validation.momentum_predictions)
    )
    benchmark_baseline_accuracy = float(
        accuracy_score(validation.labels, validation.benchmark_predictions)
    )
    strongest_baseline_accuracy = max(
        baseline_accuracy,
        momentum_baseline_accuracy,
        benchmark_baseline_accuracy,
    )
    accuracy_edge = validation_accuracy - strongest_baseline_accuracy
    brier_score = float(brier_score_loss(validation.labels, validation.probabilities))
    baseline_brier_score = float(
        brier_score_loss(validation.labels, validation.prior_probabilities)
    )
    validation_log_loss = float(
        log_loss(validation.labels, validation.probabilities, labels=[0, 1])
    )
    validation_status = _classify_validation_status(
        accuracy_edge=accuracy_edge,
        roc_auc=validation_roc_auc,
        brier_score=brier_score,
        baseline_brier_score=baseline_brier_score,
    )
    decisive_indexes = [
        index
        for index, probability in enumerate(validation.probabilities)
        if probability >= UP_THRESHOLD or probability <= DOWN_THRESHOLD
    ]
    decisive_accuracy = (
        float(
            accuracy_score(
                [validation.labels[index] for index in decisive_indexes],
                [validation.predictions[index] for index in decisive_indexes],
            )
        )
        if decisive_indexes
        else None
    )
    (
        true_down_predicted_down,
        true_down_predicted_up,
        true_up_predicted_down,
        true_up_predicted_up,
    ) = (
        int(value)
        for value in confusion_matrix(
            validation.labels,
            validation.predictions,
            labels=[0, 1],
        ).ravel()
    )

    if len(training_rows) < 150:
        warnings.append(
            "The training sample is small; probabilities may change substantially with new data."
        )

    if validation_status != "validated_edge":
        warnings.append(
            "The model did not pass the provisional validation gate, so the displayed "
            "direction is forced to mixed."
        )

    if brier_score >= baseline_brier_score:
        warnings.append(
            "Probability error did not beat the fold-specific historical up-rate baseline."
        )

    warnings.append(
        "Feature coefficients can be unstable when indicators are correlated and are not causal effects."
    )

    if news_features_used:
        warnings.append(
            "News is aligned to market-close cutoffs so articles published later cannot enter "
            "earlier training rows."
        )

    return StockDirectionResponse(
        horizon_sessions=horizon_sessions,
        model_version=MODEL_VERSION,
        model_type="logistic_regression",
        symbol=stock_history.symbol,
        benchmark_symbol=benchmark_history.symbol,
        target="next_completed_close_is_higher"
        if horizon_sessions == 1
        else f"close_after_{horizon_sessions}_sessions_is_higher",
        horizon="next completed daily close"
        if horizon_sessions == 1
        else f"close after {horizon_sessions} completed daily sessions",
        generated_at=generated_at or _utc_timestamp(),
        data_through=latest_row.observation_date,
        lean=_classify_lean(up_probability, validation_status),
        confidence=_classify_confidence(
            up_probability=up_probability,
            validation_status=validation_status,
        ),
        up_probability_pct=round(up_probability * 100, 2),
        down_probability_pct=round((1 - up_probability) * 100, 2),
        training_start=training_rows[0].observation_date,
        training_end=training_rows[-1].observation_date,
        training_sample_count=len(training_rows),
        validation_sample_count=len(validation.labels),
        validation_fold_count=len(validation.folds),
        validation_status=validation_status,
        validation_accuracy_pct=round(validation_accuracy * 100, 2),
        validation_balanced_accuracy_pct=round(
            validation_balanced_accuracy * 100,
            2,
        ),
        validation_precision_pct=round(validation_precision * 100, 2),
        validation_recall_pct=round(validation_recall * 100, 2),
        validation_f1_pct=round(validation_f1 * 100, 2),
        validation_roc_auc=(
            round(validation_roc_auc, 4) if validation_roc_auc is not None else None
        ),
        baseline_accuracy_pct=round(baseline_accuracy * 100, 2),
        momentum_baseline_accuracy_pct=round(
            momentum_baseline_accuracy * 100,
            2,
        ),
        benchmark_baseline_accuracy_pct=round(
            benchmark_baseline_accuracy * 100,
            2,
        ),
        strongest_baseline_accuracy_pct=round(
            strongest_baseline_accuracy * 100,
            2,
        ),
        accuracy_edge_pct_points=round(accuracy_edge * 100, 2),
        validation_brier_score=round(brier_score, 4),
        baseline_brier_score=round(baseline_brier_score, 4),
        validation_log_loss=round(validation_log_loss, 4),
        observed_up_rate_pct=round(fmean(validation.labels) * 100, 2),
        decisive_prediction_count=len(decisive_indexes),
        decisive_coverage_pct=round(
            (len(decisive_indexes) / len(validation.labels)) * 100,
            2,
        ),
        decisive_accuracy_pct=(
            round(decisive_accuracy * 100, 2) if decisive_accuracy is not None else None
        ),
        confusion_matrix=DirectionConfusionMatrixResponse(
            true_down_predicted_down=true_down_predicted_down,
            true_down_predicted_up=true_down_predicted_up,
            true_up_predicted_down=true_up_predicted_down,
            true_up_predicted_up=true_up_predicted_up,
        ),
        folds=validation.folds,
        calibration=_build_calibration_bins(
            validation.labels,
            validation.probabilities,
        ),
        feature_stability=_build_feature_stability(
            feature_names,
            validation.fold_coefficients,
        ),
        news_features_used=news_features_used,
        feature_names=feature_names,
        latest_feature_values={
            name: round(value, 6)
            for name, value in zip(feature_names, latest_row.features)
        },
        warnings=warnings,
    )


def _walk_forward_validate(
    training_rows: list[ModelRow],
    feature_names: list[str],
    fold_count: int,
    horizon_sessions: int = 1,
) -> WalkForwardValidation:
    features = [row.features for row in training_rows]
    labels = [int(row.target) for row in training_rows if row.target is not None]
    momentum_index = feature_names.index("return_1d")
    benchmark_index = feature_names.index("benchmark_return_1d")
    # Purge labels whose future observation window reaches the validation period.
    splitter = TimeSeriesSplit(n_splits=fold_count, gap=horizon_sessions)
    validation_labels: list[int] = []
    validation_probabilities: list[float] = []
    validation_predictions: list[int] = []
    majority_predictions: list[int] = []
    momentum_predictions: list[int] = []
    benchmark_predictions: list[int] = []
    prior_probabilities: list[float] = []
    folds: list[DirectionFoldValidationResponse] = []
    fold_coefficients: list[list[float]] = []

    for fold_number, (train_indexes, test_indexes) in enumerate(
        splitter.split(features),
        start=1,
    ):
        train_labels = [labels[index] for index in train_indexes]

        if len(set(train_labels)) < 2:
            continue

        model = _create_pipeline()
        model.fit(
            [features[index] for index in train_indexes],
            train_labels,
        )
        test_features = [features[index] for index in test_indexes]
        fold_probabilities = model.predict_proba(test_features)[:, 1].tolist()
        fold_predictions = [
            int(probability >= 0.5) for probability in fold_probabilities
        ]
        fold_labels = [labels[index] for index in test_indexes]
        majority_label = int(fmean(train_labels) >= 0.5)
        fold_majority_predictions = [majority_label for _ in fold_labels]
        fold_momentum_predictions = [
            int(feature_values[momentum_index] >= 0) for feature_values in test_features
        ]
        fold_benchmark_predictions = [
            int(feature_values[benchmark_index] >= 0)
            for feature_values in test_features
        ]
        prior_probability = fmean(train_labels)
        classifier = model.named_steps["classifier"]
        fold_coefficients.append(classifier.coef_[0].tolist())

        validation_labels.extend(fold_labels)
        validation_probabilities.extend(fold_probabilities)
        validation_predictions.extend(fold_predictions)
        majority_predictions.extend(fold_majority_predictions)
        momentum_predictions.extend(fold_momentum_predictions)
        benchmark_predictions.extend(fold_benchmark_predictions)
        prior_probabilities.extend(prior_probability for _ in fold_labels)
        folds.append(
            DirectionFoldValidationResponse(
                fold=fold_number,
                training_sample_count=len(train_indexes),
                validation_sample_count=len(test_indexes),
                validation_start=training_rows[test_indexes[0]].observation_date,
                validation_end=training_rows[test_indexes[-1]].observation_date,
                accuracy_pct=round(
                    accuracy_score(fold_labels, fold_predictions) * 100,
                    2,
                ),
                balanced_accuracy_pct=round(
                    balanced_accuracy_score(fold_labels, fold_predictions) * 100,
                    2,
                ),
                brier_score=round(
                    brier_score_loss(fold_labels, fold_probabilities),
                    4,
                ),
                roc_auc=_round_optional_metric(
                    _safe_roc_auc(fold_labels, fold_probabilities)
                ),
                majority_baseline_accuracy_pct=round(
                    accuracy_score(fold_labels, fold_majority_predictions) * 100,
                    2,
                ),
                momentum_baseline_accuracy_pct=round(
                    accuracy_score(fold_labels, fold_momentum_predictions) * 100,
                    2,
                ),
                benchmark_baseline_accuracy_pct=round(
                    accuracy_score(fold_labels, fold_benchmark_predictions) * 100,
                    2,
                ),
            )
        )

    return WalkForwardValidation(
        labels=validation_labels,
        probabilities=validation_probabilities,
        predictions=validation_predictions,
        majority_predictions=majority_predictions,
        momentum_predictions=momentum_predictions,
        benchmark_predictions=benchmark_predictions,
        prior_probabilities=prior_probabilities,
        folds=folds,
        fold_coefficients=fold_coefficients,
    )


def _build_calibration_bins(
    labels: list[int],
    probabilities: list[float],
) -> list[DirectionCalibrationBinResponse]:
    bins: list[DirectionCalibrationBinResponse] = []

    for index in range(5):
        lower = index / 5
        upper = (index + 1) / 5
        matching_indexes = [
            probability_index
            for probability_index, probability in enumerate(probabilities)
            if probability >= lower
            and (probability < upper or (index == 4 and probability <= upper))
        ]

        if not matching_indexes:
            continue

        bins.append(
            DirectionCalibrationBinResponse(
                lower_probability_pct=round(lower * 100, 2),
                upper_probability_pct=round(upper * 100, 2),
                sample_count=len(matching_indexes),
                average_predicted_up_pct=round(
                    fmean(probabilities[item] for item in matching_indexes) * 100,
                    2,
                ),
                observed_up_pct=round(
                    fmean(labels[item] for item in matching_indexes) * 100,
                    2,
                ),
            )
        )

    return bins


def _build_feature_stability(
    feature_names: list[str],
    fold_coefficients: list[list[float]],
) -> list[DirectionFeatureStabilityResponse]:
    if not fold_coefficients:
        return []

    feature_results: list[DirectionFeatureStabilityResponse] = []

    for feature_index, feature_name in enumerate(feature_names):
        coefficients = [fold[feature_index] for fold in fold_coefficients]
        mean_coefficient = fmean(coefficients)
        same_sign_count = sum(
            coefficient == 0 or (coefficient > 0) == (mean_coefficient > 0)
            for coefficient in coefficients
        )
        feature_results.append(
            DirectionFeatureStabilityResponse(
                feature_name=feature_name,
                mean_standardized_coefficient=round(mean_coefficient, 4),
                coefficient_std_dev=round(pstdev(coefficients), 4),
                sign_consistency_pct=round(
                    (same_sign_count / len(coefficients)) * 100,
                    2,
                ),
            )
        )

    return sorted(
        feature_results,
        key=lambda item: abs(item.mean_standardized_coefficient),
        reverse=True,
    )


def _safe_roc_auc(labels: list[int], probabilities: list[float]) -> float | None:
    if len(set(labels)) < 2:
        return None

    return float(roc_auc_score(labels, probabilities))


def _round_optional_metric(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None


def _build_model_rows(
    stock_history: StockHistoryResponse,
    benchmark_history: StockHistoryResponse,
    news: StockNewsResponse | None,
    horizon_sessions: int = 1,
) -> list[ModelRow]:
    stock_bars = stock_history.bars
    benchmark_by_date = {
        _bar_date(bar): (index, bar) for index, bar in enumerate(benchmark_history.bars)
    }
    news_period_start = (
        _parse_timestamp(news.period_start) if news is not None else None
    )
    rows: list[ModelRow] = []

    for index in range(FEATURE_LOOKBACK, len(stock_bars)):
        current_bar = stock_bars[index]
        observation_date = _bar_date(current_bar)
        benchmark_entry = benchmark_by_date.get(observation_date)

        if benchmark_entry is None:
            continue

        benchmark_index, benchmark_bar = benchmark_entry

        if benchmark_index < 5:
            continue

        previous_close_cutoff = _market_close_utc(_bar_date(stock_bars[index - 1]))
        current_close_cutoff = _market_close_utc(observation_date)

        if news_period_start is not None and previous_close_cutoff < news_period_start:
            continue

        stock_window = stock_bars[: index + 1]
        benchmark_bars = benchmark_history.bars
        feature_values = _price_features(
            stock_window=stock_window,
            benchmark_window=benchmark_bars[: benchmark_index + 1],
            benchmark_bar=benchmark_bar,
        )

        if news is not None:
            feature_values.extend(
                _news_features(
                    articles=news.articles,
                    period_start=previous_close_cutoff,
                    period_end=current_close_cutoff,
                )
            )

        target = (
            int(stock_bars[index + horizon_sessions].close > current_bar.close)
            if index + horizon_sessions < len(stock_bars)
            else None
        )
        rows.append(
            ModelRow(
                observation_date=observation_date.isoformat(),
                features=feature_values,
                target=target,
            )
        )

    return rows


def _price_features(
    stock_window: list[StockHistoryBarResponse],
    benchmark_window: list[StockHistoryBarResponse],
    benchmark_bar: StockHistoryBarResponse,
) -> list[float]:
    current = stock_window[-1]
    previous = stock_window[-2]
    closes = [bar.close for bar in stock_window]
    volumes = [bar.volume for bar in stock_window]
    benchmark_closes = [bar.close for bar in benchmark_window]
    return_1d = (current.close / previous.close) - 1
    return_5d = (current.close / stock_window[-6].close) - 1
    benchmark_return_1d = (benchmark_bar.close / benchmark_window[-2].close) - 1
    benchmark_return_5d = (benchmark_bar.close / benchmark_window[-6].close) - 1
    log_returns = [
        log(current_close / previous_close)
        for previous_close, current_close in zip(closes, closes[1:])
    ]
    average_volume = fmean(volumes[-20:])

    return [
        return_1d,
        return_5d,
        (current.close / current.open) - 1,
        (current.high - current.low) / current.close,
        stdev(log_returns[-5:]),
        stdev(log_returns[-20:]),
        (current.close / fmean(closes[-5:])) - 1,
        (current.close / fmean(closes[-20:])) - 1,
        _rsi(closes, 14),
        _average_true_range_pct(stock_window, 14),
        current.volume / average_volume if average_volume > 0 else 1.0,
        benchmark_return_1d,
        benchmark_return_5d,
        return_1d - benchmark_return_1d,
    ]


def _news_features(
    articles: list[StockNewsArticleResponse],
    period_start: datetime,
    period_end: datetime,
) -> list[float]:
    matching_articles = [
        article
        for article in articles
        if period_start < _required_timestamp(article.published_at) <= period_end
    ]

    if not matching_articles:
        return [0.0, 0.0, 0.0]

    weights = [
        article.relevance_score
        if article.relevance_score is not None and article.relevance_score > 0
        else 1.0
        for article in matching_articles
    ]
    weight_total = sum(weights)
    vader_sentiment = (
        sum(
            article.vader_compound * weight
            for article, weight in zip(matching_articles, weights)
        )
        / weight_total
    )
    provider_articles = [
        article
        for article in matching_articles
        if article.provider_sentiment_score is not None
    ]
    provider_sentiment = (
        fmean(
            article.provider_sentiment_score
            for article in provider_articles
            if article.provider_sentiment_score is not None
        )
        if provider_articles
        else 0.0
    )

    return [vader_sentiment, provider_sentiment, log1p(len(matching_articles))]


def _rsi(closes: list[float], window: int) -> float:
    changes = [
        current - previous
        for previous, current in zip(closes[-(window + 1) :], closes[-window:])
    ]
    average_gain = fmean(max(change, 0.0) for change in changes)
    average_loss = fmean(max(-change, 0.0) for change in changes)

    if average_loss == 0:
        return 100.0 if average_gain > 0 else 50.0

    relative_strength = average_gain / average_loss
    return 100 - (100 / (1 + relative_strength))


def _average_true_range_pct(
    bars: list[StockHistoryBarResponse],
    window: int,
) -> float:
    recent_bars = bars[-window:]
    previous_closes = bars[-(window + 1) : -1]
    true_ranges = [
        max(
            current.high - current.low,
            abs(current.high - previous.close),
            abs(current.low - previous.close),
        )
        for previous, current in zip(previous_closes, recent_bars)
    ]

    return fmean(true_ranges) / bars[-1].close


def _create_pipeline() -> Pipeline:
    return Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "classifier",
                LogisticRegression(
                    C=MODEL_REGULARIZATION_C,
                    max_iter=1000,
                    random_state=42,
                ),
            ),
        ]
    )


def _classify_validation_status(
    accuracy_edge: float,
    roc_auc: float | None,
    brier_score: float,
    baseline_brier_score: float,
) -> ValidationStatus:
    if (
        accuracy_edge >= MIN_VALIDATED_ACCURACY_EDGE
        and roc_auc is not None
        and roc_auc >= MIN_VALIDATED_ROC_AUC
        and brier_score < baseline_brier_score
    ):
        return "validated_edge"

    if (
        accuracy_edge > 0
        and roc_auc is not None
        and roc_auc >= 0.5
        and brier_score <= baseline_brier_score
    ):
        return "inconclusive"

    return "no_edge"


def _classify_lean(
    up_probability: float,
    validation_status: ValidationStatus,
) -> DirectionLean:
    if validation_status != "validated_edge":
        return "mixed"

    if up_probability >= UP_THRESHOLD:
        return "leaning_up"

    if up_probability <= DOWN_THRESHOLD:
        return "leaning_down"

    return "mixed"


def _classify_confidence(
    up_probability: float,
    validation_status: ValidationStatus,
) -> DirectionConfidence:
    probability_margin = abs(up_probability - 0.5)

    if probability_margin >= 0.1 and validation_status == "validated_edge":
        return "moderate"

    return "low"


def _bar_date(bar: StockHistoryBarResponse) -> date:
    try:
        return date.fromisoformat(bar.timestamp[:10])
    except ValueError as error:
        raise DirectionModelError(
            f"Historical bar timestamp {bar.timestamp!r} is invalid."
        ) from error


def _market_close_utc(value: date) -> datetime:
    local_close = datetime.combine(value, time(hour=16), tzinfo=MARKET_TIME_ZONE)
    return local_close.astimezone(timezone.utc)


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed_value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise DirectionModelError(f"Timestamp {value!r} is invalid.") from error

    if parsed_value.tzinfo is None:
        parsed_value = parsed_value.replace(tzinfo=timezone.utc)

    return parsed_value.astimezone(timezone.utc)


def _required_timestamp(value: str) -> datetime:
    return _parse_timestamp(value)


def _utc_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
