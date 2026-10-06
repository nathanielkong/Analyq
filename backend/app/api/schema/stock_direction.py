from typing import Literal

from pydantic import BaseModel, Field

from app.api.schema.stock_news import StockNewsResponse


DirectionLean = Literal["leaning_up", "leaning_down", "mixed"]
DirectionConfidence = Literal["low", "moderate"]
ValidationStatus = Literal["validated_edge", "inconclusive", "no_edge"]


class DirectionConfusionMatrixResponse(BaseModel):
    true_down_predicted_down: int
    true_down_predicted_up: int
    true_up_predicted_down: int
    true_up_predicted_up: int


class DirectionFoldValidationResponse(BaseModel):
    fold: int
    training_sample_count: int
    validation_sample_count: int
    validation_start: str
    validation_end: str
    accuracy_pct: float
    balanced_accuracy_pct: float
    brier_score: float
    roc_auc: float | None
    majority_baseline_accuracy_pct: float
    momentum_baseline_accuracy_pct: float
    benchmark_baseline_accuracy_pct: float


class DirectionCalibrationBinResponse(BaseModel):
    lower_probability_pct: float
    upper_probability_pct: float
    sample_count: int
    average_predicted_up_pct: float
    observed_up_pct: float


class DirectionFeatureStabilityResponse(BaseModel):
    feature_name: str
    mean_standardized_coefficient: float
    coefficient_std_dev: float
    sign_consistency_pct: float


class StockDirectionResponse(BaseModel):
    horizon_sessions: int = 1
    model_version: str
    model_type: str
    symbol: str
    benchmark_symbol: str
    target: str
    horizon: str
    generated_at: str
    data_through: str
    lean: DirectionLean
    confidence: DirectionConfidence
    up_probability_pct: float
    down_probability_pct: float
    training_start: str
    training_end: str
    training_sample_count: int
    validation_sample_count: int
    validation_fold_count: int
    validation_status: ValidationStatus
    validation_accuracy_pct: float
    validation_balanced_accuracy_pct: float
    validation_precision_pct: float
    validation_recall_pct: float
    validation_f1_pct: float
    validation_roc_auc: float | None
    baseline_accuracy_pct: float
    momentum_baseline_accuracy_pct: float
    benchmark_baseline_accuracy_pct: float
    strongest_baseline_accuracy_pct: float
    accuracy_edge_pct_points: float
    validation_brier_score: float
    baseline_brier_score: float
    validation_log_loss: float
    observed_up_rate_pct: float
    decisive_prediction_count: int
    decisive_coverage_pct: float
    decisive_accuracy_pct: float | None
    confusion_matrix: DirectionConfusionMatrixResponse
    folds: list[DirectionFoldValidationResponse]
    calibration: list[DirectionCalibrationBinResponse]
    feature_stability: list[DirectionFeatureStabilityResponse]
    news_features_used: bool
    feature_names: list[str]
    latest_feature_values: dict[str, float]
    warnings: list[str]


class StockOutlookResponse(BaseModel):
    additional_horizons: list[StockDirectionResponse] = Field(default_factory=list)
    horizon_errors: list[str] = Field(default_factory=list)
    symbol: str
    benchmark_symbol: str
    news: StockNewsResponse
    direction: StockDirectionResponse
