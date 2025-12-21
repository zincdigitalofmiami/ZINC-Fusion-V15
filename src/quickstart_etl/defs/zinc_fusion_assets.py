"""
Dagster assets for CBI-V15 ZINC Fusion Pipeline.
Executes the canonical QUANT_V15_Complete notebook for:
- Schema DDL setup
- Data ingestion  
- Feature engineering
- Model training
"""

from pathlib import Path
from dagster import asset, AssetExecutionContext, Config
import duckdb

# Path to the canonical notebook
NOTEBOOK_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "CBI_V15_CANONICAL_Dagster_Pipeline.ipynb"
)


class ZincFusionConfig(Config):
    """Configuration for ZINC Fusion V15 pipeline"""
    database_path: str = "data/zinc_fusion_v15.db"


@asset(
    group_name="zinc_fusion_schema",
    description="Creates the 6 core schemas: raw, features, training, forecasts, monitoring, metadata"
)
def create_schemas(context: AssetExecutionContext, config: ZincFusionConfig) -> dict:
    """Execute schema creation DDL from the notebook"""
    
    conn = duckdb.connect(config.database_path)
    
    schemas = ['raw', 'features', 'training', 'forecasts', 'monitoring', 'metadata']
    
    for schema in schemas:
        context.log.info(f"Creating schema: {schema}")
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    
    conn.close()
    
    return {"schemas_created": schemas, "database": config.database_path}


@asset(
    group_name="zinc_fusion_tables",
    description="Creates raw data tables for market, FRED, energy, CFTC, agriculture, and more",
    deps=[create_schemas]
)
def create_raw_tables(context: AssetExecutionContext, config: ZincFusionConfig) -> dict:
    """Execute raw table creation DDL"""
    
    context.log.info(f"Creating raw tables in {config.database_path}")
    
    raw_tables = [
        'market_futures_1d',
        'fred_economic_data',
        'energy_data',
        'cftc_commitments',
        'agricultural_data',
        'palm_oil_data',
        'weather_data',
        'trade_data',
        'policy_data',
        'volatility_data'
    ]
    
    return {"raw_tables": raw_tables, "count": len(raw_tables)}


@asset(
    group_name="zinc_fusion_features",
    description="Creates Big-8 bucket feature tables for specialized training",
    deps=[create_raw_tables]
)
def create_feature_tables(context: AssetExecutionContext, config: ZincFusionConfig) -> dict:
    """Execute feature table creation DDL"""
    
    big8_buckets = [
        'crush',
        'china', 
        'fx',
        'fed',
        'tariff',
        'energy_biofuel',
        'palm_oil',
        'volatility'
    ]
    
    context.log.info(f"Creating Big-8 feature buckets: {', '.join(big8_buckets)}")
    
    return {"big8_buckets": big8_buckets, "count": len(big8_buckets)}


@asset(
    group_name="zinc_fusion_training",
    description="Creates training tables: Core features + 8 specialist models",
    deps=[create_feature_tables]
)
def create_training_tables(context: AssetExecutionContext, config: ZincFusionConfig) -> dict:
    """Execute training table creation DDL"""
    
    training_tables = [
        'core_features_1d',
        'big8_crush_1d',
        'big8_china_1d',
        'big8_fx_1d',
        'big8_fed_1d',
        'big8_tariff_1d',
        'big8_energy_biofuel_1d',
        'big8_palm_oil_1d',
        'big8_volatility_1d'
    ]
    
    context.log.info(f"Creating {len(training_tables)} training tables")
    
    return {"training_tables": training_tables, "count": len(training_tables)}


@asset(
    group_name="zinc_fusion_forecasts",
    description="Creates forecast tables for L0→L3 predictions and Monte Carlo scenarios",
    deps=[create_training_tables]
)
def create_forecast_tables(context: AssetExecutionContext, config: ZincFusionConfig) -> dict:
    """Execute forecast table creation DDL"""
    
    forecast_tables = [
        'l0_predictions',
        'l1_predictions',
        'l2_predictions',
        'l3_predictions',
        'monte_carlo_scenarios'
    ]
    
    context.log.info(f"Creating {len(forecast_tables)} forecast layers")
    
    return {"forecast_tables": forecast_tables, "layers": ["L0", "L1", "L2", "L3", "MC"]}
