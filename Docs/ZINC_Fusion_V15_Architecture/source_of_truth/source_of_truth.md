# Source of Truth

A single source of truth is critical for reliable analytics.  In the medallion pattern the **Bronze** layer retains the original raw records as they arrived, enabling reprocessing and auditability【872581463529754†L123-L134】.  ZINC Fusion preserves this source of truth by storing all ingested files in object storage with versioning enabled and by capturing metadata such as file name and ingestion timestamp.  Downstream Silver and Gold tables are derived from Bronze, but they never overwrite the original data.  This approach prevents data loss and facilitates reproducibility; if transformation logic changes, pipelines can be rerun against historical raw data.

Model runs and experiments managed by **MLFlow** are also versioned, providing an immutable record of how predictions were generated.  Combined with Git‑based version control in **VS Code**, the platform ensures that both data and code have traceable provenance.
