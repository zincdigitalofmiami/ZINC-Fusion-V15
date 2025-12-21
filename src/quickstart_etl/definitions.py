from dagster import (
    Definitions,
    ScheduleDefinition,
    define_asset_job,
)

# ZINC Fusion V15 Assets
from .defs.zinc_fusion_assets import (
    create_schemas,
    create_raw_tables,
    create_feature_tables,
    create_training_tables,
    create_forecast_tables,
    DuckDBResource,
)

# Default job (used by tests and local runs)
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

# Named pipeline job (kept stable for schedules/ops)
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

# Daily pipeline schedule (6:00 AM EST = 11:00 AM UTC)
daily_refresh_schedule = ScheduleDefinition(
    job=zinc_fusion_v15_pipeline_job,
    cron_schedule="0 11 * * *",  # Daily at 6:00 AM EST (11:00 AM UTC)
)

# ZINC Fusion V15 assets
zinc_fusion_assets = [
    create_schemas,
    create_raw_tables,
    create_feature_tables,
    create_training_tables,
    create_forecast_tables,
]

defs = Definitions(
    assets=zinc_fusion_assets,
    jobs=[all_assets_job, zinc_fusion_v15_pipeline_job],
    schedules=[daily_refresh_schedule],
    resources={
        "duckdb_resource": DuckDBResource(database_path="data/zinc_fusion_v15.db")
    },
)
