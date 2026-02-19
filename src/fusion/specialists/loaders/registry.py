"""Specialist data loader registry."""

from datetime import date

import pandas as pd

from .biofuel import load_biofuel_data
from .china import load_china_data
from .crush import load_crush_data
from .energy import load_energy_data
from .fed import load_fed_data
from .fx import load_fx_data
from .palm import load_palm_data
from .substitutes import load_substitutes_data
from .tariff import load_tariff_data
from .trump_effect import load_trump_effect_data
from .volatility import load_volatility_data

# Registry mapping bucket name to loader function
DATA_LOADERS = {
    "crush": load_crush_data,
    "china": load_china_data,
    "energy": load_energy_data,
    "fx": load_fx_data,
    "fed": load_fed_data,
    "volatility": load_volatility_data,
    "substitutes": load_substitutes_data,
    "palm": load_palm_data,
    "biofuel": load_biofuel_data,
    "tariff": load_tariff_data,
    "trump_effect": load_trump_effect_data,
}


def load_specialist_data(
    bucket: str, start_date: date | None = None, end_date: date | None = None
) -> pd.DataFrame:
    """Load data for a specific specialist bucket."""
    if bucket not in DATA_LOADERS:
        raise ValueError(f"Unknown bucket: {bucket}")
    df = DATA_LOADERS[bucket](start_date, end_date)

    # Normalize to ZL trading calendar for all specialists.
    # Some "thick" loaders can introduce dates where non-ZL symbols trade but
    # ZL is missing; those rows inflate coverage and create off-calendar signals.
    if "close" in df.columns:
        df = df[df["close"].notna()]

    if not df.index.is_monotonic_increasing:
        df = df.sort_index()

    return df
