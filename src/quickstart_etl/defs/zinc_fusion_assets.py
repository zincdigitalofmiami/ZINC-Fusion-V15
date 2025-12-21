"""
Dagster assets for CBI-V15 ZINC Fusion Pipeline.
Executes the canonical QUANT_V15_Complete notebook DDL for:
- Schema DDL setup
- Data ingestion tables
- Feature engineering tables
- Model training tables
"""

from pathlib import Path
from dagster import asset, AssetExecutionContext, ConfigurableResource, MetadataValue
import duckdb
import os

# Path to the canonical notebook
NOTEBOOK_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "CBI_V15_CANONICAL_Dagster_Pipeline.ipynb"
)


class DuckDBResource(ConfigurableResource):
    """DuckDB connection resource for ZINC Fusion V15"""

    database_path: str = "data/zinc_fusion_v15.db"

    def get_connection(self):
        """Get a DuckDB connection, creating data directory if needed"""
        os.makedirs(
            os.path.dirname(self.database_path)
            if os.path.dirname(self.database_path)
            else "data",
            exist_ok=True,
        )
        return duckdb.connect(self.database_path)


@asset(
    group_name="zinc_fusion_schema",
    description="Creates the 6 core schemas: raw, features, training, forecasts, monitoring, metadata",
)
def create_schemas(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> dict:
    """Execute schema creation DDL from the notebook"""

    conn = duckdb_resource.get_connection()

    schemas = ["raw", "features", "training", "forecasts", "monitoring", "metadata"]

    for schema in schemas:
        context.log.info(f"Creating schema: {schema}")
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")

    conn.close()

    return {
        "schemas_created": schemas,
        "database": duckdb_resource.database_path,
        "metadata": {
            "schema_count": MetadataValue.int(len(schemas)),
            "schemas": MetadataValue.md("\n".join([f"- `{s}`" for s in schemas])),
        },
    }


@asset(
    group_name="zinc_fusion_tables",
    description="Creates raw data tables for market, FRED, energy, CFTC, agriculture, and more",
    deps=[create_schemas],
)
def create_raw_tables(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> dict:
    """Execute raw table creation DDL"""

    conn = duckdb_resource.get_connection()

    # Market futures tables
    context.log.info("Creating market futures tables (1d, 1h)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS raw.market_futures_1d (
            as_of_date      DATE NOT NULL,
            symbol          VARCHAR NOT NULL,
            open            DECIMAL(12, 4),
            high            DECIMAL(12, 4),
            low             DECIMAL(12, 4),
            close           DECIMAL(12, 4),
            volume          BIGINT,
            open_interest   BIGINT,
            source          VARCHAR DEFAULT 'yahoo',
            ingested_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (as_of_date, symbol)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS raw.market_futures_1h (
            ts_event        TIMESTAMP NOT NULL,
            symbol          VARCHAR NOT NULL,
            open            DECIMAL(12, 4),
            high            DECIMAL(12, 4),
            low             DECIMAL(12, 4),
            close           DECIMAL(12, 4),
            volume          BIGINT,
            source          VARCHAR DEFAULT 'databento',
            ingested_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (ts_event, symbol)
        )
    """)

    # Economic indicators (FRED)
    context.log.info("Creating economic indicators tables (1d, 1w, 1m)")
    for cadence in ["1d", "1w", "1m"]:
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS raw.economic_indicators_{cadence} (
                as_of_date      DATE NOT NULL,
                series_id       VARCHAR NOT NULL,
                value           DOUBLE,
                series_name     VARCHAR,
                bucket          VARCHAR,
                source          VARCHAR DEFAULT 'fred',
                ingested_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (as_of_date, series_id)
            )
        """)

    conn.close()

    raw_tables = [
        "market_futures_1d",
        "market_futures_1h",
        "economic_indicators_1d",
        "economic_indicators_1w",
        "economic_indicators_1m",
    ]

    return {
        "raw_tables": raw_tables,
        "count": len(raw_tables),
        "metadata": {
            "tables_created": MetadataValue.int(len(raw_tables)),
            "database_path": MetadataValue.text(duckdb_resource.database_path),
        },
    }


@asset(
    group_name="zinc_fusion_features",
    description="Creates Big-8 bucket feature tables for specialized training",
    deps=[create_raw_tables],
)
def create_feature_tables(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> dict:
    """Execute feature table creation DDL"""

    conn = duckdb_resource.get_connection()

    big8_buckets = [
        "crush",
        "china",
        "fx",
        "fed",
        "tariff",
        "energy_biofuel",
        "palm_oil",
        "volatility",
    ]

    context.log.info(f"Creating Big-8 feature bucket tables")

    for bucket in big8_buckets:
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS features.{bucket}_1d (
                as_of_date      DATE NOT NULL,
                feature_data    VARCHAR,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (as_of_date)
            )
        """)

    conn.close()

    return {
        "big8_buckets": big8_buckets,
        "count": len(big8_buckets),
        "metadata": {
            "buckets_created": MetadataValue.md(
                "\n".join([f"- `features.{b}_1d`" for b in big8_buckets])
            )
        },
    }


@asset(
    group_name="zinc_fusion_training",
    description="Creates training tables: Core features + 8 specialist models",
    deps=[create_feature_tables],
)
def create_training_tables(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> dict:
    """Execute training table creation DDL"""

    conn = duckdb_resource.get_connection()

    # Core features table
    context.log.info("Creating core features training table")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS training.core_features_1d (
            as_of_date      DATE NOT NULL,
            target          DOUBLE,
            features        VARCHAR,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (as_of_date)
        )
    """)

    # Big-8 specialist tables
    big8_models = [
        "crush",
        "china",
        "fx",
        "fed",
        "tariff",
        "energy_biofuel",
        "palm_oil",
        "volatility",
    ]

    context.log.info(f"Creating {len(big8_models)} specialist training tables")

    for model in big8_models:
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS training.big8_{model}_1d (
                as_of_date      DATE NOT NULL,
                prediction      DOUBLE,
                features        VARCHAR,
                model_version   VARCHAR,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (as_of_date)
            )
        """)

    conn.close()

    training_tables = ["core_features_1d"] + [f"big8_{m}_1d" for m in big8_models]

    return {
        "training_tables": training_tables,
        "count": len(training_tables),
        "metadata": {
            "core_table": MetadataValue.text("training.core_features_1d"),
            "specialist_models": MetadataValue.int(len(big8_models)),
        },
    }


@asset(
    group_name="zinc_fusion_forecasts",
    description="Creates forecast tables for L0→L3 predictions and Monte Carlo scenarios",
    deps=[create_training_tables],
)
def create_forecast_tables(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> dict:
    """Execute forecast table creation DDL"""

    conn = duckdb_resource.get_connection()

    # L0-L3 prediction layers
    for layer in range(4):
        context.log.info(f"Creating L{layer} predictions table")
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS forecasts.l{layer}_predictions (
                as_of_date      DATE NOT NULL,
                forecast_date   DATE NOT NULL,
                prediction      DOUBLE,
                confidence      DOUBLE,
                model_version   VARCHAR,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (as_of_date, forecast_date)
            )
        """)

    # Monte Carlo scenarios
    context.log.info("Creating Monte Carlo scenarios table")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS forecasts.monte_carlo_scenarios (
            scenario_id     VARCHAR NOT NULL,
            as_of_date      DATE NOT NULL,
            forecast_date   DATE NOT NULL,
            scenario_value  DOUBLE,
            probability     DOUBLE,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (scenario_id, as_of_date, forecast_date)
        )
    """)

    conn.close()

    forecast_tables = [f"l{i}_predictions" for i in range(4)] + [
        "monte_carlo_scenarios"
    ]

    return {
        "forecast_tables": forecast_tables,
        "layers": ["L0", "L1", "L2", "L3", "MC"],
        "count": len(forecast_tables),
        "metadata": {
            "prediction_layers": MetadataValue.int(4),
            "total_tables": MetadataValue.int(len(forecast_tables)),
            "database_ready": MetadataValue.bool(True),
        },
    }
