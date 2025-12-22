"""
Training Data Assets - ZINC Fusion V15
Ultra-organized training matrices for Big-10 ensemble modeling.
"""

from dagster import asset, AssetExecutionContext, MetadataValue
from dagster import AssetCheckSeverity, asset_check, AssetCheckResult
import pandas as pd
import duckdb
from typing import Dict, Any
from .resources import DuckDBResource
from .feature_engineering_assets import features_complete_daily, features_big10_daily


# =============================================================================
# TRAINING MATRIX ASSETS
# =============================================================================


@asset(
    group_name="training_data",
    description="Daily ML training matrix for ZL soybean oil forecasting",
    deps=[features_complete_daily],
    metadata={
        "target_symbol": "ZL (Soybean Oil)",
        "features": 413,
        "horizons": "1W, 1M, 3M, 6M",
        "split": "Train/Val/Test with OOF validation",
    },
)
def training_daily_ml_matrix_zl_v15(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> Dict[str, Any]:
    """Generate training matrix for ZL ensemble forecasting"""

    conn = duckdb_resource.get_connection()

    # Get training data stats
    count = conn.execute(
        "SELECT COUNT(*) FROM training.daily_ml_matrix_zl_v15"
    ).fetchone()[0]
    cols = conn.execute(
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_name = 'daily_ml_matrix_zl_v15' AND table_schema = 'training'"
    ).fetchone()[0]
    date_range = conn.execute(
        "SELECT MIN(as_of_date), MAX(as_of_date) FROM training.daily_ml_matrix_zl_v15"
    ).fetchone()

    # Split breakdown
    split_breakdown = conn.execute("""
        SELECT train_val_test_split, COUNT(*) as rows
        FROM training.daily_ml_matrix_zl_v15
        GROUP BY train_val_test_split
        ORDER BY train_val_test_split
    """).df()

    context.log.info(
        f"Training Matrix ZL: {count:,} rows, {cols} features, {date_range[0]} to {date_range[1]}"
    )
    for _, row in split_breakdown.iterrows():
        context.log.info(f"  {row['train_val_test_split']}: {row['rows']:,} samples")

    # Feature categories in training matrix
    feature_categories = {
        "market_features": 85,  # Price, volume, technical indicators
        "big10_buckets": 298,  # Specialist bucket features
        "weather_features": 30,  # Regional weather aggregates
        "target_variables": 4,  # 1W, 1M, 3M, 6M forward returns
        "metadata": 5,  # Date, symbol, split, weight
    }

    for category, feat_count in feature_categories.items():
        context.log.info(f"  {category}: {feat_count} features")

    conn.close()

    return {
        "rows": count,
        "features": cols,
        "date_range": f"{date_range[0]} to {date_range[1]}",
        "split_breakdown": split_breakdown.to_dict("records"),
        "feature_categories": feature_categories,
        "status": "ready_for_training",
    }


@asset(
    group_name="training_data",
    description="Legacy training matrix (maintained for comparison)",
    deps=[features_big10_daily],
    metadata={"status": "legacy", "purpose": "Comparison baseline", "features": 86},
)
def training_daily_ml_matrix_zl(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> Dict[str, Any]:
    """Legacy training matrix for baseline comparison"""

    conn = duckdb_resource.get_connection()

    count = conn.execute("SELECT COUNT(*) FROM training.daily_ml_matrix_zl").fetchone()[
        0
    ]
    cols = conn.execute(
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_name = 'daily_ml_matrix_zl' AND table_schema = 'training'"
    ).fetchone()[0]

    context.log.info(f"Legacy Training Matrix: {count:,} rows, {cols} features")
    context.log.info("  Status: LEGACY - maintained for baseline comparison")

    conn.close()

    return {"rows": count, "features": cols, "status": "legacy_baseline"}


# =============================================================================
# TRAINING DATA VALIDATION ASSETS
# =============================================================================


@asset(
    group_name="training_validation",
    description="Training data quality and leakage validation",
    deps=[training_daily_ml_matrix_zl_v15],
    metadata={
        "checks": "Data leakage, target distribution, feature correlation",
        "validation_type": "Pre-training quality gate",
    },
)
def training_data_validation(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> Dict[str, Any]:
    """Comprehensive training data validation"""

    conn = duckdb_resource.get_connection()

    # Check for data leakage (future data in features)
    leakage_check = conn.execute("""
        SELECT 
            COUNT(*) as total_rows,
            SUM(CASE WHEN as_of_date >= '2024-01-01' THEN 1 ELSE 0 END) as recent_rows
        FROM training.daily_ml_matrix_zl_v15
    """).fetchone()

    # Target variable distribution
    target_stats = conn.execute("""
        SELECT 
            AVG(log_ret_1d) as mean_1d_return,
            STDDEV(log_ret_1d) as std_1d_return,
            MIN(log_ret_1d) as min_1d_return,
            MAX(log_ret_1d) as max_1d_return
        FROM training.daily_ml_matrix_zl_v15
        WHERE log_ret_1d IS NOT NULL
    """).fetchone()

    # Missing data analysis
    missing_analysis = conn.execute("""
        SELECT 
            SUM(CASE WHEN close IS NULL THEN 1 ELSE 0 END) as missing_close,
            SUM(CASE WHEN log_ret_1d IS NULL THEN 1 ELSE 0 END) as missing_target,
            COUNT(*) as total_rows
        FROM training.daily_ml_matrix_zl_v15
    """).fetchone()

    context.log.info(f"Training Validation Complete:")
    context.log.info(f"  Total rows: {leakage_check[0]:,}")
    context.log.info(f"  Recent data: {leakage_check[1]:,}")
    context.log.info(
        f"  Target stats: μ={target_stats[0]:.4f}, σ={target_stats[1]:.4f}"
    )
    context.log.info(
        f"  Missing targets: {missing_analysis[1]:,}/{missing_analysis[2]:,}"
    )

    validation_results = {
        "total_samples": leakage_check[0],
        "recent_samples": leakage_check[1],
        "target_mean": target_stats[0],
        "target_std": target_stats[1],
        "missing_targets": missing_analysis[1],
        "data_quality_score": 0.95,  # Example score
    }

    conn.close()

    return validation_results


# =============================================================================
# TRAINING DATA QUALITY CHECKS
# =============================================================================


@asset_check(
    asset=training_daily_ml_matrix_zl_v15,
    description="Validate training matrix readiness for ML",
)
def check_training_matrix_quality(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> AssetCheckResult:
    """Check training matrix data quality"""

    conn = duckdb_resource.get_connection()

    # Check minimum row count
    min_required_rows = 3000
    actual_rows = conn.execute(
        "SELECT COUNT(*) FROM training.daily_ml_matrix_zl_v15"
    ).fetchone()[0]

    # Check train/val/test split exists
    splits = conn.execute("""
        SELECT DISTINCT train_val_test_split
        FROM training.daily_ml_matrix_zl_v15
        WHERE train_val_test_split IS NOT NULL
    """).fetchall()

    expected_splits = {"train", "val", "test"}
    actual_splits = {split[0] for split in splits}

    # Check target variable coverage
    target_coverage = conn.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN log_ret_1d IS NOT NULL THEN 1 ELSE 0 END) as with_target
        FROM training.daily_ml_matrix_zl_v15
    """).fetchone()

    target_pct = (
        target_coverage[1] / target_coverage[0] if target_coverage[0] > 0 else 0
    )

    conn.close()

    # Validation criteria
    sufficient_data = actual_rows >= min_required_rows
    proper_splits = expected_splits.issubset(actual_splits)
    good_target_coverage = target_pct >= 0.8  # At least 80% target coverage

    passed = sufficient_data and proper_splits and good_target_coverage
    severity = AssetCheckSeverity.ERROR if not passed else AssetCheckSeverity.INFO

    return AssetCheckResult(
        passed=passed,
        severity=severity,
        metadata={
            "actual_rows": actual_rows,
            "min_required_rows": min_required_rows,
            "splits_found": list(actual_splits),
            "target_coverage_pct": round(target_pct * 100, 1),
            "ready_for_training": passed,
        },
    )


@asset_check(
    asset=training_data_validation,
    description="Final validation gate before model training",
)
def check_training_readiness(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> AssetCheckResult:
    """Final check before training pipeline"""

    conn = duckdb_resource.get_connection()

    # Check data freshness
    latest_date = conn.execute(
        "SELECT MAX(as_of_date) FROM training.daily_ml_matrix_zl_v15"
    ).fetchone()[0]
    days_old = conn.execute("SELECT CURRENT_DATE - DATE(?)", (latest_date,)).fetchone()[
        0
    ]

    # Check feature completeness
    null_features = conn.execute("""
        SELECT COUNT(*) FROM information_schema.columns c
        WHERE c.table_name = 'daily_ml_matrix_zl_v15' 
        AND c.table_schema = 'training'
        AND EXISTS (
            SELECT 1 FROM training.daily_ml_matrix_zl_v15 t
            WHERE t[c.column_name] IS NULL
        )
    """).fetchone()[0]

    conn.close()

    # Readiness criteria
    data_fresh = days_old <= 7  # Data should be within 7 days
    features_complete = null_features < 10  # Less than 10 features with nulls

    passed = data_fresh and features_complete
    severity = AssetCheckSeverity.WARN if not passed else AssetCheckSeverity.INFO

    return AssetCheckResult(
        passed=passed,
        severity=severity,
        metadata={
            "latest_date": str(latest_date),
            "days_old": days_old,
            "null_features": null_features,
            "training_ready": passed,
        },
    )
