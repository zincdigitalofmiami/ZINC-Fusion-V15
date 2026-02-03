"""
Universal News Loader for ALL Specialists.

Automatically loads news/alt data from ANY table with specialist_tags column.
Each specialist gets articles tagged for them across all sources.

Tables with specialist_tags:
- alt.profarmer_news (978 rows)
- alt.econ_news (1131 rows)
- alt.news_1d (1301 rows)
- alt.legislation_1d (1164 rows)
- econ.news_event (1131 rows)
- features.news_sentiment_1d (23 rows)

Rule: If a table has specialist_tags[], and an article has 'crush' in that array,
      then the CRUSH specialist gets that article in its feature matrix.
"""

import pandas as pd
import numpy as np
from typing import Optional, List
from datetime import date
import logging
import os
import psycopg2

logger = logging.getLogger(__name__)


def get_connection():
    """Get database connection."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")
    return psycopg2.connect(database_url)


def load_news_for_specialist(
    specialist_bucket: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> pd.DataFrame:
    """
    Load ALL news articles tagged for this specialist from ALL tables.

    Args:
        specialist_bucket: One of the 11 specialists (crush, china, tariff, etc.)
        start_date: Optional start date filter
        end_date: Optional end date filter

    Returns:
        DataFrame with columns:
            - trade_date: date index
            - article_count: number of articles on that date for this specialist
            - avg_sentiment: average sentiment score (if available)
            - sources: list of source tables
            - headlines: concatenated headlines (for text features)
            - content: concatenated content (for NLP)

    This ensures EVERY specialist gets news data from EVERY source that tags them.
    """
    conn = get_connection()

    # Tables with specialist_tags column (discovered dynamically)
    tables_query = """
    SELECT DISTINCT 
        table_schema || '.' || table_name as full_table_name,
        table_schema,
        table_name
    FROM information_schema.columns
    WHERE column_name = 'specialist_tags'
      AND table_schema IN ('alt', 'econ', 'features')
      AND NOT (table_schema = 'econ' AND table_name = 'news_event')
    ORDER BY table_schema, table_name
    """

    tables_df = pd.read_sql(tables_query, conn)
    all_news = []

    logger.info(
        f"Loading news for {specialist_bucket.upper()} from {len(tables_df)} tables"
    )

    for _, row in tables_df.iterrows():
        schema = row["table_schema"]
        table = row["table_name"]
        full_name = f"{schema}.{table}"

        try:
            # Build query based on available columns
            # Check what columns exist
            cols_query = f"""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = '{schema}' 
              AND table_name = '{table}'
              AND column_name IN ('event_date', 'published_at', 'headline', 'content', 
                                  'sentiment_score', 'summary', 'url', 'source')
            """
            available_cols = pd.read_sql(cols_query, conn)
            col_names = set(available_cols["column_name"].tolist())

            # Determine date column
            date_col = "event_date" if "event_date" in col_names else "published_at"
            if date_col not in col_names:
                logger.warning(f"  Skipping {full_name} - no date column")
                continue

            # Build SELECT clause
            select_parts = [f"{date_col} as trade_date"]
            if "headline" in col_names:
                select_parts.append("headline")
            if "content" in col_names:
                select_parts.append("content")
            if "summary" in col_names:
                select_parts.append("summary")
            if "sentiment_score" in col_names:
                select_parts.append("sentiment_score")
            if "url" in col_names:
                select_parts.append("url")
            if "source" in col_names:
                select_parts.append("source")

            # Add table name as source if no source column
            if "source" not in col_names:
                select_parts.append(f"'{table}' as source")

            select_clause = ", ".join(select_parts)

            # Query for articles tagged for this specialist
            query = f"""
            SELECT {select_clause}
            FROM {full_name}
            WHERE '{specialist_bucket}' = ANY(specialist_tags)
            ORDER BY {date_col}
            """

            df = pd.read_sql(query, conn)

            if not df.empty:
                df["trade_date"] = pd.to_datetime(df["trade_date"])
                df["table_source"] = full_name
                all_news.append(df)
                logger.info(
                    f"  {full_name}: {len(df)} articles for {specialist_bucket}"
                )

        except Exception as e:
            logger.warning(f"  Error loading from {full_name}: {e}")
            continue

    conn.close()

    # Combine all news sources
    if not all_news:
        logger.warning(f"No news found for {specialist_bucket}")
        # Return empty dataframe with expected structure
        result = pd.DataFrame(
            columns=["trade_date", "article_count", "avg_sentiment"]
        )
        result.set_index("trade_date", inplace=True)
        return result

    combined = pd.concat(all_news, ignore_index=True)

    # Apply date filters
    if start_date:
        combined = combined[combined["trade_date"] >= pd.Timestamp(start_date)]
    if end_date:
        combined = combined[combined["trade_date"] <= pd.Timestamp(end_date)]

    # Aggregate by date
    agg_dict = {
        "headline": lambda x: " | ".join(
            [str(h) for h in x if pd.notna(h)]
        ),  # Concatenate headlines
        "table_source": lambda x: list(set(x)),  # Unique sources
    }

    if "sentiment_score" in combined.columns:
        agg_dict["sentiment_score"] = "mean"
    if "content" in combined.columns:
        agg_dict["content"] = lambda x: " ".join(
            [str(c) for c in x if pd.notna(c)][:5]
        )  # First 5 articles' content
    if "summary" in combined.columns:
        agg_dict["summary"] = lambda x: " | ".join(
            [str(s) for s in x if pd.notna(s)][:10]
        )  # First 10 summaries

    result = combined.groupby("trade_date").agg(agg_dict)
    result["article_count"] = combined.groupby("trade_date").size()

    # Rename columns
    rename_map = {
        "headline": "headlines",
        "table_source": "sources",
        "sentiment_score": "avg_sentiment",
    }
    result = result.rename(columns=rename_map)

    logger.info(
        f"Total news for {specialist_bucket}: {len(result)} days, {result.get('article_count', pd.Series()).sum()} articles"
    )

    return result


# For backward compatibility - direct access functions for each specialist
def load_news_crush(
    start_date: Optional[date] = None, end_date: Optional[date] = None
) -> pd.DataFrame:
    return load_news_for_specialist("crush", start_date, end_date)


def load_news_china(
    start_date: Optional[date] = None, end_date: Optional[date] = None
) -> pd.DataFrame:
    return load_news_for_specialist("china", start_date, end_date)


def load_news_tariff(
    start_date: Optional[date] = None, end_date: Optional[date] = None
) -> pd.DataFrame:
    return load_news_for_specialist("tariff", start_date, end_date)


def load_news_trump_effect(
    start_date: Optional[date] = None, end_date: Optional[date] = None
) -> pd.DataFrame:
    return load_news_for_specialist("trump_effect", start_date, end_date)


def load_news_biofuel(
    start_date: Optional[date] = None, end_date: Optional[date] = None
) -> pd.DataFrame:
    return load_news_for_specialist("biofuel", start_date, end_date)


def load_news_palm(
    start_date: Optional[date] = None, end_date: Optional[date] = None
) -> pd.DataFrame:
    return load_news_for_specialist("palm", start_date, end_date)


def load_news_volatility(
    start_date: Optional[date] = None, end_date: Optional[date] = None
) -> pd.DataFrame:
    return load_news_for_specialist("volatility", start_date, end_date)


def load_news_energy(
    start_date: Optional[date] = None, end_date: Optional[date] = None
) -> pd.DataFrame:
    return load_news_for_specialist("energy", start_date, end_date)


def load_news_fx(
    start_date: Optional[date] = None, end_date: Optional[date] = None
) -> pd.DataFrame:
    return load_news_for_specialist("fx", start_date, end_date)


def load_news_fed(
    start_date: Optional[date] = None, end_date: Optional[date] = None
) -> pd.DataFrame:
    return load_news_for_specialist("fed", start_date, end_date)


def load_news_substitutes(
    start_date: Optional[date] = None, end_date: Optional[date] = None
) -> pd.DataFrame:
    return load_news_for_specialist("substitutes", start_date, end_date)
