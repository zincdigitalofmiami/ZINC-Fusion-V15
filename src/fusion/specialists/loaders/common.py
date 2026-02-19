"""Shared utilities for specialist data loaders."""

# Specialist data loaders: each specialist gets only the data it needs.
# No shared matrix. News sources are discovered dynamically by tag.

import logging
from datetime import date

import pandas as pd

from fusion.db.connection import get_write_connection

logger = logging.getLogger(__name__)

# Allowlist of valid specialist buckets (Big-11 + extras)
VALID_SPECIALIST_BUCKETS = frozenset(
    {
        "crush",
        "china",
        "energy",
        "fx",
        "fed",
        "volatility",
        "substitutes",
        "palm",
        "biofuel",
        "tariff",
        "trump_effect",
    }
)

# Allowlist of schemas that may contain specialist-tagged news tables
_ALLOWED_NEWS_SCHEMAS = frozenset({"alt", "econ", "features"})


def load_news_for_specialist(
    specialist_bucket: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pd.DataFrame:
    """
    Load ALL news articles tagged for this specialist from ALL tables.

    Scans all tables with specialist_tags column and returns articles
    where this specialist is in the tags array.

    New table structure (2026-01-31):
    - alt.econ_news_event: FRED blog (Federal Reserve economic research)
    - alt.executive_actions_event: WhiteHouse presidential documents
    - alt.policy_news_event: Other policy sources (ICE, CBP, AEI, FarmDoc)
    - alt.profarmer_news_event: ProFarmer premium ag news
    - alt.legislation_1d: Federal Register legislation

    Returns:
        DataFrame indexed by trade_date with:
        - news_article_count: count of articles for this specialist on this date
        - news_headline_text: concatenated headlines for NLP features
    """
    # Validate specialist_bucket against allowlist
    if specialist_bucket not in VALID_SPECIALIST_BUCKETS:
        logger.warning(
            f"Invalid specialist_bucket '{specialist_bucket}', "
            f"must be one of {sorted(VALID_SPECIALIST_BUCKETS)}"
        )
        return pd.DataFrame(
            columns=["trade_date", "news_article_count", "news_headline_text"]
        ).set_index("trade_date")

    conn = get_connection()

    # Dynamically find all tables with specialist_tags
    tables_query = """
    SELECT DISTINCT table_schema || '.' || table_name as full_name
    FROM information_schema.columns
    WHERE column_name = 'specialist_tags'
      AND table_schema IN ('alt', 'econ', 'features')
      AND table_name NOT IN ('news_1d')  -- Skip deprecated table
    """
    tables_df = pd.read_sql(tables_query, conn)

    all_news = []

    for full_name in tables_df["full_name"]:
        try:
            # Validate schema.table from DB against allowlist
            schema, table = full_name.split(".")
            if schema not in _ALLOWED_NEWS_SCHEMAS:
                logger.warning(f"Skipping table in disallowed schema: {full_name}")
                continue

            # Use parameterized query for column discovery
            cols_query = """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
              AND column_name IN ('event_date', 'published_at', 'headline',
                                  'content', 'summary')
            """
            cols_df = pd.read_sql(cols_query, conn, params=[schema, table])
            available = set(cols_df["column_name"])

            # Determine date column (allowlisted values only)
            date_col = "event_date" if "event_date" in available else "published_at"
            if date_col not in available:
                continue

            # Build query with allowlisted column names and parameterized bucket
            _ALLOWED_COLS = {"event_date", "published_at", "headline", "summary"}
            select_parts = [f"{date_col} as trade_date"]
            for col in ("headline", "summary"):
                if col in available and col in _ALLOWED_COLS:
                    select_parts.append(col)

            # table name comes from information_schema (trusted) + schema allowlist
            query = f"""
            SELECT {", ".join(select_parts)}
            FROM {full_name}
            WHERE %s = ANY(specialist_tags)
            """

            df = pd.read_sql(query, conn, params=[specialist_bucket])
            if not df.empty:
                df["trade_date"] = pd.to_datetime(df["trade_date"])
                df["source_table"] = full_name
                all_news.append(df)

        except Exception as e:
            logger.warning(f"Could not load from {full_name}: {e}")
            continue

    conn.close()

    if not all_news:
        # Return empty structure
        return pd.DataFrame(
            columns=[
                "trade_date",
                "news_article_count",
                "news_headline_text",
            ]
        ).set_index("trade_date")

    # Combine all sources
    combined = pd.concat(all_news, ignore_index=True)

    # Apply date filters
    if start_date:
        combined = combined[combined["trade_date"] >= pd.Timestamp(start_date)]
    if end_date:
        combined = combined[combined["trade_date"] <= pd.Timestamp(end_date)]

    # Aggregate by date
    agg_dict = {}
    if "headline" in combined.columns:
        agg_dict["headline"] = lambda x: " | ".join(
            [str(h) for h in x if pd.notna(h)][:10]
        )
    if "summary" in combined.columns:
        agg_dict["summary"] = lambda x: " | ".join(
            [str(s) for s in x if pd.notna(s)][:5]
        )
    result = combined.groupby("trade_date").agg(agg_dict)
    result["news_article_count"] = combined.groupby("trade_date").size()

    # Rename
    rename_map = {}
    if "headline" in result.columns:
        rename_map["headline"] = "news_headline_text"
    if "summary" in result.columns:
        rename_map["summary"] = "news_summary_text"

    result = result.rename(columns=rename_map)

    logger.info(
        f"  News for {specialist_bucket}: {len(result)} days, "
        f"{result['news_article_count'].sum():.0f} articles"
    )

    return result


def ffill_with_real_mask(
    series: pd.Series, limit: int | None = None
) -> tuple[pd.Series, pd.Series]:
    """
    Forward-fill with real observation mask tracking.

    Args:
        series: Time series to forward-fill
        limit: Maximum number of consecutive NaN values to fill

    Returns:
        Tuple of (filled_series, is_real_mask)
        - filled_series: Forward-filled series
        - is_real_mask: Boolean Series (True where raw had data, False where filled)
    """
    # Create mask: True where original data exists, False where NaN
    is_real = series.notna().copy()

    # Apply forward-fill
    filled = series.ffill(limit=limit) if limit is not None else series.ffill()

    # is_real mask remains unchanged (True = real, False = filled/NaN)
    return filled, is_real


def get_connection():
    """Get database connection from standardized URL resolution."""
    return get_write_connection()
