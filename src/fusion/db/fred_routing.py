"""
FRED Series Routing Map — Routes series_id to correct econ.* domain table.

This module provides the canonical mapping from FRED series IDs to their
domain-specific tables in the v2 schema architecture.

IMPORTANT: This module is SYNCED with TypeScript FRED_TABLE_MAP in
frontend/src/inngest/fred-daily.ts. TypeScript is the canonical source
because it is the writer (Inngest jobs write data to DB).

Domain Tables:
- econ.rates_1d: Interest rates, yields, spreads, FX rates
- econ.activity_1d: GDP, industrial production, trade, consumption
- econ.inflation_1d: CPI, PCE, PPI, inflation expectations, TIPS yields
- econ.labor_1d: Employment, claims
- econ.money_1d: Money supply, Fed balance sheet
- econ.vol_indices_1d: VIX, volatility indices, financial stress, equity indices, policy uncertainty
- econ.commodities_1d: Oil, gas, agricultural commodities, fuel prices, PPI commodities

Usage:
    from src.fusion.db.fred_routing import get_fred_table, FRED_SERIES_ROUTING

    table = get_fred_table("VIXCLS")  # Returns "econ.vol_indices_1d"
"""

# Master routing map — series_id -> qualified table name
# Synced with TypeScript FRED_TABLE_MAP (2026-01-23)
FRED_SERIES_ROUTING = {
    # =========================================================================
    # RATES (32 series) — Interest rates, yields, spreads, FX
    # =========================================================================
    # Fed policy rates
    "DFF": "econ.rates_1d",
    "FEDFUNDS": "econ.rates_1d",
    "DFEDTARL": "econ.rates_1d",
    "DFEDTARU": "econ.rates_1d",
    "SOFR": "econ.rates_1d",
    "DPRIME": "econ.rates_1d",
    "MORTGAGE30US": "econ.rates_1d",
    # Treasury yields
    "DGS1MO": "econ.rates_1d",
    "DGS3MO": "econ.rates_1d",
    "DGS6MO": "econ.rates_1d",
    "DGS1": "econ.rates_1d",
    "DGS2": "econ.rates_1d",
    "DGS5": "econ.rates_1d",
    "DGS7": "econ.rates_1d",
    "DGS10": "econ.rates_1d",
    "DGS20": "econ.rates_1d",
    "DGS30": "econ.rates_1d",
    # Yield curve spreads
    "T10Y2Y": "econ.rates_1d",
    "T10Y3M": "econ.rates_1d",
    # FX rates
    "DEXBZUS": "econ.rates_1d",
    "ARGCCUSMA02STM": "econ.rates_1d",
    "DEXCAUS": "econ.rates_1d",
    "DEXCHUS": "econ.rates_1d",
    "DEXINUS": "econ.rates_1d",
    "DEXJPUS": "econ.rates_1d",
    "DEXKOUS": "econ.rates_1d",
    "DEXMXUS": "econ.rates_1d",
    "DEXTAUS": "econ.rates_1d",
    "DEXUSAL": "econ.rates_1d",
    "DEXUSEU": "econ.rates_1d",
    "DEXUSUK": "econ.rates_1d",
    "DEXHKUS": "econ.rates_1d",
    "DEXMAUS": "econ.rates_1d",
    "DEXSFUS": "econ.rates_1d",
    "DEXTHUS": "econ.rates_1d",
    "DEXNOUS": "econ.rates_1d",
    "DEXSZUS": "econ.rates_1d",
    "DEXSIUS": "econ.rates_1d",
    # Dollar indices
    "DTWEXBGS": "econ.rates_1d",
    "DTWEXAFEGS": "econ.rates_1d",
    "DTWEXEMEGS": "econ.rates_1d",
    # NY Fed rates (if available)
    "NYFED_BGCR": "econ.rates_1d",
    "NYFED_EFFR": "econ.rates_1d",
    "NYFED_OBFR": "econ.rates_1d",
    "NYFED_SOFR": "econ.rates_1d",
    "NYFED_TGCR": "econ.rates_1d",
    # Discontinued but may have historical data
    "TEDRATE": "econ.rates_1d",
    # =========================================================================
    # INFLATION (14 series) — CPI, PCE, PPI, inflation expectations, TIPS yields
    # =========================================================================
    # Core inflation
    "CPIAUCSL": "econ.inflation_1d",
    "CPILFESL": "econ.inflation_1d",
    "PCEPI": "econ.inflation_1d",
    "PCEPILFE": "econ.inflation_1d",
    "PPIACO": "econ.inflation_1d",
    "PPIFIS": "econ.inflation_1d",  # Replaced PPIFGS (discontinued 2015)
    # Inflation expectations (DAILY)
    "T5YIE": "econ.inflation_1d",
    "T10YIE": "econ.inflation_1d",
    "T5YIFR": "econ.inflation_1d",
    # TIPS real yields (DAILY)
    "DFII5": "econ.inflation_1d",
    "DFII7": "econ.inflation_1d",
    "DFII10": "econ.inflation_1d",
    "DFII20": "econ.inflation_1d",
    "DFII30": "econ.inflation_1d",
    # =========================================================================
    # LABOR (5 series) — Employment, claims
    # =========================================================================
    "UNRATE": "econ.labor_1d",
    "PAYEMS": "econ.labor_1d",
    "MANEMP": "econ.labor_1d",
    "ICSA": "econ.labor_1d",
    "CCSA": "econ.labor_1d",
    # =========================================================================
    # ACTIVITY (19 series) — GDP, production, housing, trade, consumption
    # =========================================================================
    "GDP": "econ.activity_1d",
    "GDPC1": "econ.activity_1d",
    "INDPRO": "econ.activity_1d",
    "HOUST": "econ.activity_1d",
    "PERMIT": "econ.activity_1d",
    "RSXFS": "econ.activity_1d",
    "PCE": "econ.activity_1d",
    "UMCSENT": "econ.activity_1d",
    "FRGSHPUSM649NCIS": "econ.activity_1d",
    "BOPGSTB": "econ.activity_1d",
    "EXPGS": "econ.activity_1d",
    "IMPGS": "econ.activity_1d",
    "BUSLOANS": "econ.activity_1d",
    # China economic data
    "CHNCPIALLMINMEI": "econ.activity_1d",
    # NOTE: CHNPRINTO01IXPYM removed 2026-01-31 - discontinued series (822 days stale)
    "CHNGDPNQDSMEI": "econ.activity_1d",
    "CHNMAINLANDTPU": "econ.activity_1d",
    "XTEXVA01CNM667S": "econ.activity_1d",
    "XTIMVA01CNM667S": "econ.activity_1d",
    "IMPCH": "econ.activity_1d",
    "B235RC1Q027SBEA": "econ.activity_1d",
    # =========================================================================
    # VOL_INDICES (17 series) — VIX, stress, equity indices, policy uncertainty
    # =========================================================================
    # VIX family
    "VIXCLS": "econ.vol_indices_1d",
    "VXVCLS": "econ.vol_indices_1d",  # VIX3M (3-month VIX)
    "OVXCLS": "econ.vol_indices_1d",
    "GVZCLS": "econ.vol_indices_1d",
    # Financial stress indices
    "STLFSI4": "econ.vol_indices_1d",
    "NFCI": "econ.vol_indices_1d",
    "ANFCI": "econ.vol_indices_1d",
    # Credit spreads
    "BAMLH0A0HYM2": "econ.vol_indices_1d",  # High Yield OAS
    "BAMLC0A0CM": "econ.vol_indices_1d",  # Corporate OAS
    # Equity indices
    "SP500": "econ.vol_indices_1d",
    "NASDAQCOM": "econ.vol_indices_1d",
    # Policy uncertainty
    "USEPUINDXD": "econ.vol_indices_1d",
    "USEPUINDXM": "econ.vol_indices_1d",
    "EPUTRADE": "econ.vol_indices_1d",
    "EMVTRADEPOLEMV": "econ.vol_indices_1d",
    # =========================================================================
    # MONEY (8 series) — Money supply, Fed balance sheet
    # =========================================================================
    "M2SL": "econ.money_1d",
    "WALCL": "econ.money_1d",
    "BOGMBASE": "econ.money_1d",
    "WRESBAL": "econ.money_1d",
    "RRPONTSYD": "econ.money_1d",
    "TOTRESNS": "econ.money_1d",
    # China money/rates
    "MYAGM2CNM189N": "econ.money_1d",
    "IR3TIB01CNM156N": "econ.money_1d",
    # =========================================================================
    # COMMODITIES (32 series) — Oil, gas, agricultural, fuels, PPI commodities
    # =========================================================================
    # Crude oil
    "DCOILWTICO": "econ.commodities_1d",
    "DCOILBRENTEU": "econ.commodities_1d",
    # Natural gas
    "DHHNGSP": "econ.commodities_1d",
    "PNGASEUUSDM": "econ.commodities_1d",
    # Heating oil / diesel / gasoline
    "DHOILNYH": "econ.commodities_1d",
    "DDFUELUSGULF": "econ.commodities_1d",
    "DGASUSGULF": "econ.commodities_1d",
    "DJFUELUSGULF": "econ.commodities_1d",
    "DPROPANEMBTX": "econ.commodities_1d",
    # Retail fuel prices
    "APU000074714": "econ.commodities_1d",
    "GASREGW": "econ.commodities_1d",
    "GASDESW": "econ.commodities_1d",
    # PPI ethanol
    "WPU06140341": "econ.commodities_1d",
    # World Bank oilseed prices
    "PSOILUSDM": "econ.commodities_1d",
    "PSOYBUSDM": "econ.commodities_1d",
    "PCU311224311224": "econ.commodities_1d",
    # Grains
    "PMAIZMTUSDM": "econ.commodities_1d",
    "PWHEAMTUSDM": "econ.commodities_1d",
    "PBARLUSDM": "econ.commodities_1d",
    # Palm and other oils
    "PPOILUSDM": "econ.commodities_1d",
    "PROILUSDM": "econ.commodities_1d",
    # Metals and other
    "PCOPPUSDM": "econ.commodities_1d",
    "PRICENPQUSDM": "econ.commodities_1d",
    "PSUNOUSDM": "econ.commodities_1d",
    "POLVOILUSDM": "econ.commodities_1d",
    "PSUGAISAUSDM": "econ.commodities_1d",
    # PPI commodity series
    "WPU057303": "econ.commodities_1d",
    "PCU32411032411012": "econ.commodities_1d",
    "WPU01830161": "econ.commodities_1d",
    "WPU01830171": "econ.commodities_1d",
}

# Default table for unknown series (activity is the catch-all)
DEFAULT_ECON_TABLE = "econ.activity_1d"


# =============================================================================
# SPECIALIST ROUTING — Maps each Big-11 bucket to its required econ.* tables
# =============================================================================
# This enables bucket-aware loading: query only 1-2 tables per specialist,
# NOT all 7 tables via UNION ALL.
#
# Source: SPECIALIST_FEATURE_CONFIGS in scripts/generate_specialist_features.py

SPECIALIST_ECON_TABLES: dict[str, list[str]] = {
    # Buckets with NO FRED data (use fundamentals/supply tables instead)
    "crush": [],  # Uses mkt.futures_1d (ZL, ZS, ZM spreads)
    "palm": [],  # Uses mkt.futures_1d (FCPO) — no FRED palm data
    "biofuel": [],  # Uses supply.epa_rin_1d — RINs not in FRED
    # Buckets with FRED data
    "china": ["econ.commodities_1d"],  # PCOPPUSDM (copper as China demand proxy)
    "energy": ["econ.commodities_1d"],  # DCOILWTICO, DCOILBRENTEU
    "fx": ["econ.rates_1d"],  # DTWEXBGS (dollar index)
    "fed": [
        "econ.rates_1d",
        "econ.vol_indices_1d",
    ],  # FEDFUNDS, DGS10, DGS2, T10Y2Y + NFCI
    "tariff": ["econ.vol_indices_1d"],  # USEPUINDXM (policy uncertainty)
    "volatility": ["econ.vol_indices_1d"],  # VIXCLS, OVXCLS, STLFSI4
    "substitutes": ["econ.commodities_1d"],  # PSUNOUSDM (sunflower oil)
    "trump_effect": [
        "econ.vol_indices_1d",
        "econ.rates_1d",
    ],  # USEPUINDXD, EPUTRADE + T10Y2Y
}

# Curated FRED series per specialist bucket
# Source: "fred_series" in SPECIALIST_FEATURE_CONFIGS
SPECIALIST_FRED_SERIES: dict[str, list[str]] = {
    "crush": [],
    "china": ["PCOPPUSDM"],
    "fx": ["DTWEXBGS"],
    "fed": ["FEDFUNDS", "DGS10", "DGS2", "T10Y2Y", "NFCI"],
    "tariff": ["USEPUINDXM"],
    "energy": ["DCOILWTICO", "DCOILBRENTEU"],
    "biofuel": [],
    "palm": [],
    "volatility": ["VIXCLS", "OVXCLS", "STLFSI4"],
    "substitutes": ["PSUNOUSDM"],
    "trump_effect": ["VIXCLS", "T10Y2Y", "USEPUINDXD", "EPUTRADE"],
}


def get_fred_table(series_id: str) -> str:
    """
    Get the target econ.* table for a FRED series.

    Args:
        series_id: FRED series identifier (e.g., "VIXCLS", "DGS10")

    Returns:
        Fully qualified table name (e.g., "econ.vol_indices_1d")
    """
    return FRED_SERIES_ROUTING.get(series_id.upper(), DEFAULT_ECON_TABLE)


def get_fred_schema_table(series_id: str) -> tuple[str, str]:
    """
    Get schema and table name separately for a FRED series.

    Args:
        series_id: FRED series identifier

    Returns:
        Tuple of (schema, table_name) e.g., ("econ", "vol_indices_1d")
    """
    qualified = get_fred_table(series_id)
    schema, table = qualified.split(".")
    return schema, table


def get_all_econ_tables() -> list[str]:
    """Get list of all econ.* tables for UNION queries."""
    return [
        "econ.rates_1d",
        "econ.activity_1d",
        "econ.inflation_1d",
        "econ.labor_1d",
        "econ.money_1d",
        "econ.vol_indices_1d",
        "econ.commodities_1d",
    ]


def get_series_for_table(table_name: str) -> list[str]:
    """
    Get list of all series IDs routed to a specific table.

    Args:
        table_name: Qualified table name (e.g., "econ.vol_indices_1d")

    Returns:
        List of series IDs routed to that table
    """
    return [sid for sid, tbl in FRED_SERIES_ROUTING.items() if tbl == table_name]


def get_tables_for_series(series_ids: list[str]) -> dict[str, list[str]]:
    """
    Group series IDs by their target table for efficient queries.

    Args:
        series_ids: List of FRED series IDs

    Returns:
        Dict mapping table name to list of series IDs for that table

    Example:
        >>> get_tables_for_series(["VIXCLS", "DGS10", "OVXCLS"])
        {
            "econ.vol_indices_1d": ["VIXCLS", "OVXCLS"],
            "econ.rates_1d": ["DGS10"]
        }
    """
    result: dict[str, list[str]] = {}
    for sid in series_ids:
        table = get_fred_table(sid)
        if table not in result:
            result[table] = []
        result[table].append(sid)
    return result


# =============================================================================
# SPECIALIST-AWARE ROUTING FUNCTIONS
# =============================================================================


def get_specialist_tables(bucket: str) -> list[str]:
    """
    Get the econ.* tables needed for a specific specialist bucket.

    This is the core of Option B: instead of querying all 7 tables,
    each specialist queries only the 1-2 tables it actually needs.

    Args:
        bucket: Specialist bucket name (e.g., "volatility", "fed", "crush")

    Returns:
        List of table names this bucket needs (may be empty for non-FRED buckets)

    Example:
        >>> get_specialist_tables("volatility")
        ["econ.vol_indices_1d"]
        >>> get_specialist_tables("fed")
        ["econ.rates_1d", "econ.vol_indices_1d"]
        >>> get_specialist_tables("crush")
        []  # No FRED data, uses fundamentals only
    """
    return SPECIALIST_ECON_TABLES.get(bucket, [])


def get_specialist_series(bucket: str) -> list[str]:
    """
    Get the curated FRED series IDs for a specific specialist bucket.

    These are the series explicitly defined in SPECIALIST_FEATURE_CONFIGS
    for each bucket's fred_series field.

    Args:
        bucket: Specialist bucket name

    Returns:
        List of FRED series IDs this bucket uses (may be empty)

    Example:
        >>> get_specialist_series("volatility")
        ["VIXCLS", "OVXCLS", "STLFSI4"]
        >>> get_specialist_series("crush")
        []
    """
    return SPECIALIST_FRED_SERIES.get(bucket, [])


def build_specialist_query(bucket: str) -> str | None:
    """
    Build an optimized SQL query for a specialist bucket's FRED data.

    Returns None if the bucket doesn't use FRED data.

    Args:
        bucket: Specialist bucket name

    Returns:
        SQL query string or None

    Example:
        >>> build_specialist_query("volatility")
        '''
        SELECT event_date AS as_of_date, series_id, value
        FROM econ.vol_indices_1d
        WHERE series_id IN ('VIXCLS', 'OVXCLS', 'STLFSI4')
        ORDER BY event_date, series_id
        '''
    """
    tables = get_specialist_tables(bucket)
    series = get_specialist_series(bucket)

    if not tables or not series:
        return None

    # Group series by their canonical table
    table_series = get_tables_for_series(series)

    # Build UNION ALL only across tables this bucket actually needs
    queries = []
    for tbl in tables:
        series_in_table = table_series.get(tbl, [])
        if series_in_table:
            placeholders = ", ".join(f"'{s}'" for s in series_in_table)
            queries.append(
                f"SELECT event_date AS as_of_date, series_id, value "
                f"FROM {tbl} WHERE series_id IN ({placeholders})"
            )

    if not queries:
        return None

    return " UNION ALL ".join(queries) + " ORDER BY as_of_date, series_id"


def get_all_specialist_buckets() -> list[str]:
    """Return list of all Big-11 specialist bucket names."""
    return list(SPECIALIST_ECON_TABLES.keys())
