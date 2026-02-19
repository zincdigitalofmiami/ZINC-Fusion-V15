"""Sentiment, strategy, and driver API routes."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Query

from fusion.api.news_sentiment import analyze_articles, get_policy_sentiment

from .common import _fetch_recent_news_rows, _fetch_rows, _to_datetime

router = APIRouter()


@router.get("/api/sentiment/news")
def sentiment_news(
    limit: int = Query(200, ge=1, le=2000),
) -> dict[str, Any]:
    articles = _fetch_recent_news_rows(limit)

    mapped = [
        {
            "id": row.get("article_id"),
            "title": row.get("title"),
            "body": row.get("content"),
            "source": row.get("source"),
            "published_at": row.get("published_at"),
        }
        for row in articles
    ]

    return analyze_articles(mapped)


@router.get("/api/sentiment/series")
def sentiment_series(limit: int = Query(365, ge=1, le=5000)) -> dict[str, Any]:
    scan_limit = min(max(limit * 25, 500), 5000)
    articles = _fetch_recent_news_rows(scan_limit)
    analyzed = analyze_articles(
        [
            {
                "id": row.get("article_id"),
                "title": row.get("title"),
                "body": row.get("content"),
                "source": row.get("source"),
                "published_at": row.get("published_at"),
            }
            for row in articles
        ]
    ).get("articles", [])

    by_day: dict[date, dict[str, Any]] = {}
    for article in analyzed:
        published_at = article.get("published_at")
        ts = _to_datetime(published_at)
        day = ts.date() if ts != datetime.min else None
        score = article.get("impact_score")
        if day is None or score is None:
            continue
        if day not in by_day:
            by_day[day] = {"sum": 0.0, "count": 0}
        by_day[day]["sum"] += float(score)
        by_day[day]["count"] += 1

    rows = [
        {
            "as_of_date": as_of_date,
            "sentiment_score": agg["sum"] / agg["count"] if agg["count"] else None,
            "article_count": agg["count"],
        }
        for as_of_date, agg in by_day.items()
    ]
    rows.sort(key=lambda row: row["as_of_date"])
    rows = rows[-limit:]

    series = [
        {
            "time": row["as_of_date"],
            "value": row["sentiment_score"],
            "article_count": row["article_count"],
        }
        for row in rows
        if row.get("sentiment_score") is not None
    ]
    return {"series": series}


@router.get("/api/legislation/news")
def legislation_news(limit: int = Query(200, ge=1, le=2000)) -> dict[str, Any]:
    analyzed = sentiment_news(limit=limit)
    keep = {
        "US Regulatory Filings",
        "Legislation Changes",
        "Biofuel Mandates",
        "Tariff Updates",
    }
    articles = []
    for article in analyzed.get("articles", []):
        buckets = set(article.get("alert_buckets") or [])
        if buckets & keep:
            articles.append(article)

    summary = analyzed.get("summary") or {}
    summary["filtered_alert_buckets"] = sorted(keep)
    summary["filtered_articles"] = len(articles)
    return {"articles": articles, "summary": summary}


@router.get("/api/strategy/posture")
def strategy_posture(symbol: str = "ZL") -> dict[str, Any]:
    actions = _fetch_rows(
        """
        SELECT as_of_date, action, confidence, rationale
        FROM analytics.procurement_actions
        WHERE symbol = ?
        ORDER BY as_of_date DESC
        LIMIT 30
        """,
        [symbol],
    )
    latest_action = actions[0] if actions else None

    windows = _fetch_rows(
        """
        SELECT as_of_date, horizon_days, tail_proximity, probability_lift, confidence_adjusted_lift,
               regime_dampening, window_start_week, window_end_week
        FROM analytics.value_timing_windows
        WHERE symbol = ?
        ORDER BY as_of_date DESC, horizon_days ASC
        LIMIT 200
        """,
        [symbol],
    )

    return {
        "symbol": symbol,
        "latest_action": latest_action,
        "recent_actions": actions,
        "value_windows": windows,
    }


@router.get("/api/strategy/risk")
def strategy_risk(symbol: str = "ZL", horizon: str | None = None) -> dict[str, Any]:
    # Schema: no symbol column; columns are var_01/var_05/var_10/cvar_05
    rows = _fetch_rows(
        """
        SELECT as_of_date, horizon, var_01, var_05, var_10, cvar_05,
               prob_up, prob_up_5pct, prob_down_5pct, regime, tail_risk_flag
        FROM analytics.risk_metrics
        ORDER BY as_of_date DESC
        LIMIT 1000
        """
    )
    if horizon:
        rows = [row for row in rows if str(row.get("horizon")) == horizon]
    return {"symbol": symbol, "risk_metrics": rows}


@router.get("/api/vegas-intel/status")
def vegas_intel_status() -> dict[str, Any]:
    return {
        "status": "not_implemented",
        "reason": "Vegas-intel tables not available.",
    }


@router.get("/api/sentiment/policy")
def sentiment_policy(limit: int = Query(90, ge=1, le=2000)) -> dict[str, Any]:
    return {"rows": get_policy_sentiment(limit=limit)}


@router.get("/api/drivers/latest")
def drivers_latest(symbol: str = "ZL") -> dict[str, Any]:
    # Schema: no symbol/bucket/score/weight; actual columns are specialist/signal/direction/confidence/shap_contribution
    rows = _fetch_rows(
        """
        WITH latest AS (
            SELECT MAX(as_of_date) AS as_of_date
            FROM analytics.driver_scores
        )
        SELECT
            s.as_of_date,
            s.specialist,
            s.signal,
            s.direction,
            s.confidence,
            s.shap_contribution
        FROM analytics.driver_scores s
        JOIN latest l ON s.as_of_date = l.as_of_date
        ORDER BY s.specialist
        """
    )
    as_of_date = rows[0]["as_of_date"] if rows else None
    return {"symbol": symbol, "as_of_date": as_of_date, "signals": rows}


@router.get("/api/drivers/series")
def drivers_series(
    symbol: str = "ZL",
    driver_id: str = Query(..., min_length=1),
    limit: int = Query(2000, ge=1, le=10000),
) -> dict[str, Any]:
    # Schema: no symbol/bucket/score; use specialist/signal
    rows = _fetch_rows(
        """
        SELECT as_of_date, signal AS score
        FROM (
            SELECT as_of_date, signal
            FROM analytics.driver_scores
            WHERE specialist = ?
            ORDER BY as_of_date DESC
            LIMIT ?
        ) t
        ORDER BY as_of_date ASC
        """,
        [driver_id, limit],
    )
    series = [
        {"time": row["as_of_date"], "value": row["score"]}
        for row in rows
        if row.get("score") is not None
    ]
    return {"symbol": symbol, "driver_id": driver_id, "series": series}
