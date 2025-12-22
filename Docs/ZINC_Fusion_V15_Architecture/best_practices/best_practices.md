# Best Practices

- **Ingest once**: Write all raw data to the Bronze layer exactly as received.  Avoid pre‑processing during ingestion to ensure that the raw source can be reprocessed or audited later【872581463529754†L123-L134】.
- **Incremental processing**: Move data from Bronze to Silver and Gold using incremental, idempotent pipelines.  Use Dagster’s sensors and schedules to detect new data and process only changed partitions.
- **Schema enforcement**: Validate and enforce schemas in the Silver layer.  Use typed columns, handle missing values and deduplicate records【872581463529754†L146-L169】.
- **Transaction safety**: Employ ACID‑compliant storage like Delta Lake to ensure transactions commit fully and concurrently.  Configure checkpoints and vacuum policies to manage history.
- **Model management**: Use MLFlow to track experiments and register models.  Link model versions to the data snapshot they were trained on and to the code commit in VS Code.
- **Observability and testing**: Instrument pipelines with metrics.  Use data quality tests in Dagster and monitor results via dashboards served through Vercel.
- **Local analytics**: Use DuckDB for interactive SQL analysis on moderate‑sized datasets extracted from Bronze, Silver or Gold layers. DuckDB runs in‑process and can query Parquet files directly, making it ideal for exploratory analyses and testing pipeline logic locally.
- **Security and governance**: Apply role‑based access control at each layer.  Only operational teams should access Bronze, while analysts and data scientists use Silver and Gold.  Maintain audit logs for compliance.
