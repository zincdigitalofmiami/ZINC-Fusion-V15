from pathlib import Path

from dagster import (
    Definitions,
    ScheduleDefinition,
    define_asset_job,
    link_code_references_to_git,
    with_source_code_references,
)
from dagster._core.definitions.metadata.source_code import AnchorBasedFilePathMapping

# ZINC Fusion V15 Assets
from .defs.zinc_fusion_assets import (
    create_schemas,
    create_raw_tables,
    create_feature_tables,
    create_training_tables,
    create_forecast_tables,
)

# Daily pipeline schedule
daily_refresh_schedule = ScheduleDefinition(
    job=define_asset_job(
        name="zinc_fusion_v15_pipeline",
        selection=[
            create_schemas,
            create_raw_tables,
            create_feature_tables,
            create_training_tables,
            create_forecast_tables,
        ]
    ),
    cron_schedule="0 0 * * *"  # Daily at midnight UTC
)

# ZINC Fusion V15 assets
zinc_fusion_assets = [
    create_schemas,
    create_raw_tables,
    create_feature_tables,
    create_training_tables,
    create_forecast_tables,
]

# Add source code references
zinc_fusion_assets = with_source_code_references(zinc_fusion_assets)

zinc_fusion_assets = link_code_references_to_git(
    assets_defs=zinc_fusion_assets,
    git_url="https://github.com/zincdigitalofmiami/ZINC-Fusion-V15/",
    git_branch="main",
    file_path_mapping=AnchorBasedFilePathMapping(
        local_file_anchor=Path(__file__).parent,
        file_anchor_path_in_repository="src/quickstart_etl/",
    ),
)

defs = Definitions(
    assets=zinc_fusion_assets,
    schedules=[daily_refresh_schedule],
)
