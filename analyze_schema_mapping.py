#!/usr/bin/env python3
"""
Analyze Historical Data parquet files and map to proper DuckDB schema
"""
import pandas as pd
from pathlib import Path
import duckdb

HIST_DATA = Path("/Volumes/Satechi Hub/Historical Data")

# Define proper schema mapping
SCHEMA_MAP = {
    # RAW DATA LAYER
    'raw': {
        'databento_futures_ohlcv_1d': 'market_futures_1d',
        'databento_futures_ohlcv_1h': 'market_futures_1h',
        'databento_options_ohlcv_1d': 'market_options_1d',
        'fred_economic': 'fred_observations_1d',
        'weather_noaa': 'weather_observations_1d',
        'cftc_cot': 'cftc_cot_1w',
        'cftc_cot_tff': 'cftc_cot_tff_1w',
        'eia_biofuels': 'eia_observations_1d',
        'epa_rin_prices': 'epa_rin_prices_1d',
        'usda_export_sales': 'usda_export_sales_1w',
        'usda_wasde': 'usda_wasde_1m',
        'usda_crop_progress': 'usda_crop_progress_1w',
        'bucket_news': 'news_articles_event',
        'scrapecreators_news_buckets': 'news_buckets_event',
        'scrapecreators_trump': 'news_trump_event',
        'profarmer_articles': 'profarmer_articles_event',
        'profarmer_crop_tour': 'profarmer_crop_tour_event',
        'tradingeconomics_calendar': 'tradingeconomics_calendar_event',
        'tradingeconomics_indicators': 'tradingeconomics_indicators_1d',
    },
    
    # STAGING LAYER
    'staging': {
        'cftc_normalized': 'cftc_normalized_1w',
        'fred_macro_clean': 'fred_macro_clean_1d',
        'china_daily': 'china_daily_1d',
        'crush_daily': 'crush_daily_1d',
        'daily_returns': 'daily_returns_1d',
        'market_daily': 'market_daily_1d',
        'ohlcv_daily': 'ohlcv_daily_1d',
        'news_bucketed': 'news_bucketed_event',
        'news_daily': 'news_daily_1d',
        'sentiment_buckets': 'sentiment_buckets_1d',
    },
    
    # FEATURES LAYER
    'features': {
        'daily_ml_matrix_zl': 'daily_matrix_1d',
        'daily_ml_matrix_zl_v15': 'daily_matrix_v15_1d',
        'technical_indicators_all_symbols': 'technical_indicators_1d',
        'bucket_biofuel': 'bucket_biofuel_1d',
        'bucket_china': 'bucket_china_1d',
        'bucket_crush': 'bucket_crush_1d',
        'bucket_energy': 'bucket_energy_1d',
        'bucket_fed': 'bucket_fed_1d',
        'bucket_fx': 'bucket_fx_1d',
        'bucket_tariff': 'bucket_tariff_1d',
        'bucket_volatility': 'bucket_volatility_1d',
        'bucket_scores': 'bucket_scores_1d',
        'rolling_corr_beta': 'rolling_corr_beta_1d',
        'targets': 'targets_1d',
    },
    
    # TRAINING LAYER
    'training': {
        'bucket_predictions': 'bucket_predictions_1d',
        'core_ts_predictions': 'core_predictions_1d',
        'ensemble_weights': 'ensemble_weights_1d',
        'feature_preconditioning_params_zl': 'feature_preconditioning_params',
        'meta_ml_matrix': 'meta_matrix_1d',
        'specialist_signals': 'specialist_signals_1d',
        'stacking_features': 'stacking_features_1d',
    },
    
    # FORECASTS LAYER
    'forecasts': {
        'monte_carlo_scenarios': 'scenarios_1d',
        'procurement_recommendations': 'procurement_actions_1d',
        'specialist_signals': 'specialist_signals_1d',
        'zl_predictions': 'predictions_zl_1d',
        'zl_v15_predictions': 'predictions_zl_v15_1d',
    },
    
    # REFERENCE/METADATA
    'metadata': {
        'big8_bucket_sources': 'bucket_sources_static',
        'symbols': 'symbols_static',
        'trading_calendar': 'trading_calendar_static',
        'train_val_test_splits': 'train_val_test_splits_static',
    },
    
    # SPECIALIST LAYER
    'specialist': {
        'driver_group': 'driver_groups_static',
        'feature_catalog': 'feature_catalog_static',
        'feature_to_driver_group_map': 'feature_driver_map_static',
        'geo_admin_regions': 'geo_admin_regions_static',
        'geo_countries': 'geo_countries_static',
        'model_registry': 'model_registry_static',
        'regime_calendar': 'regime_calendar_static',
        'regime_weights': 'regime_weights_static',
        'weather_location_registry': 'weather_locations_static',
    },
    
    # MONITORING/OPS
    'monitoring': {
        'alert_history': 'alert_history_event',
        'data_quality_log': 'data_quality_1d',
        'ensemble_topology': 'ensemble_topology_static',
        'ingestion_completion': 'ingestion_completion_event',
        'ingestion_status': 'ingestion_status_event',
        'job_locks': 'job_locks_event',
        'model_performance': 'model_performance_1d',
        'pipeline_metrics': 'pipeline_metrics_event',
        'training_runs': 'training_runs_event',
    },
    
    # EXPLANATIONS/SHAP
    'explanations': {
        'shap_values': 'shap_values_1d',
    }
}

def find_parquet_files():
    """Find all parquet files and map them"""
    files = []
    
    for root, dirs, filenames in HIST_DATA.rglob('*.parquet'):
        for filepath in filenames:
            if filepath.is_file():
                # Get relative path and extract meaningful parts
                rel_path = filepath.relative_to(HIST_DATA)
                parts = rel_path.parts
                
                # Skip duplicates (MotherDuck vs All Other)
                if 'MotherDuck' in parts:
                    continue  # Use All Other or direct sources
                
                filename = filepath.stem
                parent_folder = parts[-2] if len(parts) > 1 else 'unknown'
                
                files.append({
                    'filepath': filepath,
                    'filename': filename,
                    'folder': parent_folder,
                    'size_mb': filepath.stat().st_size / 1024 / 1024
                })
    
    return files

def map_to_schema(filename, folder):
    """Map parquet filename to proper schema.table"""
    
    # Search through schema map
    for schema, mappings in SCHEMA_MAP.items():
        if filename in mappings:
            return schema, mappings[filename]
    
    # Fallback - unknown
    return 'unknown', filename

def analyze_parquet_structure(filepath):
    """Read parquet metadata without loading full data"""
    try:
        df = pd.read_parquet(filepath)
        return {
            'rows': len(df),
            'columns': list(df.columns),
            'dtypes': {col: str(dtype) for col, dtype in df.dtypes.items()},
            'sample': df.head(3).to_dict('records') if len(df) > 0 else []
        }
    except Exception as e:
        return {'error': str(e)}

# Main analysis
print("="*80)
print("HISTORICAL DATA SCHEMA MAPPING ANALYSIS")
print("="*80)

files = find_parquet_files()
print(f"\nFound {len(files)} parquet files to analyze\n")

# Group by schema
schema_groups = {}
for file_info in files:
    schema, table = map_to_schema(file_info['filename'], file_info['folder'])
    
    if schema not in schema_groups:
        schema_groups[schema] = []
    
    schema_groups[schema].append({
        **file_info,
        'target_schema': schema,
        'target_table': table
    })

# Print mapping
for schema in sorted(schema_groups.keys()):
    files_in_schema = schema_groups[schema]
    total_size = sum(f['size_mb'] for f in files_in_schema)
    
    print(f"\n{'='*80}")
    print(f"SCHEMA: {schema.upper()} ({len(files_in_schema)} files, {total_size:.2f} MB)")
    print('='*80)
    
    for f in sorted(files_in_schema, key=lambda x: x['size_mb'], reverse=True):
        print(f"{f['size_mb']:>8.2f} MB  {f['filename']:50} → {f['target_schema']}.{f['target_table']}")

# Analyze structure of key files
print("\n\n" + "="*80)
print("STRUCTURE ANALYSIS - KEY FILES")
print("="*80)

key_files = [
    'databento_futures_ohlcv_1d',
    'databento_futures_ohlcv_1h',
    'fred_economic',
    'weather_noaa',
    'cftc_cot',
    'daily_ml_matrix_zl_v15',
]

for filename in key_files:
    # Find the file
    file_match = next((f for f in files if f['filename'] == filename), None)
    if not file_match:
        print(f"\n❌ {filename} - NOT FOUND")
        continue
    
    print(f"\n{'-'*80}")
    print(f"FILE: {filename}")
    print(f"PATH: {file_match['filepath']}")
    print(f"SIZE: {file_match['size_mb']:.2f} MB")
    
    schema, table = map_to_schema(filename, file_match['folder'])
    print(f"TARGET: {schema}.{table}")
    
    structure = analyze_parquet_structure(file_match['filepath'])
    if 'error' in structure:
        print(f"ERROR: {structure['error']}")
    else:
        print(f"\nRows: {structure['rows']:,}")
        print(f"Columns: {len(structure['columns'])}")
        print("\nColumn list:")
        for col in structure['columns'][:20]:
            dtype = structure['dtypes'].get(col, 'unknown')
            print(f"  - {col:40} {dtype}")
        if len(structure['columns']) > 20:
            print(f"  ... and {len(structure['columns']) - 20} more columns")

print("\n" + "="*80)
print("MIGRATION PLAN READY")
print("="*80)
print("\nNext step: Create migration script to load all files into new DuckDB")
