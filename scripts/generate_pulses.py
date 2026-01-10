#!/usr/bin/env python3
"""
ZINC-FUSION-V15 Pulse Generation Script
=========================================

Daily pulse generation for all 11 specialist domains.
Fetches external data, generates AI pulses, extracts features, stores to DB.

Usage:
    python scripts/generate_pulses.py                    # All domains, all horizons
    python scripts/generate_pulses.py --domain CRUSH     # Single domain
    python scripts/generate_pulses.py --dry-run          # Preview without storing
    python scripts/generate_pulses.py --force-refresh    # Skip cache
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from fusion.pulse import (
    PulseEngine,
    RetrievalLayer,
    DOMAINS,
    HORIZONS,
    extract_all_features,
    compute_quant_payload,
    compute_driver_weights
)
from fusion.pulse.storage import get_connection, insert_intel_drop

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('generate_pulses')


class PulseGenerator:
    """
    Orchestrates daily pulse generation.

    Flow:
    1. Fetch external data for each domain
    2. Build prompts with signal snapshots
    3. Call AI model for each domain
    4. Validate and extract features
    5. Store to database
    """

    def __init__(
        self,
        domains: Optional[List[str]] = None,
        horizons: Optional[List[str]] = None,
        dry_run: bool = False,
        force_refresh: bool = False,
        model: str = 'gpt-4'
    ):
        self.domains = domains or DOMAINS
        self.horizons = horizons or HORIZONS
        self.dry_run = dry_run
        self.force_refresh = force_refresh
        self.model = model

        self.engine = PulseEngine()
        self.retrieval = RetrievalLayer()

        self.stats = {
            'domains_processed': 0,
            'pulses_generated': 0,
            'pulses_stored': 0,
            'errors': []
        }

    async def close(self):
        """Cleanup resources."""
        await self.retrieval.close()

    async def fetch_domain_data(self, domain: str) -> Dict[str, Any]:
        """
        Fetch all external data for a domain.

        Args:
            domain: Specialist domain

        Returns:
            Dictionary with signal_snapshot, event_stream, receipts
        """
        logger.info(f"Fetching data for {domain}...")

        # Fetch from retrieval layer
        result = await self.retrieval.fetch_domain_sources(
            domain=domain,
            force_refresh=self.force_refresh
        )

        # Log any missing sources
        if result['missing_sources']:
            logger.warning(
                f"[{domain}] Missing sources: {', '.join(result['missing_sources'])}"
            )

        # Compute quant payload from fetched data
        quant_payload = compute_quant_payload(result['sources'])

        # Build signal snapshot for prompt
        signal_snapshot = self._build_signal_snapshot(domain, result['sources'])

        # Build event stream (placeholder - would come from news sources)
        event_stream = self._build_event_stream(domain, result['sources'])

        # Receipt IDs for evidence
        receipt_ids = list(result['sources'].keys())

        return {
            'signal_snapshot': signal_snapshot,
            'event_stream': event_stream,
            'receipt_ids': receipt_ids,
            'quant_payload': quant_payload,
            'raw_sources': result['sources'],
            'missing': result['missing_sources'],
            'errors': result['errors']
        }

    def _build_signal_snapshot(
        self,
        domain: str,
        sources: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Build signal snapshot for prompt from fetched sources.
        """
        snapshot = {}

        # Extract FRED data
        for key, data in sources.items():
            if key.startswith('fred_'):
                series_id = key.replace('fred_', '')
                if isinstance(data, dict) and 'values' in data:
                    values = data['values']
                    if values:
                        latest = values[0]  # Most recent
                        snapshot[series_id] = {
                            'value': latest.get('value'),
                            'date': latest.get('date'),
                            'source': 'FRED'
                        }

        # Extract VIX data
        if 'cboe_vix' in sources:
            vix_data = sources['cboe_vix'].get('vix_data', [])
            if vix_data:
                latest = vix_data[-1]
                snapshot['VIX'] = {
                    'close': latest.get('close'),
                    'date': latest.get('date'),
                    'source': 'CBOE'
                }

        # Extract Fed rates
        if 'nyfed_rates' in sources:
            snapshot['NY_FED'] = sources['nyfed_rates']

        return snapshot

    def _build_event_stream(
        self,
        domain: str,
        sources: Dict[str, Any]
    ) -> List[str]:
        """
        Build event stream from news sources.
        Placeholder - would parse actual news data.
        """
        events = []

        # Extract from Federal Register for policy domains
        if 'federal_register' in sources:
            docs = sources['federal_register'].get('documents', [])
            for doc in docs[:3]:  # Top 3 recent
                title = doc.get('title', '')
                if title:
                    events.append(f"Federal Register: {title[:100]}")

        return events

    async def generate_pulse(
        self,
        domain: str,
        data: Dict[str, Any],
        as_of_ts: datetime
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a pulse for a domain using AI.

        Args:
            domain: Specialist domain
            data: Fetched data (signal_snapshot, etc.)
            as_of_ts: Timestamp for the pulse

        Returns:
            Pulse data dictionary or None on failure
        """
        logger.info(f"Generating pulse for {domain}...")

        # Build prompt
        prompt = self.engine.build_prompt(
            domain=domain,
            as_of_ts=as_of_ts.isoformat(),
            signal_snapshot=data['signal_snapshot'],
            event_stream=data['event_stream'],
            receipt_ids=data['receipt_ids'],
            benchmark_summaries=[]
        )

        if self.dry_run:
            logger.info(f"[DRY RUN] Would call {self.model} with prompt ({len(prompt)} chars)")
            # Return mock pulse for dry run
            return self._mock_pulse(domain, as_of_ts)

        # Call AI model
        try:
            response = await self._call_ai_model(prompt, domain)
            pulse_data = self.engine.validate_response(response)
            return pulse_data
        except Exception as e:
            logger.error(f"[{domain}] AI generation failed: {e}")
            self.stats['errors'].append({
                'domain': domain,
                'stage': 'generation',
                'error': str(e)
            })
            return None

    async def _call_ai_model(self, prompt: str, domain: str) -> str:
        """
        Call the AI model to generate pulse.

        Uses OpenAI by default, falls back to Anthropic.
        """
        import httpx

        openai_key = os.environ.get('OPENAI_API_KEY')
        anthropic_key = os.environ.get('ANTHROPIC_API_KEY')

        if openai_key and self.model.startswith('gpt'):
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    'https://api.openai.com/v1/chat/completions',
                    headers={
                        'Authorization': f'Bearer {openai_key}',
                        'Content-Type': 'application/json'
                    },
                    json={
                        'model': self.model,
                        'messages': [
                            {'role': 'system', 'content': self.engine.system_prompt},
                            {'role': 'user', 'content': prompt}
                        ],
                        'temperature': 0.7,
                        'max_tokens': 4000
                    },
                    timeout=120.0
                )
                response.raise_for_status()
                data = response.json()
                return data['choices'][0]['message']['content']

        elif anthropic_key:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    'https://api.anthropic.com/v1/messages',
                    headers={
                        'x-api-key': anthropic_key,
                        'Content-Type': 'application/json',
                        'anthropic-version': '2023-06-01'
                    },
                    json={
                        'model': 'claude-3-5-sonnet-20241022',
                        'max_tokens': 4000,
                        'system': self.engine.system_prompt,
                        'messages': [
                            {'role': 'user', 'content': prompt}
                        ]
                    },
                    timeout=120.0
                )
                response.raise_for_status()
                data = response.json()
                return data['content'][0]['text']

        else:
            raise ValueError("No AI API key available (OPENAI_API_KEY or ANTHROPIC_API_KEY)")

    def _mock_pulse(self, domain: str, as_of_ts: datetime) -> Dict[str, Any]:
        """Generate mock pulse for dry run testing."""
        return {
            'domain': domain,
            'as_of_ts': as_of_ts.isoformat(),
            'tl_dr': f"Mock pulse for {domain} - dry run mode",
            'quantitative_analysis': {
                'primary_forecast': {
                    'horizon_1w': {'direction': 0, 'pressure_cents': 0.0, 'edge': 0.5},
                    'horizon_1m': {'direction': 0, 'pressure_cents': 0.0, 'edge': 0.5},
                    'horizon_3m': {'direction': 0, 'pressure_cents': 0.0, 'edge': 0.5},
                    'horizon_6m': {'direction': 0, 'pressure_cents': 0.0, 'edge': 0.5}
                }
            },
            'driver_attribution': {'mock_driver': 1.0},
            'regime_assessment': {'current': 'mock', 'volatility_regime': 'normal'}
        }

    async def store_pulse(
        self,
        domain: str,
        horizon: str,
        pulse_data: Dict[str, Any],
        data: Dict[str, Any],
        as_of_ts: datetime
    ) -> Optional[int]:
        """
        Store pulse to database.

        Args:
            domain: Specialist domain
            horizon: Time horizon
            pulse_data: Validated pulse data
            data: Original fetched data
            as_of_ts: Timestamp

        Returns:
            Inserted row ID or None
        """
        if self.dry_run:
            logger.info(f"[DRY RUN] Would store {domain}/{horizon} to database")
            return None

        try:
            conn = await get_connection()

            # Extract features
            features = extract_all_features(pulse_data, domain, as_of_ts)
            feature = features.get(horizon)

            if not feature:
                logger.error(f"[{domain}/{horizon}] Failed to extract features")
                return None

            # Build narrative (use tl_dr or full narrative from pulse)
            narrative = pulse_data.get('narrative', pulse_data.get('tl_dr', ''))

            # Store
            row_id = await insert_intel_drop(
                conn=conn,
                domain=domain,
                horizon=horizon,
                as_of_ts=as_of_ts,
                direction=feature.direction,
                pressure_cents=feature.pressure_cents,
                edge=feature.edge,
                driver_weights=feature.driver_weights,
                top_drivers=feature.top_drivers,
                regime_tags=feature.regime_tags,
                quality_flags=feature.quality_flags,
                data_gaps=data.get('missing', []),
                narrative=narrative,
                quant_payload=data.get('quant_payload', {}),
                receipts={'sources': data.get('receipt_ids', [])},
                source_model=self.model
            )

            await conn.close()
            logger.info(f"[{domain}/{horizon}] Stored with ID {row_id}")
            return row_id

        except Exception as e:
            logger.error(f"[{domain}/{horizon}] Storage failed: {e}")
            self.stats['errors'].append({
                'domain': domain,
                'horizon': horizon,
                'stage': 'storage',
                'error': str(e)
            })
            return None

    async def run(self) -> Dict[str, Any]:
        """
        Run full pulse generation for all configured domains.

        Returns:
            Statistics dictionary
        """
        as_of_ts = datetime.utcnow()
        logger.info(f"Starting pulse generation for {len(self.domains)} domains")
        logger.info(f"As-of timestamp: {as_of_ts.isoformat()}")
        logger.info(f"Dry run: {self.dry_run}")

        for domain in self.domains:
            try:
                # Fetch data
                data = await self.fetch_domain_data(domain)

                # Generate pulse
                pulse_data = await self.generate_pulse(domain, data, as_of_ts)

                if pulse_data:
                    self.stats['pulses_generated'] += 1

                    # Store for each horizon
                    for horizon in self.horizons:
                        row_id = await self.store_pulse(
                            domain, horizon, pulse_data, data, as_of_ts
                        )
                        if row_id:
                            self.stats['pulses_stored'] += 1

                self.stats['domains_processed'] += 1

            except Exception as e:
                logger.error(f"[{domain}] Failed: {e}")
                self.stats['errors'].append({
                    'domain': domain,
                    'stage': 'processing',
                    'error': str(e)
                })

        await self.close()

        # Summary
        logger.info("=" * 60)
        logger.info("PULSE GENERATION COMPLETE")
        logger.info(f"  Domains processed: {self.stats['domains_processed']}/{len(self.domains)}")
        logger.info(f"  Pulses generated: {self.stats['pulses_generated']}")
        logger.info(f"  Pulses stored: {self.stats['pulses_stored']}")
        logger.info(f"  Errors: {len(self.stats['errors'])}")
        if self.stats['errors']:
            for err in self.stats['errors'][:5]:
                logger.error(f"    - {err['domain']}: {err['error']}")

        return self.stats


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Generate pulses for ZINC-FUSION-V15 specialist domains'
    )
    parser.add_argument(
        '--domain', '-d',
        type=str,
        help='Single domain to process (default: all)'
    )
    parser.add_argument(
        '--horizon', '-H',
        type=str,
        help='Single horizon to process (default: all)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview without storing to database'
    )
    parser.add_argument(
        '--force-refresh',
        action='store_true',
        help='Skip cache and fetch fresh data'
    )
    parser.add_argument(
        '--model',
        type=str,
        default='gpt-4',
        help='AI model to use (default: gpt-4)'
    )

    args = parser.parse_args()

    # Validate domain
    domains = None
    if args.domain:
        if args.domain.upper() not in DOMAINS:
            print(f"Invalid domain: {args.domain}")
            print(f"Valid domains: {', '.join(DOMAINS)}")
            sys.exit(1)
        domains = [args.domain.upper()]

    # Validate horizon
    horizons = None
    if args.horizon:
        if args.horizon.upper() not in HORIZONS:
            print(f"Invalid horizon: {args.horizon}")
            print(f"Valid horizons: {', '.join(HORIZONS)}")
            sys.exit(1)
        horizons = [args.horizon.upper()]

    # Run generator
    generator = PulseGenerator(
        domains=domains,
        horizons=horizons,
        dry_run=args.dry_run,
        force_refresh=args.force_refresh,
        model=args.model
    )

    stats = await generator.run()

    # Exit with error if any failures
    if stats['errors']:
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
