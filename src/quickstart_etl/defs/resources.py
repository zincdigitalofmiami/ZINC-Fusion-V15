"""
Resources - ZINC Fusion V15
Centralized resource definitions for ultra-organized Dagster setup.
"""

from dagster import ConfigurableResource, InitResourceContext
import duckdb
import os
from pathlib import Path
from typing import Optional


class DuckDBResource(ConfigurableResource):
    """Ultra-organized DuckDB resource with enhanced capabilities"""

    database_path: str = "data/zinc_fusion_v15.db"
    read_only: bool = False
    connection_timeout: int = 30

    def get_connection(self):
        """Get a DuckDB connection with proper error handling"""

        # Ensure data directory exists
        db_path = Path(self.database_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            conn = duckdb.connect(
                self.database_path,
                read_only=self.read_only,
                config={
                    "threads": 4,
                    "memory_limit": "2GB",
                    "temp_directory": "data/temp/",
                },
            )

            # Install required extensions
            conn.execute("INSTALL spatial")
            conn.execute("LOAD spatial")

            return conn

        except Exception as e:
            raise Exception(
                f"Failed to connect to DuckDB at {self.database_path}: {str(e)}"
            )

    def execute_query(self, query: str, params: Optional[tuple] = None):
        """Execute a query with proper connection handling"""
        conn = self.get_connection()
        try:
            if params:
                result = conn.execute(query, params)
            else:
                result = conn.execute(query)
            return result.fetchall()
        finally:
            conn.close()

    def get_table_info(self, schema: str, table: str) -> dict:
        """Get comprehensive table information"""
        conn = self.get_connection()
        try:
            # Row count
            count = conn.execute(f"SELECT COUNT(*) FROM {schema}.{table}").fetchone()[0]

            # Column info
            columns = conn.execute(f"DESCRIBE {schema}.{table}").df()

            # Date range if applicable
            date_cols = columns[
                columns["column_name"].str.contains("date|time", case=False, na=False)
            ]["column_name"].tolist()
            date_range = None
            if date_cols:
                date_col = date_cols[0]
                try:
                    date_range = conn.execute(
                        f"SELECT MIN({date_col}), MAX({date_col}) FROM {schema}.{table}"
                    ).fetchone()
                except:
                    pass

            return {
                "rows": count,
                "columns": len(columns),
                "column_names": columns["column_name"].tolist(),
                "date_range": date_range,
            }
        finally:
            conn.close()


class DataValidationResource(ConfigurableResource):
    """Resource for comprehensive data validation"""

    max_null_percentage: float = 0.5  # 50% max nulls allowed
    min_row_count: int = 100
    required_date_range_days: int = 30

    def validate_table_quality(
        self, duckdb_resource: DuckDBResource, schema: str, table: str
    ) -> dict:
        """Comprehensive table validation"""

        conn = duckdb_resource.get_connection()

        try:
            # Basic stats
            total_rows = conn.execute(
                f"SELECT COUNT(*) FROM {schema}.{table}"
            ).fetchone()[0]

            # Column analysis
            columns = conn.execute(f"DESCRIBE {schema}.{table}").df()

            validation_results = {
                "table": f"{schema}.{table}",
                "total_rows": total_rows,
                "total_columns": len(columns),
                "sufficient_rows": total_rows >= self.min_row_count,
                "issues": [],
            }

            # Check for excessive nulls in each column
            for _, col in columns.iterrows():
                col_name = col["column_name"]
                try:
                    null_count = conn.execute(
                        f"SELECT COUNT(*) FROM {schema}.{table} WHERE {col_name} IS NULL"
                    ).fetchone()[0]
                    null_pct = null_count / total_rows if total_rows > 0 else 0

                    if null_pct > self.max_null_percentage:
                        validation_results["issues"].append(
                            {
                                "type": "high_null_percentage",
                                "column": col_name,
                                "null_percentage": null_pct,
                                "severity": "warning" if null_pct < 0.8 else "error",
                            }
                        )
                except:
                    # Skip columns that can't be checked for nulls
                    pass

            # Overall quality score
            quality_score = 1.0
            if not validation_results["sufficient_rows"]:
                quality_score -= 0.3

            error_issues = [
                i for i in validation_results["issues"] if i["severity"] == "error"
            ]
            warning_issues = [
                i for i in validation_results["issues"] if i["severity"] == "warning"
            ]

            quality_score -= len(error_issues) * 0.2
            quality_score -= len(warning_issues) * 0.1

            validation_results["quality_score"] = max(0.0, quality_score)
            validation_results["passed"] = quality_score >= 0.7

            return validation_results

        finally:
            conn.close()


class MLflowTrackingResource(ConfigurableResource):
    """Resource for MLflow experiment tracking"""

    tracking_uri: str = "file://./mlruns"
    experiment_name: str = "zinc-fusion-v15"

    def setup_experiment(self) -> str:
        """Set up MLflow experiment"""
        try:
            import mlflow

            mlflow.set_tracking_uri(self.tracking_uri)

            # Create experiment if it doesn't exist
            try:
                experiment_id = mlflow.create_experiment(self.experiment_name)
            except:
                experiment = mlflow.get_experiment_by_name(self.experiment_name)
                experiment_id = experiment.experiment_id

            mlflow.set_experiment(self.experiment_name)

            return experiment_id

        except ImportError:
            raise Exception("MLflow not installed. Run: pip install mlflow")

    def log_asset_metadata(self, asset_name: str, metadata: dict):
        """Log asset execution metadata to MLflow"""
        try:
            import mlflow

            with mlflow.start_run(run_name=f"asset_{asset_name}"):
                for key, value in metadata.items():
                    if isinstance(value, (int, float)):
                        mlflow.log_metric(key, value)
                    else:
                        mlflow.log_param(key, str(value))

        except ImportError:
            pass  # MLflow not available, skip logging


class WeatherAPIResource(ConfigurableResource):
    """Resource for weather data ingestion"""

    base_url: str = "https://archive-api.open-meteo.com/v1/archive"
    rate_limit_delay: float = 1.0  # seconds between requests
    timeout: int = 60

    def fetch_station_data(
        self, latitude: float, longitude: float, start_date: str, end_date: str
    ) -> dict:
        """Fetch weather data for a specific station"""
        import requests
        import time

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start_date,
            "end_date": end_date,
            "daily": [
                "temperature_2m_max",
                "temperature_2m_min",
                "temperature_2m_mean",
                "precipitation_sum",
                "snowfall_sum",
                "rain_sum",
                "wind_speed_10m_max",
                "wind_gusts_10m_max",
            ],
            "timezone": "UTC",
        }

        try:
            time.sleep(self.rate_limit_delay)  # Rate limiting

            response = requests.get(self.base_url, params=params, timeout=self.timeout)
            response.raise_for_status()

            return response.json()

        except requests.exceptions.RequestException as e:
            raise Exception(f"Weather API request failed: {str(e)}")
