"""
ZINC-FUSION-V15 Pulse Retrieval Layer
======================================

External data source retrieval with caching, rate limiting, and backoff.
AI is resourceful - it finds its own data.

Hierarchy:
1. API with key (preferred - structured data)
2. Scrape HTML/PDF (fallback - unstructured)
3. Web search (last resort - discovery)
"""

import os
import json
import hashlib
import time
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum

import httpx

logger = logging.getLogger(__name__)


class SourceStatus(Enum):
    SUCCESS = "success"
    CACHED = "cached"
    PARTIAL = "partial"
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"


@dataclass
class RetrievalResult:
    """Result from a source retrieval attempt."""
    source: str
    status: SourceStatus
    data: Optional[Dict[str, Any]] = None
    cached_at: Optional[datetime] = None
    fetched_at: Optional[datetime] = None
    error: Optional[str] = None
    latency_ms: float = 0.0


@dataclass
class SourceConfig:
    """Configuration for a data source."""
    name: str
    base_url: str
    method: str  # api_get, api_post, scrape_html, scrape_pdf, download_csv
    api_key_env: Optional[str] = None
    calls_per_min: int = 60
    cache_ttl_hours: float = 24.0
    backoff_base: float = 1.0
    priority: str = "P1"
    params: Dict[str, Any] = field(default_factory=dict)


# Source configurations
SOURCE_CONFIG: Dict[str, SourceConfig] = {
    'fred': SourceConfig(
        name='fred',
        base_url='https://api.stlouisfed.org/fred/series/observations',
        method='api_get',
        api_key_env='FRED_API_KEY',
        calls_per_min=120,
        cache_ttl_hours=24.0,
        backoff_base=1.0,
        priority='P0'
    ),
    'eia': SourceConfig(
        name='eia',
        base_url='https://api.eia.gov/v2/',
        method='api_get',
        api_key_env='EIA_API_KEY',
        calls_per_min=100,
        cache_ttl_hours=24.0,
        backoff_base=1.0,
        priority='P0'
    ),
    'noaa': SourceConfig(
        name='noaa',
        base_url='https://www.ncdc.noaa.gov/cdo-web/api/v2/',
        method='api_get',
        api_key_env='NOAA_API_TOKEN',
        calls_per_min=5,
        cache_ttl_hours=6.0,
        backoff_base=2.0,
        priority='P1'
    ),
    'cboe_vix': SourceConfig(
        name='cboe_vix',
        base_url='http://www.cboe.com/publish/ScheduledTask/MktData/datahouse/vixcurrent.csv',
        method='download_csv',
        calls_per_min=10,
        cache_ttl_hours=1.0,
        backoff_base=1.0,
        priority='P0'
    ),
    'federal_register': SourceConfig(
        name='federal_register',
        base_url='https://www.federalregister.gov/api/v1/documents.json',
        method='api_get',
        calls_per_min=30,
        cache_ttl_hours=4.0,
        backoff_base=1.0,
        priority='P0'
    ),
    'nyfed_rates': SourceConfig(
        name='nyfed_rates',
        base_url='https://markets.newyorkfed.org/api/rates/all/latest.json',
        method='api_get',
        calls_per_min=60,
        cache_ttl_hours=1.0,
        backoff_base=1.0,
        priority='P0'
    ),
    'treasury_fiscal': SourceConfig(
        name='treasury_fiscal',
        base_url='https://api.fiscaldata.treasury.gov/services/api/v1/',
        method='api_get',
        calls_per_min=60,
        cache_ttl_hours=24.0,
        backoff_base=1.0,
        priority='P1'
    )
}

# Domain to priority sources mapping
DOMAIN_PRIORITY_SOURCES: Dict[str, List[str]] = {
    "CRUSH": ["usda_nass", "usda_wasde", "usda_fas", "conab", "abiove", "nopa"],
    "CHINA": ["gacc_customs", "mofcom", "cngoic", "tradingeconomics_china"],
    "FX": ["fred_fx", "ecb_sdw", "usda_ers_fx"],
    "FED": ["fred_rates", "nyfed_rates", "treasury_fiscal", "fed_speeches"],
    "TARIFF": ["federal_register", "ustr", "usitc"],
    "ENERGY": ["eia", "fred_energy", "tradingeconomics_energy"],
    "BIOFUEL": ["epa_rin", "epa_rfs", "eia_biofuels"],
    "PALM": ["mpob", "bursa_malaysia", "tradingeconomics_palm"],
    "VOLATILITY": ["cboe_vix", "fred_volatility", "yahoo_vix"],
    "SUBSTITUTES": ["tradingeconomics_oils", "usda_oilseeds"],
    "TRUMP_EFFECT": ["whitehouse", "truth_social", "federal_register_eo", "prediction_markets"]
}

# FRED series by domain
FRED_SERIES: Dict[str, List[str]] = {
    "FX": [
        "DEXBZUS", "DEXCHUS", "DEXARUS", "DEXMXUS", "DEXUSEU",
        "DEXUSUK", "DEXJPUS", "DEXCAUS", "DTWEXBGS", "DTWEXAFEGS", "DTWEXEMEGS"
    ],
    "FED": [
        "DFF", "FEDFUNDS", "DFEDTARU",
        "DGS1MO", "DGS3MO", "DGS6MO", "DGS1", "DGS2", "DGS5", "DGS7", "DGS10", "DGS20", "DGS30",
        "MORTGAGE30US", "T10Y2Y", "T10Y3M", "TEDRATE",
        "PAYEMS", "UNRATE", "CIVPART",
        "CPIAUCSL", "CPILFESL", "PCEPI", "PCEPILFE", "GDP",
        "AMBSL", "M1SL", "M2SL"
    ],
    "ENERGY": ["DCOILWTICO", "DCOILBRENTEU", "DHHNGSP", "GASDESW"],
    "VOLATILITY": ["VIXCLS", "STLFSI4", "NFCI", "KCFSI", "BAMLH0A0HYM2", "BAMLEMNADE", "BAMLC0A0CM"]
}


class RetrievalCache:
    """Simple file-based cache for retrieved data."""

    def __init__(self, cache_dir: Optional[str] = None):
        if cache_dir is None:
            cache_dir = Path.home() / '.zinc_fusion_cache'
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_key(self, source: str, params: Dict[str, Any]) -> str:
        """Generate cache key from source and params."""
        param_str = json.dumps(params, sort_keys=True)
        hash_input = f"{source}:{param_str}"
        return hashlib.md5(hash_input.encode()).hexdigest()

    def get(self, source: str, params: Dict[str, Any], ttl_hours: float) -> Optional[Dict[str, Any]]:
        """Get cached data if still valid."""
        key = self._cache_key(source, params)
        cache_file = self.cache_dir / f"{key}.json"

        if not cache_file.exists():
            return None

        try:
            with open(cache_file, 'r') as f:
                cached = json.load(f)

            cached_at = datetime.fromisoformat(cached['cached_at'])
            if datetime.utcnow() - cached_at > timedelta(hours=ttl_hours):
                return None

            return cached['data']
        except Exception as e:
            logger.warning(f"Cache read error for {source}: {e}")
            return None

    def set(self, source: str, params: Dict[str, Any], data: Dict[str, Any]):
        """Store data in cache."""
        key = self._cache_key(source, params)
        cache_file = self.cache_dir / f"{key}.json"

        try:
            with open(cache_file, 'w') as f:
                json.dump({
                    'cached_at': datetime.utcnow().isoformat(),
                    'source': source,
                    'params': params,
                    'data': data
                }, f)
        except Exception as e:
            logger.warning(f"Cache write error for {source}: {e}")

    def invalidate(self, pattern: str = "*"):
        """Invalidate cached entries matching pattern."""
        for cache_file in self.cache_dir.glob(f"{pattern}.json"):
            try:
                cache_file.unlink()
            except Exception as e:
                logger.warning(f"Cache invalidate error: {e}")


class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self):
        self.buckets: Dict[str, Dict[str, Any]] = {}

    def can_proceed(self, source: str, calls_per_min: int) -> bool:
        """Check if we can make another call."""
        now = time.time()

        if source not in self.buckets:
            self.buckets[source] = {
                'tokens': calls_per_min,
                'last_refill': now
            }

        bucket = self.buckets[source]

        # Refill tokens based on time elapsed
        elapsed = now - bucket['last_refill']
        refill = int(elapsed * calls_per_min / 60)
        if refill > 0:
            bucket['tokens'] = min(calls_per_min, bucket['tokens'] + refill)
            bucket['last_refill'] = now

        if bucket['tokens'] > 0:
            bucket['tokens'] -= 1
            return True

        return False

    def wait_time(self, source: str, calls_per_min: int) -> float:
        """Get wait time in seconds until next available token."""
        if source not in self.buckets:
            return 0.0

        bucket = self.buckets[source]
        if bucket['tokens'] > 0:
            return 0.0

        return 60.0 / calls_per_min


class RetryBackoff:
    """Exponential backoff with jitter."""

    def __init__(self, base: float = 1.0, max_delay: float = 60.0, jitter: float = 0.1):
        self.base = base
        self.max_delay = max_delay
        self.jitter = jitter
        self.attempts: Dict[str, int] = {}

    def get_delay(self, source: str) -> float:
        """Get delay for next retry."""
        attempts = self.attempts.get(source, 0)
        delay = min(self.base * (2 ** attempts), self.max_delay)

        # Add jitter
        import random
        jitter_range = delay * self.jitter
        delay += random.uniform(-jitter_range, jitter_range)

        return max(0, delay)

    def record_failure(self, source: str):
        """Record a failed attempt."""
        self.attempts[source] = self.attempts.get(source, 0) + 1

    def record_success(self, source: str):
        """Reset attempts on success."""
        self.attempts[source] = 0


class RetrievalLayer:
    """
    Main retrieval orchestrator.

    Handles fetching data from all configured sources with:
    - Caching
    - Rate limiting
    - Retry with backoff
    - Error handling
    """

    def __init__(self, cache_dir: Optional[str] = None):
        self.cache = RetrievalCache(cache_dir)
        self.rate_limiter = RateLimiter()
        self.backoff = RetryBackoff()
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    def _get_api_key(self, env_var: Optional[str]) -> Optional[str]:
        """Get API key from environment."""
        if env_var is None:
            return None
        return os.environ.get(env_var)

    async def _fetch_fred(self, series_id: str, api_key: str) -> Dict[str, Any]:
        """Fetch a FRED series."""
        params = {
            'series_id': series_id,
            'api_key': api_key,
            'file_type': 'json',
            'sort_order': 'desc',
            'limit': 100
        }

        response = await self.client.get(
            'https://api.stlouisfed.org/fred/series/observations',
            params=params
        )
        response.raise_for_status()
        data = response.json()

        # Extract observations
        observations = data.get('observations', [])
        return {
            'series_id': series_id,
            'values': [
                {
                    'date': obs.get('date'),
                    'value': float(obs.get('value')) if obs.get('value') != '.' else None
                }
                for obs in observations
                if obs.get('value') != '.'
            ][:50]  # Last 50 observations
        }

    async def _fetch_eia(self, endpoint: str, api_key: str) -> Dict[str, Any]:
        """Fetch EIA data."""
        url = f"https://api.eia.gov/v2/{endpoint}"
        params = {'api_key': api_key}

        response = await self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    async def _fetch_vix_csv(self) -> Dict[str, Any]:
        """Download VIX CSV from CBOE."""
        response = await self.client.get(
            'http://www.cboe.com/publish/ScheduledTask/MktData/datahouse/vixcurrent.csv'
        )
        response.raise_for_status()

        lines = response.text.strip().split('\n')
        # Parse CSV (skip header rows)
        data = []
        for line in lines[2:]:  # Skip first 2 header rows
            parts = line.split(',')
            if len(parts) >= 5:
                try:
                    data.append({
                        'date': parts[0].strip(),
                        'open': float(parts[1]),
                        'high': float(parts[2]),
                        'low': float(parts[3]),
                        'close': float(parts[4])
                    })
                except (ValueError, IndexError):
                    continue

        return {'vix_data': data[-50:]}  # Last 50 days

    async def _fetch_federal_register(self, search_term: str = 'tariff') -> Dict[str, Any]:
        """Fetch from Federal Register API."""
        params = {
            'conditions[term]': search_term,
            'conditions[type][]': 'PRESDOCU',
            'per_page': 20,
            'order': 'newest'
        }

        response = await self.client.get(
            'https://www.federalregister.gov/api/v1/documents.json',
            params=params
        )
        response.raise_for_status()
        data = response.json()

        return {
            'documents': [
                {
                    'title': doc.get('title'),
                    'publication_date': doc.get('publication_date'),
                    'document_number': doc.get('document_number'),
                    'type': doc.get('type'),
                    'abstract': doc.get('abstract', '')[:500]
                }
                for doc in data.get('results', [])
            ]
        }

    async def _fetch_nyfed_rates(self) -> Dict[str, Any]:
        """Fetch NY Fed reference rates."""
        response = await self.client.get(
            'https://markets.newyorkfed.org/api/rates/all/latest.json'
        )
        response.raise_for_status()
        return response.json()

    async def fetch_source(
        self,
        source: str,
        params: Optional[Dict[str, Any]] = None,
        force_refresh: bool = False
    ) -> RetrievalResult:
        """
        Fetch data from a single source.

        Args:
            source: Source name (e.g., 'fred', 'eia')
            params: Additional parameters for the request
            force_refresh: Skip cache if True

        Returns:
            RetrievalResult with data or error
        """
        params = params or {}
        start_time = time.time()

        config = SOURCE_CONFIG.get(source)
        if config is None:
            return RetrievalResult(
                source=source,
                status=SourceStatus.FAILED,
                error=f"Unknown source: {source}"
            )

        # Check cache first
        if not force_refresh:
            cached = self.cache.get(source, params, config.cache_ttl_hours)
            if cached:
                return RetrievalResult(
                    source=source,
                    status=SourceStatus.CACHED,
                    data=cached,
                    cached_at=datetime.utcnow(),
                    latency_ms=0.0
                )

        # Check rate limit
        if not self.rate_limiter.can_proceed(source, config.calls_per_min):
            wait = self.rate_limiter.wait_time(source, config.calls_per_min)
            return RetrievalResult(
                source=source,
                status=SourceStatus.RATE_LIMITED,
                error=f"Rate limited, wait {wait:.1f}s"
            )

        # Get API key if needed
        api_key = self._get_api_key(config.api_key_env)
        if config.api_key_env and not api_key:
            return RetrievalResult(
                source=source,
                status=SourceStatus.FAILED,
                error=f"Missing API key: {config.api_key_env}"
            )

        try:
            # Fetch based on source type
            if source == 'fred':
                series_id = params.get('series_id', 'DGS10')
                data = await self._fetch_fred(series_id, api_key)
            elif source == 'eia':
                endpoint = params.get('endpoint', 'petroleum/pri/spt/data/')
                data = await self._fetch_eia(endpoint, api_key)
            elif source == 'cboe_vix':
                data = await self._fetch_vix_csv()
            elif source == 'federal_register':
                search_term = params.get('search_term', 'tariff')
                data = await self._fetch_federal_register(search_term)
            elif source == 'nyfed_rates':
                data = await self._fetch_nyfed_rates()
            else:
                return RetrievalResult(
                    source=source,
                    status=SourceStatus.FAILED,
                    error=f"Fetch not implemented for: {source}"
                )

            # Cache the result
            self.cache.set(source, params, data)
            self.backoff.record_success(source)

            latency = (time.time() - start_time) * 1000

            return RetrievalResult(
                source=source,
                status=SourceStatus.SUCCESS,
                data=data,
                fetched_at=datetime.utcnow(),
                latency_ms=latency
            )

        except httpx.HTTPStatusError as e:
            self.backoff.record_failure(source)
            return RetrievalResult(
                source=source,
                status=SourceStatus.FAILED,
                error=f"HTTP {e.response.status_code}: {str(e)}"
            )
        except Exception as e:
            self.backoff.record_failure(source)
            return RetrievalResult(
                source=source,
                status=SourceStatus.FAILED,
                error=str(e)
            )

    async def fetch_fred_series(
        self,
        series_ids: List[str],
        force_refresh: bool = False
    ) -> Dict[str, RetrievalResult]:
        """Fetch multiple FRED series in parallel."""
        tasks = [
            self.fetch_source('fred', {'series_id': sid}, force_refresh)
            for sid in series_ids
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return {
            series_ids[i]: (
                results[i] if isinstance(results[i], RetrievalResult)
                else RetrievalResult(
                    source='fred',
                    status=SourceStatus.FAILED,
                    error=str(results[i])
                )
            )
            for i in range(len(series_ids))
        }

    async def fetch_domain_sources(
        self,
        domain: str,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Fetch all priority sources for a specialist domain.

        Args:
            domain: Specialist domain (CRUSH, CHINA, etc.)
            force_refresh: Skip cache if True

        Returns:
            Dictionary with:
                - sources: Dict[source_name, data]
                - missing_sources: List of sources that failed
                - errors: List of error details
        """
        result = {
            'domain': domain,
            'fetched_at': datetime.utcnow().isoformat(),
            'sources': {},
            'missing_sources': [],
            'errors': []
        }

        # Get priority sources for this domain
        priority_sources = DOMAIN_PRIORITY_SOURCES.get(domain, [])

        # Fetch FRED series for this domain
        fred_series = FRED_SERIES.get(domain, [])
        if fred_series:
            fred_results = await self.fetch_fred_series(fred_series, force_refresh)
            for series_id, fetch_result in fred_results.items():
                if fetch_result.status in (SourceStatus.SUCCESS, SourceStatus.CACHED):
                    result['sources'][f'fred_{series_id}'] = fetch_result.data
                else:
                    result['missing_sources'].append(f'fred_{series_id}')
                    result['errors'].append({
                        'source': f'fred_{series_id}',
                        'error': fetch_result.error
                    })

        # Fetch other sources
        for source in priority_sources:
            if source in SOURCE_CONFIG:
                fetch_result = await self.fetch_source(source, force_refresh=force_refresh)
                if fetch_result.status in (SourceStatus.SUCCESS, SourceStatus.CACHED):
                    result['sources'][source] = fetch_result.data
                else:
                    result['missing_sources'].append(source)
                    result['errors'].append({
                        'source': source,
                        'error': fetch_result.error
                    })
            else:
                result['missing_sources'].append(source)
                logger.warning(f"Missing priority source implementation: {source}")

        return result


# Convenience function for synchronous usage
def fetch_domain_sync(domain: str, force_refresh: bool = False) -> Dict[str, Any]:
    """Synchronous wrapper for fetch_domain_sources."""
    async def _fetch():
        layer = RetrievalLayer()
        try:
            return await layer.fetch_domain_sources(domain, force_refresh)
        finally:
            await layer.close()

    return asyncio.run(_fetch())
