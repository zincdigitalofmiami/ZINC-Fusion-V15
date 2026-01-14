#!/usr/bin/env python3
"""
Phase 2a: Fix FRED observations_1d general tags
"""
import os
import psycopg2
from dotenv import load_dotenv
load_dotenv()

# FRED series → specialist mapping
# Based on Big 11 specialists + economic relevance
FRED_TAG_MAP = {
    # ===== FED (monetary policy, rates, liquidity) =====
    'T10Y3M': ['fed', 'volatility'],           # Treasury spread
    'DGS7': ['fed', 'volatility'],             # 7-year Treasury
    'DGS3MO': ['fed', 'volatility'],           # 3-month Treasury
    'DGS6MO': ['fed', 'volatility'],           # 6-month Treasury
    'DGS1MO': ['fed', 'volatility'],           # 1-month Treasury
    'DFEDTARL': ['fed'],                        # Fed funds lower
    'DFEDTARU': ['fed'],                        # Fed funds upper
    'SOFR': ['fed'],                            # Secured overnight rate
    'RRPONTSYD': ['fed'],                       # Reverse repo
    'WALCL': ['fed'],                           # Fed balance sheet
    'WRESBAL': ['fed'],                         # Reserve balances
    'TOTRESNS': ['fed'],                        # Total reserves
    'BOGMBASE': ['fed'],                        # Monetary base
    'M2SL': ['fed'],                            # M2 money supply
    'MORTGAGE30US': ['fed'],                    # Mortgage rates
    'STLFSI': ['fed', 'volatility'],           # Financial stress index
    'BUSLOANS': ['fed'],                        # Business loans
    'DRCCLACBS': ['fed'],                       # Consumer credit
    
    # ===== ENERGY =====
    'DJFUELUSGULF': ['energy'],                 # Jet fuel
    'DGASUSGULF': ['energy'],                   # Gasoline
    'DHOILNYH': ['energy'],                     # Heating oil
    'DDFUELUSGULF': ['energy'],                 # Diesel
    'PPOILUSDM': ['energy'],                    # Crude oil price
    'PNGASEUUSDM': ['energy'],                  # Natural gas EU
    'PROILUSDM': ['energy'],                    # Propane
    
    # ===== BIOFUEL =====
    'EIA_BIODIESEL_PRODUCTION': ['biofuel', 'energy'],
    'EIA_BIOFUEL_CONSUMPTION': ['biofuel', 'energy'],
    'EIA_BIOFUEL_SUPPLY': ['biofuel', 'energy'],
    'EIA_ETHANOL_CONSUMPTION': ['biofuel', 'energy'],
    'EIA_ETHANOL_INVENTORY': ['biofuel', 'energy'],
    'EIA_ETHANOL_PRODUCTION': ['biofuel', 'energy'],
    'EIA_RENEWABLE_DIESEL_PROD': ['biofuel', 'energy'],
    'EIA_RENEWABLE_DIESEL_PRODUCTION': ['biofuel', 'energy'],
    
    # ===== CRUSH (soy complex) =====
    'PSOILUSDM': ['core', 'crush'],            # Soybean oil price (ZL!)
    'PSOYBUSDM': ['crush'],                     # Soybean price
    'PCU311224311224': ['crush'],               # PPI soybean oil processing
    'SOYBEAN_ACRES_HARVESTED': ['crush'],
    'SOYBEAN_ACRES_PLANTED': ['crush'],
    'SOYBEAN_CRUSHED_TONS': ['crush'],
    'SOYBEAN_PRICE_PER_BU': ['crush'],
    'SOYBEAN_PRICE_USD_BU': ['crush'],
    'SOYBEAN_PRODUCTION_BU': ['crush'],
    'SOYBEAN_YIELD_BU_ACRE': ['crush'],
    
    # ===== SUBSTITUTES (competing commodities) =====
    'PMAIZMTUSDM': ['substitutes', 'biofuel'],  # Corn (ethanol)
    'PWHEAMTUSDM': ['substitutes'],              # Wheat
    'PSUNOUSDM': ['substitutes', 'palm'],        # Sunflower oil
    'PBARLUSDM': ['substitutes'],                # Barley
    'PCOPPUSDM': ['substitutes'],                # Copper (industrial proxy)
    'PRICENPQUSDM': ['substitutes'],             # Rice
    'CORN_ACRES_HARVESTED': ['substitutes', 'biofuel'],
    'CORN_ACRES_PLANTED': ['substitutes', 'biofuel'],
    'CORN_BEVERAGE_ALCOHOL_BU': ['substitutes', 'biofuel'],
    'CORN_ETHANOL_USAGE_BU': ['substitutes', 'biofuel'],
    'CORN_PRICE_PER_BU': ['substitutes', 'biofuel'],
    'CORN_PRICE_USD_BU': ['substitutes', 'biofuel'],
    'CORN_PRODUCTION_BU': ['substitutes', 'biofuel'],
    
    # ===== CHINA =====
    'CHNCPIALLMINMEI': ['china'],               # China CPI
    'CHNGDPNQDSMEI': ['china'],                 # China GDP
    'CHNMAINLANDTPU': ['china'],                # China trade
    'IR3TIB01CNM156N': ['china', 'fed'],        # China interbank rate
    'MYAGM2CNM189N': ['china', 'fed'],          # China M2
    'XTEXVA01CNM667S': ['china', 'tariff'],     # China exports
    'XTIMVA01CNM667S': ['china', 'tariff'],     # China imports
    'IMPCH': ['china', 'tariff'],               # Imports from China
    'EXPCH': ['china', 'tariff'],               # Exports to China
    
    # ===== TARIFF/TRADE =====
    'EMVTRADEPOLEMV': ['tariff', 'trump_effect'],  # Trade policy uncertainty
    'EPUTRADE': ['tariff', 'trump_effect'],        # Economic policy uncertainty - trade
    'BOPGSTB': ['tariff'],                         # Trade balance
    'IMPGS': ['tariff'],                           # Imports
    'EXPGS': ['tariff'],                           # Exports
    
    # ===== TRUMP_EFFECT (policy uncertainty) =====
    'USEPUINDXD': ['trump_effect', 'volatility'],  # EPU daily
    'USEPUINDXM': ['trump_effect', 'volatility'],  # EPU monthly
    
    # ===== VOLATILITY =====
    'OVXCLS': ['volatility', 'energy'],            # Oil VIX
    'VXGSCLS': ['volatility'],                     # Gold VIX
    'DXY': ['fx', 'volatility'],                   # Dollar index
    'NASDAQCOM': ['volatility'],                   # NASDAQ
    'SP500': ['volatility'],                       # S&P 500
    'SP500_HISTORICAL': ['volatility'],            # S&P 500 historical
    'CRISIS_VOLATILITY_INDEX': ['volatility'],
    'CRISIS_VIX': ['volatility'],
    'CRISIS_LABEL': ['volatility'],
    'CRISIS_INFLATION': ['volatility', 'fed'],
    'CRISIS_GDP_GROWTH': ['volatility'],
    'CRISIS_FX_RATE_CHANGE': ['volatility', 'fx'],
    'CRISIS_FX_CHANGE': ['volatility', 'fx'],
    'CRISIS_EQUITY_RETURN': ['volatility'],
    'CRISIS_BOND_YIELD': ['volatility', 'fed'],
    
    # ===== MACRO (general economic) → fed specialist =====
    'GDP': ['fed'],
    'GDPC1': ['fed'],
    'CPIAUCSL': ['fed'],
    'CPILFESL': ['fed'],
    'PCEPI': ['fed'],
    'PCE': ['fed'],
    'PCEPILFE': ['fed'],
    'UNRATE': ['fed'],
    'PAYEMS': ['fed'],
    'ICSA': ['fed'],                               # Initial claims
    'CCSA': ['fed'],                               # Continued claims
    'INDPRO': ['fed'],                             # Industrial production
    'HOUST': ['fed'],                              # Housing starts
    'PERMIT': ['fed'],                             # Building permits
    'RSXFS': ['fed'],                              # Retail sales
    'UMCSENT': ['fed'],                            # Consumer sentiment
    'MANEMP': ['fed'],                             # Manufacturing employment
    'PPIACO': ['fed'],                             # PPI all commodities
    'PPIFGS': ['fed'],                             # PPI finished goods
    'FRGSHPUSM649NCIS': ['fed'],                   # Freight shipments
    'LVXRNSA': ['fed'],                            # Las Vegas visitor volume
    'CLVMNACSCAB1GQEA19': ['fed'],                 # EU GDP
    'B235RC1Q027SBEA': ['fed'],                    # Personal income
    
    # ===== PALM/SUBSTITUTES (oils) =====
    'APU000074714': ['palm', 'substitutes'],       # Vegetable oil CPI
    'WPU01830161': ['palm', 'substitutes'],        # Vegetable oils PPI
    'WPU01830171': ['palm', 'substitutes'],        # Fats & oils PPI
    'WPU057303': ['energy'],                       # Petroleum products
    'WPU06140341': ['energy'],                     # Petroleum refining
    
    # ===== ENERGY (petroleum processing) =====
    'PCU32411032411012': ['energy'],               # Petroleum refining PPI
    
    # ===== FX (already covered but confirm) =====
    'BAMLC0A0CM': ['fed', 'volatility'],           # Corporate bond spread
}

conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()

print('=== PHASE 2a: FIXING FRED_OBSERVATIONS_1D GENERAL TAGS ===')
print(f'Mapping {len(FRED_TAG_MAP)} series')

total_updated = 0
unmapped = []

# Get all series with general tag
cur.execute('''
    SELECT DISTINCT series_id 
    FROM raw.fred_observations_1d 
    WHERE 'general' = ANY(specialist_tags)
''')
general_series = [r[0] for r in cur.fetchall()]

for series_id in general_series:
    if series_id in FRED_TAG_MAP:
        tags = FRED_TAG_MAP[series_id]
        cur.execute(
            "UPDATE raw.fred_observations_1d SET specialist_tags = %s WHERE series_id = %s AND 'general' = ANY(specialist_tags)",
            (tags, series_id)
        )
        updated = cur.rowcount
        total_updated += updated
        print(f'  {series_id}: {updated} rows → {tags}')
    else:
        unmapped.append(series_id)

conn.commit()

print(f'\nTOTAL UPDATED: {total_updated}')

if unmapped:
    print(f'\nUNMAPPED SERIES ({len(unmapped)}):')
    for s in unmapped:
        cur.execute("SELECT COUNT(*) FROM raw.fred_observations_1d WHERE series_id = %s AND 'general' = ANY(specialist_tags)", (s,))
        cnt = cur.fetchone()[0]
        print(f'  {s}: {cnt} rows still general')

# Verify remaining general
cur.execute("SELECT COUNT(*) FROM raw.fred_observations_1d WHERE 'general' = ANY(specialist_tags)")
remaining = cur.fetchone()[0]
print(f'\nRemaining general tags: {remaining}')

conn.close()
