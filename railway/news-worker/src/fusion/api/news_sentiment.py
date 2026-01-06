"""Rule-based news sentiment analysis for soybean oil context."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List

from fusion.api.db import fetch_rows


ALERT_BUCKETS = [
    "US Regulatory Filings",
    "Political Changes",
    "Tariff Updates",
    "China Relations",
    "Legislation Changes",
    "Biofuel Mandates",
    "Logistics/Chokepoints",
    "ESG/Deforestation",
    "Labor Actions",
    "Fertilizer/Energy",
    "Animal Disease",
]

INSTITUTION_HINTS = [
    "ustr",
    "usda fas",
    "usda ers",
    "epa",
    "eu commission",
    "dg trade",
    "wto",
    "mapa",
    "conab",
    "ibama",
    "argentina economia",
    "afip",
    "moa china",
    "ndrc",
    "sinograin",
    "cofco",
    "mpob",
    "indonesian coordinating ministry of economic affairs",
    "renovabio",
    "anp",
]

SPECIFICITY_HIGH = [
    "decree",
    "approved",
    "enacted",
    "law",
    "ban",
    "rule published",
]

SPECIFICITY_LOW = [
    "proposal",
    "draft",
    "discussion",
]

RAW_CATEGORIES: List[Dict[str, Any]] = [
    {
        "id": "china_demand_levers",
        "name": "China demand levers",
        "alert_bucket": "China Relations",
        "half_life": "medium",
        "bullish": [
            "reserve stockpiles rebuild",
            "import quota boost",
            "crush margin subsidies",
            "crush-margin subsidies",
        ],
        "bearish": [
            "biosecurity import slowdowns",
            "tighter import licenses",
            "state reserve releases",
        ],
        "keywords": [
            "sinograin",
            "cofco",
            "ndrc soybean",
            "state reserves",
            "crush margins",
            "dalian",
        ],
    },
    {
        "id": "argentina_policy_fx",
        "name": "Argentina policy + FX",
        "alert_bucket": "Political Changes",
        "half_life": "medium",
        "bullish": [
            "export taxes up",
            "soy dollar ends",
            "port blockades",
            "trucker strikes",
        ],
        "bearish": [
            "temporary export tax cuts",
            "fx incentives to sell",
            "imf-driven liberalization",
        ],
        "keywords": [
            "sojadolar",
            "retenciones",
            "rosario strike",
            "ciara-cec",
            "puerto san lorenzo",
        ],
    },
    {
        "id": "brazil_policy_infra",
        "name": "Brazil policy + infrastructure",
        "alert_bucket": "Logistics/Chokepoints",
        "half_life": "medium",
        "bullish": [
            "export licensing hiccups",
            "environmental enforcement slowing amazon expansion",
            "barge bottlenecks",
            "rail bottlenecks",
        ],
        "bearish": [
            "logistics upgrades",
            "ferrograo",
            "port privatizations",
            "brl strengthening",
        ],
        "keywords": [
            "conab",
            "mapa",
            "santos",
            "arco norte",
            "ferrograo",
            "ibama embargo",
            "br-163",
            "usd/brl",
        ],
    },
    {
        "id": "us_policy",
        "name": "US policy",
        "alert_bucket": "US Regulatory Filings",
        "half_life": "long",
        "bullish": [
            "higher china tariffs",
            "retaliation risk",
            "tougher eudr alignment costs",
            "rail strikes",
            "port strikes",
            "mississippi draft limits",
        ],
        "bearish": [
            "export credit guarantees expanded",
            "grain inspection streamlining",
            "lower rfs volumes",
        ],
        "keywords": [
            "ustr",
            "rfs volumes",
            "jones act waiver",
            "usace mississippi",
            "ilwu",
            "stb rail",
        ],
    },
    {
        "id": "biofuels_policy",
        "name": "Biofuels policy swings",
        "alert_bucket": "Biofuel Mandates",
        "half_life": "medium",
        "bullish": [
            "b35",
            "b40",
            "biodiesel blend hikes",
            "lcfs",
            "saf",
            "45z",
        ],
        "bearish": [
            "iluc",
            "weaker lcfs credit prices",
            "cap on crop-based biofuels",
        ],
        "keywords": [
            "b40 indonesia",
            "renovabio",
            "cbio",
            "lcfs",
            "saf",
            "epa rvo",
        ],
    },
    {
        "id": "palm_oil_geopolitics",
        "name": "Palm oil geopolitics",
        "alert_bucket": "Tariff Updates",
        "half_life": "medium",
        "bullish": [
            "export levies",
            "export bans",
            "labor shortages",
            "esg import hurdles",
        ],
        "bearish": [
            "levy cuts",
            "export liberalization",
            "bumper output",
            "india import duty cuts",
        ],
        "keywords": [
            "cpo export levy",
            "dmo",
            "mpob",
            "india edible oil duty",
        ],
    },
    {
        "id": "black_sea_vegoils",
        "name": "Black Sea vegoils and war spillovers",
        "alert_bucket": "Logistics/Chokepoints",
        "half_life": "short",
        "bullish": [
            "corridor disruptions",
            "port strikes",
            "sanctions on russian",
            "belarus agrichemicals",
        ],
        "bearish": [
            "corridor re-openings",
            "insured shipping expands",
            "sunflower oil floods market",
        ],
        "keywords": [
            "black sea corridor",
            "danube ports",
            "sunflower oil export",
            "marine insurance",
        ],
    },
    {
        "id": "global_chokepoints_freight",
        "name": "Global chokepoints and freight",
        "alert_bucket": "Logistics/Chokepoints",
        "half_life": "short",
        "bullish": [
            "red sea",
            "suez risk",
            "panama canal draft cuts",
            "south china sea tension",
            "war risk premiums",
        ],
        "bearish": [
            "reroute subsidies",
            "canal rainfall recovery",
            "naval escorts restore throughput",
        ],
        "keywords": [
            "panama canal transit",
            "bab el-mandeb",
            "houthi",
            "war risk premiums",
        ],
    },
    {
        "id": "fertilizer_energy_sanctions",
        "name": "Fertilizer and energy sanctions",
        "alert_bucket": "Fertilizer/Energy",
        "half_life": "medium",
        "bullish": [
            "sanctions",
            "plant outages",
            "potash restrictions",
            "natgas spikes",
        ],
        "bearish": [
            "sanction carve-outs",
            "new supply",
            "cheap gas",
        ],
        "keywords": [
            "belarus potash",
            "cf industries outage",
            "ammonia pipeline",
            "urea tender",
        ],
    },
    {
        "id": "animal_disease_shocks",
        "name": "Animal disease shocks",
        "alert_bucket": "Animal Disease",
        "half_life": "short",
        "bullish": [
            "herd rebuild",
            "hog herd rebuild",
        ],
        "bearish": [
            "asf china",
            "avian influenza",
            "culling",
        ],
        "keywords": [
            "asf china",
            "avian influenza",
            "hog herd",
            "moa china",
        ],
    },
    {
        "id": "trade_disputes_quotas",
        "name": "Trade disputes and quotas",
        "alert_bucket": "Tariff Updates",
        "half_life": "long",
        "bullish": [
            "antidumping",
            "cvd",
            "quotas",
            "sps barriers",
        ],
        "bearish": [
            "tariff-rate quotas",
            "purchase commitments",
            "bilateral deal",
        ],
        "keywords": [
            "antidumping soybean oil",
            "wto panel",
            "trq soybeans",
            "sps measures",
        ],
    },
    {
        "id": "esg_deforestation_rules",
        "name": "ESG and deforestation rules",
        "alert_bucket": "ESG/Deforestation",
        "half_life": "long",
        "bullish": [
            "strict traceability deadlines",
            "shipment delays",
            "cargo rejections",
        ],
        "bearish": [
            "phased enforcement",
            "exemptions",
        ],
        "keywords": [
            "eudr soy",
            "traceability polygon",
            "due diligence regulation",
        ],
    },
    {
        "id": "labor_civil_unrest",
        "name": "Labor and civil unrest",
        "alert_bucket": "Labor Actions",
        "half_life": "short",
        "bullish": [
            "port strikes",
            "trucker protests",
            "farmer blockades",
            "rosario piquete",
            "gulf export elevators",
            "blockade",
        ],
        "bearish": [
            "strike settlements",
            "throughput guarantees",
        ],
        "keywords": [
            "port strike santos",
            "rosario piquete",
            "gulf export elevators",
            "blockade",
        ],
    },
    {
        "id": "cyber_infrastructure_surprises",
        "name": "Cyber or infrastructure surprises",
        "alert_bucket": "Logistics/Chokepoints",
        "half_life": "short",
        "bullish": [
            "ransomware port",
            "terminal outage",
            "customs it failure",
            "ais spoofing",
        ],
        "bearish": [],
        "keywords": [
            "ransomware port",
            "terminal outage",
            "customs it failure",
            "ais spoofing",
        ],
    },
    {
        "id": "regulatory_approvals",
        "name": "Regulatory approvals of traits and agrochemicals",
        "alert_bucket": "Legislation Changes",
        "half_life": "long",
        "bullish": [
            "glyphosate ban",
            "delayed trait approvals",
            "withdrawals",
        ],
        "bearish": [
            "rapid approvals",
            "alternative herbicide programs stabilized",
        ],
        "keywords": [
            "soy trait approval china",
            "glyphosate ban",
            "ctnbio",
        ],
    },
    {
        "id": "macro_fx",
        "name": "Macro and FX",
        "alert_bucket": "Political Changes",
        "half_life": "short",
        "bullish": [
            "brl strengthen",
            "ars strengthen",
        ],
        "bearish": [
            "usd strengthen",
            "dxy up",
            "brl weaken",
            "ars devalue",
            "capital controls",
            "sovereign downgrade",
        ],
        "keywords": [
            "usd",
            "brl",
            "ars",
            "capital controls",
            "sovereign downgrade",
        ],
    },
]


def _normalize_text(text: str) -> str:
    if not text:
        return ""
    ascii_text = (
        unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    )
    cleaned = re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).strip()
    return f" {cleaned} "


def _compile_terms(terms: List[str]) -> List[Dict[str, str]]:
    compiled: List[Dict[str, str]] = []
    seen = set()
    for term in terms:
        norm = _normalize_text(term).strip()
        if not norm or norm in seen:
            continue
        compiled.append({"raw": term, "norm": norm})
        seen.add(norm)
    return compiled


def _match_terms(text: str, terms: List[Dict[str, str]]) -> List[str]:
    hits: List[str] = []
    for term in terms:
        if f" {term['norm']} " in text:
            hits.append(term["raw"])
    return hits


COMPILED_CATEGORIES: List[Dict[str, Any]] = []
for category in RAW_CATEGORIES:
    compiled = dict(category)
    compiled["keywords"] = _compile_terms(category["keywords"])
    compiled["bullish"] = _compile_terms(category["bullish"])
    compiled["bearish"] = _compile_terms(category["bearish"])
    COMPILED_CATEGORIES.append(compiled)

COMPILED_INSTITUTIONS = _compile_terms(INSTITUTION_HINTS)
COMPILED_SPEC_HIGH = _compile_terms(SPECIFICITY_HIGH)
COMPILED_SPEC_LOW = _compile_terms(SPECIFICITY_LOW)


def _serialize_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def get_rules() -> Dict[str, Any]:
    return {
        "alert_buckets": ALERT_BUCKETS,
        "categories": [
            {
                "id": c["id"],
                "name": c["name"],
                "alert_bucket": c["alert_bucket"],
                "half_life": c["half_life"],
                "keywords": [k["raw"] for k in c["keywords"]],
                "bullish": [k["raw"] for k in c["bullish"]],
                "bearish": [k["raw"] for k in c["bearish"]],
            }
            for c in COMPILED_CATEGORIES
        ],
    }


def _calc_conviction(text: str, hit_count: int) -> float:
    source_bonus = 0.2 if _match_terms(text, COMPILED_INSTITUTIONS) else 0.0
    specificity_bonus = 0.2 if _match_terms(text, COMPILED_SPEC_HIGH) else 0.0
    specificity_penalty = -0.1 if _match_terms(text, COMPILED_SPEC_LOW) else 0.0
    base = 0.3 + 0.1 * min(hit_count, 5) + source_bonus + specificity_bonus
    base += specificity_penalty
    return max(0.1, min(0.95, base))


def _calc_relevance(hit_count: int) -> float:
    return min(1.0, 0.2 * hit_count)


def _calc_cross_asset_boost(text: str) -> float:
    has_oil = " oil " in text
    biofuel_terms = _compile_terms(
        ["biofuel", "biodiesel", "lcfs", "saf", "rvo", "b40", "renovabio", "cbio"]
    )
    has_biofuel = bool(_match_terms(text, biofuel_terms))
    return 0.15 if has_oil and has_biofuel else 0.0


def classify_article(article: Dict[str, Any]) -> Dict[str, Any]:
    text = _normalize_text(
        " ".join(
            [
                str(article.get("title") or ""),
                str(article.get("body") or ""),
                str(article.get("source") or ""),
            ]
        )
    )

    matches = []
    total_score = 0.0
    alert_buckets = set()

    for category in COMPILED_CATEGORIES:
        keyword_hits = _match_terms(text, category["keywords"])
        bullish_hits = _match_terms(text, category["bullish"])
        bearish_hits = _match_terms(text, category["bearish"])
        hit_count = len(keyword_hits) + len(bullish_hits) + len(bearish_hits)
        if hit_count == 0:
            continue

        if bullish_hits and bearish_hits:
            direction = "uncertain"
        elif bullish_hits:
            direction = "bullish"
        elif bearish_hits:
            direction = "bearish"
        else:
            direction = "uncertain"

        relevance = _calc_relevance(hit_count)
        conviction = _calc_conviction(text, hit_count)
        impact = relevance * conviction
        if direction == "bearish":
            impact *= -1
        elif direction == "uncertain":
            impact = 0.0

        cross_asset_boost = _calc_cross_asset_boost(text)
        impact *= 1 + cross_asset_boost

        matches.append(
            {
                "category_id": category["id"],
                "category_name": category["name"],
                "alert_bucket": category["alert_bucket"],
                "half_life": category["half_life"],
                "direction": direction,
                "relevance": round(relevance, 3),
                "conviction": round(conviction, 3),
                "impact_score": round(impact, 4),
                "keyword_hits": keyword_hits,
                "bullish_hits": bullish_hits,
                "bearish_hits": bearish_hits,
                "cross_asset_boost": round(cross_asset_boost, 3),
            }
        )

        total_score += impact
        alert_buckets.add(category["alert_bucket"])

    if total_score > 0.05:
        overall_direction = "bullish"
    elif total_score < -0.05:
        overall_direction = "bearish"
    else:
        overall_direction = "uncertain"

    return {
        "id": article.get("id"),
        "title": article.get("title"),
        "source": article.get("source"),
        "published_at": article.get("published_at"),
        "overall_direction": overall_direction,
        "impact_score": round(total_score, 4),
        "alert_buckets": sorted(alert_buckets),
        "matches": matches,
    }


def analyze_articles(articles: List[Dict[str, Any]]) -> Dict[str, Any]:
    analyzed = [classify_article(article) for article in articles]
    summary = {
        "total_articles": len(analyzed),
        "matched_articles": sum(1 for a in analyzed if a["matches"]),
        "direction_counts": {
            "bullish": sum(1 for a in analyzed if a["overall_direction"] == "bullish"),
            "bearish": sum(1 for a in analyzed if a["overall_direction"] == "bearish"),
            "uncertain": sum(
                1 for a in analyzed if a["overall_direction"] == "uncertain"
            ),
        },
        "bucket_counts": {},
    }

    bucket_counts: Dict[str, int] = {}
    for article in analyzed:
        for bucket in article["alert_buckets"]:
            bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
    summary["bucket_counts"] = bucket_counts

    return {"articles": analyzed, "summary": summary}


def get_policy_sentiment(limit: int = 30) -> List[Dict[str, Any]]:
    """Fetch policy sentiment data from Prisma Postgres."""
    try:
        rows = fetch_rows(
            """
            SELECT
                as_of_date,
                china_news_sentiment,
                tariff_sentiment_7d,
                fed_sentiment_7d,
                biofuel_sentiment_7d,
                overall_sentiment,
                source
            FROM "features"."policy_sentiment_1d"
            ORDER BY as_of_date DESC
            LIMIT %s
            """,
            [limit],
        )
        return [{k: _serialize_value(v) for k, v in row.items()} for row in rows]
    except Exception:
        # Table may not exist yet - return empty
        return []
