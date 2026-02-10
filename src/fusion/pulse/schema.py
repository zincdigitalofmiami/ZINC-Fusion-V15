"""
ZINC-FUSION-V15 Pulse Schema

Universal schema for Intel Drops across all 11 specialist domains.
This is the contract that all AI pulse generators must follow.

VOCABULARY:
- edge: confidence level (0-1)
- pressure_cents: directional magnitude in cents/lb
- receipts: evidence document IDs or URLs
- proto_stacks: suggested signal convergence candidates
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any
from enum import Enum


class Domain(str, Enum):
    """11 Specialist Domains"""

    CRUSH = "CRUSH"
    CHINA = "CHINA"
    FX = "FX"
    FED = "FED"
    TARIFF = "TARIFF"
    ENERGY = "ENERGY"
    BIOFUEL = "BIOFUEL"
    PALM = "PALM"
    VOLATILITY = "VOLATILITY"
    SUBSTITUTES = "SUBSTITUTES"
    TRUMP_EFFECT = "TRUMP_EFFECT"


class Horizon(str, Enum):
    """4 Forecast Horizons"""

    ONE_WEEK = "1W"
    ONE_MONTH = "1M"
    THREE_MONTH = "3M"
    SIX_MONTH = "6M"


class Direction(int, Enum):
    """Directional stance"""

    SHORT = -1
    FLAT = 0
    LONG = 1


class QualityFlag(str, Enum):
    """Data quality indicators"""

    OK = "OK"
    LOW_EVIDENCE = "LOW_EVIDENCE"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    MISSING_SIGNALS = "MISSING_SIGNALS"
    OUTLIER_INPUTS = "OUTLIER_INPUTS"


@dataclass
class TopDriver:
    """
    Individual driver contributing to the forecast.
    """

    driver_id: str
    label: str
    sign: int  # -1 or +1
    weight: float  # 0.0 to 1.0
    receipts: List[str] = field(default_factory=list)


@dataclass
class DriverWeights:
    """
    Weight distribution across driver categories.
    MUST sum to 1.0 (±0.01 tolerance).
    """

    technical: float = 0.0
    flows: float = 0.0
    macro: float = 0.0
    policy: float = 0.0
    weather: float = 0.0
    positioning: float = 0.0
    sentiment: float = 0.0

    def sum(self) -> float:
        return (
            self.technical
            + self.flows
            + self.macro
            + self.policy
            + self.weather
            + self.positioning
            + self.sentiment
        )

    def is_valid(self, tolerance: float = 0.01) -> bool:
        return abs(self.sum() - 1.0) <= tolerance


@dataclass
class HorizonForecast:
    """
    Forecast for a single time horizon.
    """

    horizon: str  # 1W, 1M, 3M, 6M
    direction: int  # -1, 0, +1
    pressure_cents: float
    edge: float  # 0-1
    driver_weights: DriverWeights
    top_drivers: List[TopDriver]
    regime_tags: List[str] = field(default_factory=list)
    uncertainty_notes: List[str] = field(default_factory=list)


@dataclass
class Benchmark:
    """
    External benchmark reference (AgBull, ChAI, etc.)
    """

    source: str
    as_of_ts: str
    summary: str
    direction: int
    edge: float


@dataclass
class ProtoStackSuggestion:
    """
    Suggested signal convergence candidate.
    """

    stack_name: str
    signal_ids: List[str]
    rationale: str


@dataclass
class IntelDrop:
    """
    Complete Intel Drop for a single domain.
    """

    schema_version: str = "pulse.v1"
    as_of_ts: str = ""
    instrument: str = "CBOT:ZL"
    domain: str = ""
    horizons: List[HorizonForecast] = field(default_factory=list)
    benchmarks: List[Benchmark] = field(default_factory=list)
    data_gaps: List[str] = field(default_factory=list)
    quality_flags: List[str] = field(default_factory=list)
    suggested_proto_stacks: List[ProtoStackSuggestion] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "schema_version": self.schema_version,
            "as_of_ts": self.as_of_ts,
            "instrument": self.instrument,
            "domain": self.domain,
            "horizons": [
                {
                    "horizon": h.horizon,
                    "direction": h.direction,
                    "pressure_cents": h.pressure_cents,
                    "edge": h.edge,
                    "driver_weights": {
                        "technical": h.driver_weights.technical,
                        "flows": h.driver_weights.flows,
                        "macro": h.driver_weights.macro,
                        "policy": h.driver_weights.policy,
                        "weather": h.driver_weights.weather,
                        "positioning": h.driver_weights.positioning,
                        "sentiment": h.driver_weights.sentiment,
                    },
                    "top_drivers": [
                        {
                            "driver_id": d.driver_id,
                            "label": d.label,
                            "sign": d.sign,
                            "weight": d.weight,
                            "receipts": d.receipts,
                        }
                        for d in h.top_drivers
                    ],
                    "regime_tags": h.regime_tags,
                    "uncertainty_notes": h.uncertainty_notes,
                }
                for h in self.horizons
            ],
            "benchmarks": [
                {
                    "source": b.source,
                    "as_of_ts": b.as_of_ts,
                    "summary": b.summary,
                    "direction": b.direction,
                    "edge": b.edge,
                }
                for b in self.benchmarks
            ],
            "data_gaps": self.data_gaps,
            "quality_flags": self.quality_flags,
            "suggested_proto_stacks": [
                {
                    "stack_name": p.stack_name,
                    "signal_ids": p.signal_ids,
                    "rationale": p.rationale,
                }
                for p in self.suggested_proto_stacks
            ],
        }


PULSE_JSON_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["schema_version", "as_of_ts", "instrument", "domain", "horizons"],
    "properties": {
        "schema_version": {"type": "string", "const": "pulse.v1"},
        "as_of_ts": {"type": "string", "format": "date-time"},
        "instrument": {"type": "string"},
        "domain": {
            "type": "string",
            "enum": [
                "CRUSH",
                "CHINA",
                "FX",
                "FED",
                "TARIFF",
                "ENERGY",
                "BIOFUEL",
                "PALM",
                "VOLATILITY",
                "SUBSTITUTES",
                "TRUMP_EFFECT",
            ],
        },
        "horizons": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "horizon",
                    "direction",
                    "pressure_cents",
                    "edge",
                    "driver_weights",
                    "top_drivers",
                ],
                "properties": {
                    "horizon": {"type": "string", "enum": ["1W", "1M", "3M", "6M"]},
                    "direction": {"type": "integer", "enum": [-1, 0, 1]},
                    "pressure_cents": {"type": "number"},
                    "edge": {"type": "number", "minimum": 0, "maximum": 1},
                    "driver_weights": {
                        "type": "object",
                        "properties": {
                            "technical": {"type": "number"},
                            "flows": {"type": "number"},
                            "macro": {"type": "number"},
                            "policy": {"type": "number"},
                            "weather": {"type": "number"},
                            "positioning": {"type": "number"},
                            "sentiment": {"type": "number"},
                        },
                    },
                    "top_drivers": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["driver_id", "label", "sign", "weight"],
                            "properties": {
                                "driver_id": {"type": "string"},
                                "label": {"type": "string"},
                                "sign": {"type": "integer", "enum": [-1, 1]},
                                "weight": {
                                    "type": "number",
                                    "minimum": 0,
                                    "maximum": 1,
                                },
                                "receipts": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                        },
                    },
                    "regime_tags": {"type": "array", "items": {"type": "string"}},
                    "uncertainty_notes": {"type": "array", "items": {"type": "string"}},
                },
            },
            "minItems": 4,
            "maxItems": 4,
        },
        "benchmarks": {"type": "array"},
        "data_gaps": {"type": "array", "items": {"type": "string"}},
        "quality_flags": {"type": "array", "items": {"type": "string"}},
        "suggested_proto_stacks": {"type": "array"},
    },
}
