from dagster import (
    Definitions,
    ScheduleDefinition,
    define_asset_job,
)

# ZINC Fusion V15 Resources - Ultra-Organized Setup
from .defs.resources import (
    DuckDBResource,
    DataValidationResource,
    MLflowTrackingResource,
    WeatherAPIResource,
)

# ZINC Fusion V15 Assets - Production Grade Organization
from .defs.data_ingestion_assets import (
    # Raw data ingestion assets
    raw_market_futures_1d,
    raw_market_futures_1h,
    raw_fred_economic,
    raw_cftc_cot,
    raw_weather_noaa,
    # Asset checks
    check_market_futures_1d_quality,
    check_weather_data_quality,
)

# BIG-10 SPECIALIST MODELS - Ultra-Organized Forecasting Architecture
from .defs.big10_model_assets import (
    # Core L0 Specialist Models (Big-10 Architecture)
    crush_specialist_model,
    china_specialist_model,
    fx_specialist_model,
    fed_specialist_model,
    tariff_specialist_model,
    energy_specialist_model,
    biofuel_specialist_model,
    palm_specialist_model,
    volatility_specialist_model,
    weather_specialist_model,
    # Advanced Meta-Learning Models
    l1_meta_learner_model,
    l2_fusion_engine,
    l3_risk_engine,
    # Model Quality Checks
    check_crush_model_quality,
    check_weather_model_quality,
)

# Legacy schema creation (temporary for compatibility)
from .defs.zinc_fusion_assets import (
    create_schemas,
    create_raw_tables,
    create_feature_tables,
    create_training_tables,
    create_forecast_tables,
)

# ====================================================================
# ULTRA ORGANIZED ASSET JOBS - PRODUCTION GRADE DAGSTER PIPELINE
# ====================================================================

# ====================================================================
# ULTRA ORGANIZED ASSET JOBS - BIG-10 MODEL ARCHITECTURE
# ====================================================================

# Data Ingestion Job - Raw data collection with validation
data_ingestion_job = define_asset_job(
    name="data_ingestion_pipeline",
    selection=[
        create_schemas,  # Legacy compatibility
        raw_market_futures_1d,
        raw_market_futures_1h,
        raw_fred_economic,
        raw_cftc_cot,
        raw_weather_noaa,
    ],
    description="🔄 Ingest all raw data sources with comprehensive validation",
)

# Big-10 Specialist Models Job - Core L0 forecasting models
big10_specialists_job = define_asset_job(
    name="big10_specialists_pipeline",
    selection=[
        crush_specialist_model,
        china_specialist_model,
        fx_specialist_model,
        fed_specialist_model,
        tariff_specialist_model,
        energy_specialist_model,
        biofuel_specialist_model,
        palm_specialist_model,
        volatility_specialist_model,
        weather_specialist_model,
    ],
    description="🌟 Execute all Big-10 specialist forecasting models",
)

# Meta-Learning Pipeline - Advanced model fusion
meta_learning_job = define_asset_job(
    name="meta_learning_pipeline",
    selection=[
        l1_meta_learner_model,
        l2_fusion_engine,
        l3_risk_engine,
    ],
    description="🧠 Advanced meta-learning and risk analysis pipeline",
)

# Feature Engineering Job - Using legacy assets for now
feature_engineering_job = define_asset_job(
    name="feature_engineering_pipeline",
    selection=[
        create_feature_tables,  # Legacy feature creation
    ],
    description="⚙️ Generate features using legacy structure (upgrade planned)",
)

# Training Data Job - Using legacy assets for now
training_data_job = define_asset_job(
    name="training_data_pipeline",
    selection=[
        create_training_tables,  # Legacy training setup
    ],
    description="🎯 Create ML training matrices using legacy structure",
)

# Complete Pipeline Job - Full end-to-end execution
zinc_fusion_complete_pipeline = define_asset_job(
    name="zinc_fusion_complete_pipeline",
    description="🚀 Complete ZINC-FUSION-V15: Data → Big-10 → Meta-Learning → Risk",
)

# Production Master Pipeline - All critical models
production_master_pipeline = define_asset_job(
    name="production_master_pipeline",
    selection=[
        # Data ingestion
        raw_market_futures_1d,
        raw_market_futures_1h,
        raw_fred_economic,
        raw_cftc_cot,
        raw_weather_noaa,
        # Big-10 specialist models
        crush_specialist_model,
        china_specialist_model,
        fx_specialist_model,
        fed_specialist_model,
        tariff_specialist_model,
        energy_specialist_model,
        biofuel_specialist_model,
        palm_specialist_model,
        volatility_specialist_model,
        weather_specialist_model,
        # Meta-learning pipeline
        l1_meta_learner_model,
        l2_fusion_engine,
        l3_risk_engine,
    ],
    description="🎯 Production Master: Complete Big-10 → Meta-Learning → Risk Pipeline",
)

# Legacy Jobs (for backward compatibility)
all_assets_job = define_asset_job(
    name="all_assets_job",
    selection=[
        create_schemas,
        create_raw_tables,
        create_feature_tables,
        create_training_tables,
        create_forecast_tables,
    ],
)

zinc_fusion_v15_pipeline_job = define_asset_job(
    name="zinc_fusion_v15_pipeline",
    selection=[
        create_schemas,
        create_raw_tables,
        create_feature_tables,
        create_training_tables,
        create_forecast_tables,
    ],
)

# ====================================================================
# PRODUCTION GRADE SCHEDULING - OPTIMIZED FOR INSTITUTIONAL USE
# ====================================================================

# ====================================================================
# PRODUCTION GRADE SCHEDULING - BIG-10 OPTIMIZED
# ====================================================================

# Master Production Schedule - Complete Big-10 pipeline daily
production_daily_schedule = ScheduleDefinition(
    job=production_master_pipeline,
    cron_schedule="0 5 * * 1-5",  # 5:00 AM UTC weekdays only
    description="🎯 Master Production: Full Big-10 → Meta-Learning → Risk (Weekdays 12AM EST)",
)

# Specialist Models Schedule - Big-10 models every 4 hours during market week
specialists_schedule = ScheduleDefinition(
    job=big10_specialists_job,
    cron_schedule="0 6,10,14,18 * * 1-5",  # 6AM, 10AM, 2PM, 6PM UTC weekdays
    description="🌟 Big-10 Specialists: Crush, China, FX, Fed, Tariff, Energy, Biofuel, Palm, Vol, Weather",
)

# Meta-Learning Schedule - Advanced models twice daily
meta_learning_schedule = ScheduleDefinition(
    job=meta_learning_job,
    cron_schedule="0 7,19 * * 1-5",  # 7AM, 7PM UTC weekdays
    description="🧠 Meta-Learning: L1 → L2 → L3 (2AM EST, 2PM EST)",
)

# Market Hours Schedule - Intraday data updates
market_hours_schedule = ScheduleDefinition(
    job=data_ingestion_job,
    cron_schedule="0 9,11,13,15 * * 1-5",  # 9am, 11am, 1pm, 3pm UTC weekdays
    description="🔄 Market Hours: Continuous data ingestion during trading (4AM-10AM EST)",
)

# Weekend Batch Schedule - Full reprocessing and validation
weekend_batch_schedule = ScheduleDefinition(
    job=feature_engineering_job,
    cron_schedule="0 6 * * 6",  # 6:00 AM UTC Saturday
    description="🔧 Weekend Batch: Full feature recomputation and validation (1AM EST Saturday)",
)

# Legacy Schedule (for backward compatibility)
daily_refresh_schedule = ScheduleDefinition(
    job=zinc_fusion_v15_pipeline_job,
    cron_schedule="0 11 * * *",  # Daily at 6:00 AM EST (11:00 AM UTC)
)

# ====================================================================
# ULTRA ORGANIZED ASSET COLLECTION - BIG-10 ARCHITECTURE
# ====================================================================

# Raw Data Ingestion Assets
data_ingestion_assets = [
    raw_market_futures_1d,
    raw_market_futures_1h,
    raw_fred_economic,
    raw_cftc_cot,
    raw_weather_noaa,
]

# Big-10 Specialist Models - Core L0 Architecture
big10_specialist_assets = [
    crush_specialist_model,  # 🌾 Soybean crush margin forecasting
    china_specialist_model,  # 🇨🇳 Chinese demand and policy dynamics
    fx_specialist_model,  # 💱 Currency impact modeling
    fed_specialist_model,  # 🏦 Federal Reserve policy impacts
    tariff_specialist_model,  # 🛡️ Trade policy and tariff impacts
    energy_specialist_model,  # ⚡ Energy price impact modeling
    biofuel_specialist_model,  # 🌽 Biofuel demand and RIN pricing
    palm_specialist_model,  # 🌴 Palm oil competition dynamics
    volatility_specialist_model,  # 📊 Market structure and volatility
    weather_specialist_model,  # 🌦️ Agricultural weather impacts
]

# Meta-Learning Models - L1/L2/L3 Architecture
meta_learning_assets = [
    l1_meta_learner_model,  # 🧠 L1: Ensemble specialist combination
    l2_fusion_engine,  # 🔮 L2: Final forecast fusion
    l3_risk_engine,  # 🎯 L3: Monte Carlo VaR/CVaR
]

# Asset Quality Checks
asset_quality_checks = [
    check_market_futures_1d_quality,
    check_weather_data_quality,
    check_crush_model_quality,
    check_weather_model_quality,
]

# Feature Engineering Assets - Legacy compatibility
feature_engineering_assets = [
    create_feature_tables,
]

# Training Data Assets - Legacy compatibility
training_data_assets = [
    create_training_tables,
]

# Legacy Assets (backward compatibility)
legacy_assets = [
    create_schemas,
    create_raw_tables,
    create_forecast_tables,
]

# Complete Production Asset Collection - Ultra-Organized
all_production_assets = (
    data_ingestion_assets
    + big10_specialist_assets
    + meta_learning_assets
    + feature_engineering_assets
    + training_data_assets
    + legacy_assets
)

# ====================================================================
# ULTRA BADASS DAGSTER DEFINITIONS - INSTITUTIONAL GRADE
# ====================================================================

defs = Definitions(
    assets=all_production_assets,
    jobs=[
        # Production Grade BIG-10 Jobs
        production_master_pipeline,
        big10_specialists_job,
        meta_learning_job,
        data_ingestion_job,
        feature_engineering_job,
        training_data_job,
        # Complete pipeline jobs
        zinc_fusion_complete_pipeline,
        # Legacy Jobs (backward compatibility)
        all_assets_job,
        zinc_fusion_v15_pipeline_job,
    ],
    schedules=[
        # Production BIG-10 Schedules - Optimized for institutional use
        production_daily_schedule,
        specialists_schedule,
        meta_learning_schedule,
        market_hours_schedule,
        weekend_batch_schedule,
        # Legacy Schedule
        daily_refresh_schedule,
    ],
    resources={
        # Ultra-organized resource collection
        "duckdb_resource": DuckDBResource(
            database_path="data/zinc_fusion_v15.db",
            read_only=False,
            connection_timeout=30,
        ),
        "data_validation": DataValidationResource(
            max_null_percentage=0.5, min_row_count=100, required_date_range_days=30
        ),
        "mlflow_tracking": MLflowTrackingResource(
            tracking_uri="file://./mlruns", experiment_name="zinc-fusion-v15"
        ),
        "weather_api": WeatherAPIResource(
            base_url="https://archive-api.open-meteo.com/v1/archive",
            rate_limit_delay=1.0,
            timeout=60,
        ),
    },
)
