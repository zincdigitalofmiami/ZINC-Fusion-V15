# Dependency Audit Report

**Project:** ZINC Fusion V15
**Date:** 2025-12-24
**Total Locked Packages:** 90

---

## Executive Summary

This audit analyzed the project's dependencies for outdated packages, security vulnerabilities, and unnecessary bloat. Key findings include:

- **1 Critical Issue:** Missing dashboard dependencies in `pyproject.toml`
- **3 Outdated Packages:** Minor/patch updates available
- **0 Active Security Vulnerabilities:** DuckDB is on a secure version
- **Moderate Bloat:** 90 transitive dependencies for 5 direct dependencies (expected for Dagster)

---

## 1. Missing Dependencies (Critical)

The `dashboard/zinc_fusion_dashboard.py` imports packages that are **not declared** in `pyproject.toml`:

| Package | Used In | Status |
|---------|---------|--------|
| `dash` | Dashboard | **MISSING** |
| `dash-bootstrap-components` | Dashboard | **MISSING** |
| `plotly` | Dashboard | **MISSING** |
| `mlflow` | Dashboard + Pipeline | **MISSING** |

### Recommendation

Add to `pyproject.toml`:

```toml
dependencies = [
    "dagster",
    "duckdb>=0.9.0",
    "numpy",
    "pandas",
    "matplotlib",
    "dash>=2.0",                    # ADD
    "dash-bootstrap-components",    # ADD
    "plotly>=5.0",                  # ADD
    "mlflow>=2.0",                  # ADD
]
```

---

## 2. Outdated Packages

| Package | Current | Latest | Gap | Priority |
|---------|---------|--------|-----|----------|
| dagster | 1.11.11 | 1.12.7 | Minor | Medium |
| dagster-webserver | 1.11.11 | 1.12.6 | Minor | Medium |
| pandas | 2.3.2 | 2.3.3 | Patch | Low |
| duckdb | 1.4.3 | 1.4.3 | Current | N/A |
| numpy | 2.2.6/2.3.3 | 2.3.3 | Current | N/A |
| matplotlib | 3.10.6 | 3.10.6 | Current | N/A |

### Recommendation

Update Dagster to the latest 1.12.x series for bug fixes and improvements:

```bash
uv lock --upgrade-package dagster --upgrade-package dagster-webserver --upgrade-package dagster-graphql --upgrade-package dagster-pipes --upgrade-package dagster-shared
```

---

## 3. Security Analysis

### DuckDB (SAFE)

- **Current version:** 1.4.3
- **Vulnerability CVE-2025-64429** (database encryption issues) was fixed in 1.4.2
- **Status:** Project is using a patched version

### NPM Compromise (NOT APPLICABLE)

- CVE-2025-59037 affected DuckDB Node.js packages only
- Python (PyPI) distribution was not affected

### Other Dependencies

- **pandas, numpy, matplotlib:** No known 2025 CVEs affecting current versions
- **dagster:** No known security advisories for 1.11.x+

---

## 4. Bloat Analysis

### Dependency Tree Summary

```
Direct dependencies:     5 (+ 2 dev)
Transitive dependencies: 83
Total packages:          90
```

### Heavy Transitive Dependencies

The Dagster ecosystem brings in significant dependencies:

| Dependency Chain | Packages | Justification |
|------------------|----------|---------------|
| dagster → graphql | gql, graphene, graphql-core, graphql-relay | Required for Dagster UI |
| dagster → web | starlette, uvicorn, httptools, websockets | Required for webserver |
| dagster → grpc | grpcio, grpcio-health-checking, protobuf | Required for distributed execution |
| dagster → db | sqlalchemy, alembic | Required for run storage |

### Verdict: **Expected Bloat**

The 90 packages are primarily from Dagster's rich feature set. This is normal for a data orchestration platform.

### Potential Optimizations

1. **For production deployments without UI:**
   - Move `dagster-webserver` to optional dependencies if UI not needed in all environments

2. **Consider splitting environments:**
   ```toml
   [dependency-groups]
   dev = ["dagster-webserver", "pytest"]
   dashboard = ["dash", "dash-bootstrap-components", "plotly"]
   ```

---

## 5. Version Pinning Review

### Current Strategy

- Unpinned: `dagster`, `numpy`, `pandas`, `matplotlib`
- Lower-bound only: `duckdb>=0.9.0`

### Recommendation

For production stability, consider tighter constraints:

```toml
dependencies = [
    "dagster>=1.11,<2.0",     # Pin to major version
    "duckdb>=1.4.2,<2.0",     # Security fix minimum
    "numpy>=2.0,<3.0",
    "pandas>=2.0,<3.0",
    "matplotlib>=3.8,<4.0",
]
```

---

## 6. Action Items

### High Priority

- [ ] Add missing dashboard dependencies (`dash`, `plotly`, `mlflow`, `dash-bootstrap-components`)

### Medium Priority

- [ ] Update Dagster from 1.11.11 to 1.12.x
- [ ] Consider version pinning strategy for production

### Low Priority

- [ ] Update pandas from 2.3.2 to 2.3.3
- [ ] Consider splitting dashboard dependencies into optional group

---

## Appendix: Full Dependency List

<details>
<summary>Click to expand all 90 packages</summary>

| Package | Version | Purpose |
|---------|---------|---------|
| alembic | 1.16.5 | Database migrations (dagster) |
| annotated-types | 0.7.0 | Type hints (pydantic) |
| antlr4-python3-runtime | 4.13.2 | Parser (dagster) |
| anyio | 4.10.0 | Async I/O (starlette) |
| backoff | 2.2.1 | Retry logic (dagster) |
| certifi | 2025.8.3 | SSL certificates |
| charset-normalizer | 3.4.3 | Text encoding (requests) |
| click | 8.1.8 | CLI framework (dagster) |
| colorama | 0.4.6 | Terminal colors (Windows) |
| coloredlogs | 14.0 | Logging (dagster) |
| contourpy | 1.3.2/1.3.3 | Contours (matplotlib) |
| cycler | 0.12.1 | Colors (matplotlib) |
| dagster | 1.11.11 | **Core** |
| dagster-graphql | 1.11.11 | GraphQL API |
| dagster-pipes | 1.11.11 | Subprocess execution |
| dagster-shared | 1.11.11 | Shared utilities |
| dagster-webserver | 1.11.11 | Web UI (dev) |
| docstring-parser | 0.17.0 | Docs (dagster) |
| duckdb | 1.4.3 | **Core** - Analytics DB |
| exceptiongroup | 1.3.0 | Backport (Python <3.11) |
| filelock | 3.19.1 | File locking |
| fonttools | 4.60.0 | Fonts (matplotlib) |
| fsspec | 2025.9.0 | Filesystem abstraction |
| gql | 3.5.3 | GraphQL client |
| graphene | 3.4.3 | GraphQL framework |
| graphql-core | 3.2.6 | GraphQL implementation |
| graphql-relay | 3.2.0 | GraphQL relay spec |
| greenlet | 3.2.4 | Coroutines (sqlalchemy) |
| grpcio | 1.75.0 | gRPC (dagster) |
| grpcio-health-checking | 1.75.0 | gRPC health checks |
| h11 | 0.16.0 | HTTP/1.1 (uvicorn) |
| httptools | 0.6.4 | HTTP parsing (uvicorn) |
| humanfriendly | 10.0 | Human-readable output |
| idna | 3.10 | Domain names |
| iniconfig | 2.1.0 | Config parsing (pytest) |
| jinja2 | 3.1.6 | Templating (dagster) |
| kiwisolver | 1.4.9 | Optimization (matplotlib) |
| mako | 1.3.10 | Templating (alembic) |
| markdown-it-py | 4.0.0 | Markdown (rich) |
| markupsafe | 3.0.2 | HTML escaping (jinja2) |
| matplotlib | 3.10.6 | **Core** - Plotting |
| mdurl | 0.1.2 | URL parsing (markdown-it-py) |
| multidict | 6.6.4 | Multi-valued dicts |
| numpy | 2.2.6/2.3.3 | **Core** - Numerical |
| packaging | 25.0 | Version handling |
| pandas | 2.3.2 | **Core** - DataFrames |
| pillow | 11.3.0 | Image processing (matplotlib) |
| pluggy | 1.6.0 | Plugin system (pytest) |
| propcache | 0.3.2 | Property caching |
| protobuf | 6.32.1 | Protocol buffers (grpc) |
| psutil | 7.1.0 | Process utilities |
| pydantic | 2.11.9 | Validation (dagster) |
| pydantic-core | 2.33.2 | Pydantic internals |
| pygments | 2.19.2 | Syntax highlighting |
| pyparsing | 3.2.5 | Parsing (matplotlib) |
| pyreadline3 | 3.5.4 | Readline (Windows) |
| pytest | 8.4.2 | Testing (dev) |
| python-dateutil | 2.9.0.post0 | Date utilities |
| python-dotenv | 1.1.1 | Env files (dagster) |
| pytz | 2025.2 | Timezones |
| pywin32 | 311 | Windows API (Windows) |
| pyyaml | 6.0.2 | YAML parsing |
| requests | 2.32.5 | HTTP client |
| requests-toolbelt | 1.0.0 | Requests extensions |
| rich | 14.1.0 | Terminal formatting |
| setuptools | 80.9.0 | Build system |
| six | 1.17.0 | Python 2/3 compat |
| sniffio | 1.3.1 | Async detection |
| sqlalchemy | 2.0.43 | ORM (dagster storage) |
| starlette | 0.48.0 | ASGI framework |
| structlog | 25.4.0 | Structured logging |
| tabulate | 0.9.0 | Table formatting |
| tomli | 2.2.1 | TOML parsing (Python <3.11) |
| tomlkit | 0.13.2 | TOML manipulation |
| toposort | 1.10 | Topological sorting |
| tqdm | 4.67.1 | Progress bars |
| typing-extensions | 4.15.0 | Type hints backport |
| typing-inspection | 0.4.1 | Type introspection |
| tzdata | 2025.2 | Timezone data |
| universal-pathlib | 0.2.6 | Path abstraction |
| urllib3 | 2.5.0 | HTTP client |
| uvicorn | 0.36.0 | ASGI server |
| uvloop | 0.21.0 | Fast event loop |
| watchdog | 6.0.0 | File watching |
| watchfiles | 1.1.0 | File watching |
| websockets | 15.0.1 | WebSocket support |
| yarl | 1.20.1 | URL handling |
| zinc-fusion-v15 | 0.1.0 | This project |

</details>

---

*Generated by dependency audit tool*
