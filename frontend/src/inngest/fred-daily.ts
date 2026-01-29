/**
 * FRED Daily Bronze Ingestion
 * 
 * BRONZE CONTRACT COMPLIANT:
 * - Logs each run in ops.ingest_run
 * - Computes row_hash for idempotency
 * - Assigns specialist_tags per MAPPING doc
 * - Append-only inserts (no upserts)
 * - Quarantines invalid records to ops.quarantined_record
 * 
 * @author Claude (ZINC-FUSION-V15)
 * @version 2.0.0 - Bronze Contract
 * @date 2026-01-11
 */

import { inngest } from "./client";
import { Pool, type PoolClient } from "pg";
import { createHash } from "crypto";

// Database connection pool
const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

// =============================================================================
// FRED SERIES CONFIGURATION WITH SPECIALIST TAGS
// =============================================================================

interface FredSeriesConfig {
  id: string;
  name: string;
  tags: string[];
}

interface FredSegmentConfig {
  segment: string;
  id: string;
  jobName: string;
  displayName: string;
  cron: string;
  series: FredSeriesConfig[];
  rateLimitMs?: number;
  fetchTimeoutMs?: number;
  fetchRetries?: number;
  fetchBackoffMs?: number;
  retries?: InngestRetries;
}

type FredIngestResult = { series: string; status: string; value?: number; tags?: string[] };

interface FredSegmentSummary {
  attempted: number;
  inserted: number;
  skipped: number;
  quarantined: number;
  results: FredIngestResult[];
}

type InngestRetries =
  | 0
  | 1
  | 2
  | 3
  | 4
  | 5
  | 6
  | 7
  | 8
  | 9
  | 10
  | 11
  | 12
  | 13
  | 14
  | 15
  | 16
  | 17
  | 18
  | 19
  | 20;

const DEFAULT_JOB_RETRIES: InngestRetries = 3;

/**
 * Comprehensive FRED series list grouped by specialist bucket.
 * Source: RAW_SOURCE_SPECIALIST_MAPPING.md (LOCKED)
 */
const FRED_FED_SERIES: FredSeriesConfig[] = [
  // Core Fed policy rates - affect financing costs, dollar strength
  { id: "DFF", name: "Fed Funds Effective Rate", tags: ["fed", "fx"] },
  { id: "FEDFUNDS", name: "Federal Funds Effective Rate", tags: ["fed", "fx"] },
  { id: "DFEDTARL", name: "Fed Funds Target Range (Lower)", tags: ["fed"] },
  { id: "DFEDTARU", name: "Fed Funds Target Range (Upper)", tags: ["fed"] },
  // Treasury yields - carry cost, dollar strength, risk sentiment
  { id: "DGS1MO", name: "1-Month Treasury", tags: ["fed", "volatility"] },
  { id: "DGS3MO", name: "3-Month Treasury", tags: ["fed", "volatility"] },
  { id: "DGS6MO", name: "6-Month Treasury", tags: ["fed"] },
  { id: "DGS1", name: "1-Year Treasury", tags: ["fed"] },
  { id: "DGS2", name: "2-Year Treasury", tags: ["fed", "fx"] },
  { id: "DGS5", name: "5-Year Treasury", tags: ["fed"] },
  { id: "DGS7", name: "7-Year Treasury", tags: ["fed"] },
  { id: "DGS10", name: "10-Year Treasury", tags: ["fed", "fx", "volatility"] },
  { id: "DGS20", name: "20-Year Treasury", tags: ["fed"] },
  { id: "DGS30", name: "30-Year Treasury", tags: ["fed"] },
  // Yield curve spreads - recession indicator, risk sentiment
  { id: "T10Y2Y", name: "10Y-2Y Spread (Yield Curve)", tags: ["fed", "volatility"] },
  { id: "T10Y3M", name: "10Y-3M Spread", tags: ["fed", "volatility"] },
  // Inflation expectations (DAILY) - affects real rates, biofuel economics
  { id: "T5YIE", name: "5Y Breakeven Inflation", tags: ["fed", "energy", "biofuel"] },
  { id: "T10YIE", name: "10Y Breakeven Inflation", tags: ["fed", "energy", "biofuel"] },
  { id: "T5YIFR", name: "5Y-5Y Forward Inflation Expectation", tags: ["fed", "energy"] },
  // TIPS real yields (DAILY) - inverse inflation proxy
  { id: "DFII5", name: "5Y TIPS Yield", tags: ["fed", "volatility"] },
  { id: "DFII7", name: "7Y TIPS Yield", tags: ["fed"] },
  { id: "DFII10", name: "10Y TIPS Yield", tags: ["fed", "volatility"] },
  { id: "DFII20", name: "20Y TIPS Yield", tags: ["fed"] },
  { id: "DFII30", name: "30Y TIPS Yield", tags: ["fed"] },
  { id: "SOFR", name: "SOFR Rate", tags: ["fed"] },
  { id: "DPRIME", name: "Prime Rate", tags: ["fed"] },
  { id: "MORTGAGE30US", name: "30-Year Mortgage Rate", tags: ["fed"] },
  // Fed balance sheet - liquidity, dollar supply
  { id: "WALCL", name: "Fed Total Assets", tags: ["fed", "volatility"] },
  { id: "WRESBAL", name: "Reserve Balances", tags: ["fed"] },
  { id: "RRPONTSYD", name: "Reverse Repo", tags: ["fed", "volatility"] },
  { id: "BOGMBASE", name: "Monetary Base", tags: ["fed", "fx"] },
  { id: "M2SL", name: "M2 Money Stock", tags: ["fed", "fx"] },
  { id: "TOTRESNS", name: "Total Reserves", tags: ["fed"] },
  // Credit conditions - economic health
  { id: "BUSLOANS", name: "Commercial & Industrial Loans", tags: ["fed", "crush"] },
  { id: "DRCCLACBS", name: "Credit Card Delinquency Rate", tags: ["fed", "volatility"] },
  // Inflation metrics - affect production costs, biofuel economics
  { id: "CPIAUCSL", name: "CPI All Urban", tags: ["fed", "energy", "biofuel"] },
  { id: "CPILFESL", name: "Core CPI", tags: ["fed"] },
  { id: "PCEPI", name: "PCE Price Index", tags: ["fed", "energy"] },
  { id: "PCEPILFE", name: "Core PCE", tags: ["fed"] },
  { id: "PCE", name: "Personal Consumption Expenditures", tags: ["fed", "biofuel"] },
  // PPI - production cost pressures (monthly)
  { id: "PPIACO", name: "PPI All Commodities", tags: ["fed", "energy", "crush"] },
  { id: "PPIFIS", name: "PPI Final Demand", tags: ["fed", "crush"] },  // Replaced PPIFGS (discontinued 2015)
  // Labor market - demand indicator
  { id: "UNRATE", name: "Unemployment Rate", tags: ["fed", "volatility"] },
  { id: "PAYEMS", name: "Nonfarm Payrolls", tags: ["fed"] },
  { id: "MANEMP", name: "Manufacturing Employment", tags: ["fed", "china", "crush"] },
  // Demand indicators
  { id: "RSXFS", name: "Retail Sales", tags: ["fed", "biofuel"] },
  { id: "GDP", name: "Gross Domestic Product", tags: ["fed", "energy", "crush"] },
  { id: "GDPC1", name: "Real Gross Domestic Product", tags: ["fed", "energy"] },
  { id: "HOUST", name: "Housing Starts", tags: ["fed"] },
  { id: "PERMIT", name: "Housing Permits", tags: ["fed"] },
  { id: "ICSA", name: "Initial Jobless Claims", tags: ["fed", "volatility"] },
  { id: "CCSA", name: "Continued Claims", tags: ["fed", "volatility"] },
];

const FRED_FX_SERIES: FredSeriesConfig[] = [
  // Brazil - #1 soybean exporter, competes with US crush
  { id: "DEXBZUS", name: "USD/BRL (Brazil)", tags: ["fx", "crush", "china"] },
  // China - #1 soybean importer, ZL demand driver
  { id: "DEXCHUS", name: "USD/CNY (China)", tags: ["fx", "china", "crush", "tariff"] },
  // EUR - biofuel policy, rapeseed competition
  { id: "DEXUSEU", name: "USD/EUR", tags: ["fx", "biofuel", "substitutes"] },
  { id: "DEXUSUK", name: "USD/GBP", tags: ["fx"] },
  // JPY - risk sentiment proxy
  { id: "DEXJPUS", name: "USD/JPY", tags: ["fx", "volatility"] },
  // CAD - energy exporter, canola producer
  { id: "DEXCAUS", name: "USD/CAD", tags: ["fx", "energy", "substitutes"] },
  // MXN - US trade partner, tariff sensitive
  { id: "DEXMXUS", name: "USD/MXN", tags: ["fx", "tariff"] },
  // Korea - soybean importer
  { id: "DEXKOUS", name: "USD/KRW (Korea)", tags: ["fx", "china"] },
  // India - major vegetable oil importer
  { id: "DEXINUS", name: "USD/INR (India)", tags: ["fx", "palm", "substitutes"] },
  // Malaysia - #2 palm oil producer
  { id: "DEXMAUS", name: "USD/MYR (Malaysia)", tags: ["fx", "palm"] },
  // Singapore - palm oil trading hub
  { id: "DEXSFUS", name: "USD/SGD (Singapore)", tags: ["fx", "palm"] },
  // Thailand - palm producer, rice exporter
  { id: "DEXTHUS", name: "USD/THB (Thailand)", tags: ["fx", "palm", "substitutes"] },
  // HK - China proxy
  { id: "DEXHKUS", name: "USD/HKD (Hong Kong)", tags: ["fx", "china"] },
  // Taiwan - China proxy, tech demand
  { id: "DEXTAUS", name: "USD/TWD (Taiwan)", tags: ["fx", "china"] },
  // AUD - commodity currency, China trade
  { id: "DEXUSAL", name: "USD/AUD", tags: ["fx", "china", "energy"] },
  // NOK - oil exporter
  { id: "DEXNOUS", name: "USD/NOK", tags: ["fx", "energy"] },
  // CHF - safe haven
  { id: "DEXSZUS", name: "USD/CHF", tags: ["fx", "volatility"] },
  { id: "DEXSIUS", name: "USD/SEK", tags: ["fx"] },
  // Dollar indices - broad strength affects all commodities
  { id: "DTWEXBGS", name: "Trade-Weighted USD (Broad)", tags: ["fx", "crush", "energy"] },
  { id: "DTWEXAFEGS", name: "USD vs Advanced FX", tags: ["fx"] },
  { id: "DTWEXEMEGS", name: "USD vs EM FX", tags: ["fx", "china", "palm", "crush"] },
];

const FRED_ENERGY_SERIES: FredSeriesConfig[] = [
  // Crude oils - biofuel feedstock competitor, diesel/heating oil economics
  { id: "DCOILWTICO", name: "WTI Crude Oil", tags: ["energy", "biofuel", "crush"] },
  { id: "DCOILBRENTEU", name: "Brent Crude Oil", tags: ["energy", "biofuel", "china"] },
  // Natural gas - fertilizer cost, crop drying, EU demand
  { id: "DHHNGSP", name: "Henry Hub Natural Gas", tags: ["energy", "crush", "substitutes"] },
  // Heating oil - biodiesel benchmark, ZL direct competitor
  { id: "DHOILNYH", name: "Heating Oil NY Harbor", tags: ["energy", "biofuel", "crush"] },
  // EU natgas - fertilizer costs, European demand
  { id: "PNGASEUUSDM", name: "EU Natural Gas Price", tags: ["energy", "crush"] },
  // Diesel/gasoline - biodiesel/ethanol benchmark, RIN economics
  { id: "DDFUELUSGULF", name: "Diesel Gulf Coast", tags: ["energy", "biofuel", "crush"] },
  { id: "DGASUSGULF", name: "Gasoline Gulf Coast", tags: ["energy", "biofuel"] },
  // Jet fuel - SAF feedstock demand (growing ZL driver)
  { id: "DJFUELUSGULF", name: "Jet Fuel Gulf Coast", tags: ["energy", "biofuel", "crush"] },
  // Propane - crop drying, export competitor
  { id: "DPROPANEMBTX", name: "Propane Prices: Mont Belvieu, Texas", tags: ["energy", "crush"] },
  // PPI fuels - production cost inputs
  { id: "WPU057303", name: "PPI Diesel Fuel", tags: ["energy", "biofuel", "crush"] },
  { id: "PCU32411032411012", name: "PPI Motor Gasoline", tags: ["energy", "biofuel"] },
];

const FRED_BIOFUEL_SERIES: FredSeriesConfig[] = [
  // Retail fuel prices - biodiesel/ethanol blend economics
  { id: "APU000074714", name: "Gasoline CPI (Unleaded Regular)", tags: ["biofuel", "energy", "crush"] },
  { id: "GASREGW", name: "US Regular Gas Price", tags: ["biofuel", "energy"] },
  // Diesel price - direct biodiesel competitor, ZL demand driver
  { id: "GASDESW", name: "US Diesel Price", tags: ["biofuel", "energy", "crush"] },
  // Ethanol PPI - corn ethanol economics, competes with soy biodiesel
  { id: "WPU06140341", name: "PPI Ethanol", tags: ["biofuel", "crush", "substitutes"] },
];

const FRED_CRUSH_SERIES: FredSeriesConfig[] = [
  // World Bank soy prices - direct ZL/ZS benchmark
  { id: "PSOILUSDM", name: "Soybean Oil Price (World Bank)", tags: ["crush", "palm", "substitutes", "biofuel"] },
  { id: "PSOYBUSDM", name: "Soybeans Price (World Bank)", tags: ["crush", "china", "tariff"] },
  // PPI processing - crush margin proxy
  { id: "PCU311224311224", name: "PPI Soybean Oil Processing", tags: ["crush", "biofuel"] },
  // Corn - feed competition, ethanol feedstock
  { id: "PMAIZMTUSDM", name: "Global price of Corn", tags: ["crush", "substitutes", "biofuel", "china"] },
  // Wheat/barley - acreage competition, feed substitution
  { id: "PWHEAMTUSDM", name: "Wheat Price", tags: ["substitutes", "crush", "china"] },
  { id: "PBARLUSDM", name: "Barley Price", tags: ["substitutes", "crush"] },
];

const FRED_PALM_SERIES: FredSeriesConfig[] = [
  // Palm oil - #1 ZL substitute, direct price competition
  { id: "PPOILUSDM", name: "Global price of Palm Oil", tags: ["palm", "crush", "substitutes", "china"] },
  // Rapeseed oil - EU biodiesel feedstock, ZL substitute
  { id: "PROILUSDM", name: "Global price of Rapeseed Oil (proxy for palm kernel)", tags: ["palm", "substitutes", "crush", "biofuel"] },
];

const FRED_VOLATILITY_SERIES: FredSeriesConfig[] = [
  // Equity indices - risk appetite, demand proxy
  { id: "SP500", name: "S&P 500 Index", tags: ["volatility", "fed"] },
  { id: "NASDAQCOM", name: "NASDAQ Composite Index", tags: ["volatility"] },
  // VIX - fear gauge, affects all risk assets
  { id: "VIXCLS", name: "VIX Index", tags: ["volatility", "crush", "energy"] },
  // VIX3M (VXVCLS) - 3-month VIX for term structure analysis
  // VIX/VIX3M spread: backwardation = panic, contango = complacency
  { id: "VXVCLS", name: "VIX3M (3-Month VIX)", tags: ["volatility", "fed", "energy"] },
  // OVX - crude oil specific volatility, energy sector stress
  { id: "OVXCLS", name: "Crude Oil Volatility", tags: ["volatility", "energy", "biofuel"] },
  // Financial stress (weekly) - credit conditions, demand destruction risk
  // NOTE: STLFSI discontinued 2020, TEDRATE discontinued 2022 - using replacements
  { id: "STLFSI4", name: "St. Louis Financial Stress Index", tags: ["volatility", "fed"] },
  { id: "NFCI", name: "Chicago Fed National Financial Conditions", tags: ["volatility", "fed"] },
  { id: "ANFCI", name: "Chicago Fed Adjusted NFCI", tags: ["volatility", "fed"] },
  // Credit spreads - risk appetite, economic stress
  { id: "BAMLH0A0HYM2", name: "High Yield OAS", tags: ["volatility", "fed", "energy"] },
  { id: "BAMLC0A0CM", name: "Corporate OAS", tags: ["volatility", "fed"] },
];

const FRED_TRUMP_EFFECT_SERIES: FredSeriesConfig[] = [
  // Policy uncertainty - affects all trade-sensitive commodities
  { id: "USEPUINDXD", name: "US Policy Uncertainty (Daily)", tags: ["trump_effect", "volatility", "tariff"] },
  { id: "USEPUINDXM", name: "US Policy Uncertainty (Monthly)", tags: ["trump_effect", "volatility", "tariff"] },
  // Trade policy specific - direct soy/ZL tariff risk
  { id: "EPUTRADE", name: "Trade Policy Uncertainty", tags: ["tariff", "trump_effect", "china", "crush"] },
  { id: "EMVTRADEPOLEMV", name: "Trade Policy Volatility", tags: ["trump_effect", "volatility", "tariff", "china"] },
  // China trade policy - soybean tariff risk
  { id: "CHNMAINLANDTPU", name: "China Trade Policy Uncertainty", tags: ["trump_effect", "tariff", "china", "crush"] },
  // Tariff receipts - actual tariff implementation
  { id: "B235RC1Q027SBEA", name: "Customs Duties (Tariff Receipts)", tags: ["trump_effect", "tariff", "china"] },
  // China imports - trade war barometer
  { id: "IMPCH", name: "US Imports from China", tags: ["trump_effect", "tariff", "china"] },
];

const FRED_CHINA_SERIES: FredSeriesConfig[] = [
  // China inflation - demand indicator, hog feed economics
  { id: "CHNCPIALLMINMEI", name: "China CPI (Total)", tags: ["china", "crush", "palm"] },
  // China industrial production - soybean meal demand, vegetable oil demand
  { id: "CHNPRINTO01IXPYM", name: "China Industrial Production", tags: ["china", "crush", "energy"] },
  // China GDP - overall demand driver
  { id: "CHNGDPNQDSMEI", name: "China Real GDP", tags: ["china", "crush", "energy", "palm"] },
  // China rates - financing costs, CNY strength
  { id: "IR3TIB01CNM156N", name: "China Interbank Rate (3M)", tags: ["china", "fx"] },
  // China M2 - liquidity, stimulus proxy
  { id: "MYAGM2CNM189N", name: "China M2", tags: ["china", "fx", "crush"] },
  // China trade - direct soybean flow indicator
  { id: "XTEXVA01CNM667S", name: "China Exports Value", tags: ["china", "tariff", "fx"] },
  { id: "XTIMVA01CNM667S", name: "China Imports Value", tags: ["china", "tariff", "crush", "palm"] },
];

const FRED_GENERAL_SERIES: FredSeriesConfig[] = [
  // Industrial production affects energy demand, crush margins, and overall demand
  { id: "INDPRO", name: "Industrial Production", tags: ["energy", "crush", "china"] },
  // Consumer sentiment affects discretionary spending, fuel demand
  { id: "UMCSENT", name: "Consumer Sentiment", tags: ["volatility", "biofuel"] },
  // Freight index affects export logistics, supply chain costs
  { id: "FRGSHPUSM649NCIS", name: "Cass Freight Index", tags: ["tariff", "crush", "china"] },
  // Trade balance/exports/imports - core tariff indicators
  { id: "BOPGSTB", name: "Trade Balance (Goods & Services)", tags: ["tariff", "china"] },
  { id: "EXPGS", name: "Exports of Goods & Services", tags: ["tariff", "china", "crush"] },
  { id: "IMPGS", name: "Imports of Goods & Services", tags: ["tariff", "china", "palm"] },
  // Copper - industrial demand proxy, China construction/manufacturing
  { id: "PCOPPUSDM", name: "Copper Price (Global)", tags: ["china", "volatility"] },
  // Rice - food grain substitute, competes for acreage
  { id: "PRICENPQUSDM", name: "Rice Price (Global)", tags: ["substitutes", "china"] },
  // Sunflower oil - direct ZL substitute
  { id: "PSUNOUSDM", name: "Sunflower Oil Price (Global)", tags: ["substitutes", "crush", "palm"] },
  // Olive oil - premium substitute, EU production
  { id: "POLVOILUSDM", name: "Olive Oil Price (Global)", tags: ["substitutes", "palm"] },
  // Sugar - biofuel feedstock competitor (ethanol)
  { id: "PSUGAISAUSDM", name: "Sugar Price (Global)", tags: ["substitutes", "biofuel", "energy"] },
  // PPI Sunflower/Canola - domestic oilseed substitutes
  { id: "WPU01830161", name: "PPI Farm Products: Sunflower", tags: ["substitutes", "crush"] },
  { id: "WPU01830171", name: "PPI Farm Products: Canola", tags: ["substitutes", "crush", "biofuel"] },
];

// =============================================================================
// FRED SERIES → TABLE ROUTING
// =============================================================================
// Routes FRED series to the correct econ.* table based on series type.
// Default: rates_1d for interest rates and anything unmapped.

const FRED_TABLE_MAP: Record<string, string> = {
  // Inflation (monthly) → econ.inflation_1d
  CPIAUCSL: "econ.inflation_1d",
  CPILFESL: "econ.inflation_1d",
  PCEPI: "econ.inflation_1d",
  PCEPILFE: "econ.inflation_1d",
  PPIACO: "econ.inflation_1d",
  PPIFIS: "econ.inflation_1d",  // Replaced PPIFGS (discontinued 2015)
  // Inflation expectations (DAILY) → econ.inflation_1d
  T5YIE: "econ.inflation_1d",
  T10YIE: "econ.inflation_1d",
  T5YIFR: "econ.inflation_1d",
  // TIPS real yields (DAILY) → econ.inflation_1d
  DFII5: "econ.inflation_1d",
  DFII7: "econ.inflation_1d",
  DFII10: "econ.inflation_1d",
  DFII20: "econ.inflation_1d",
  DFII30: "econ.inflation_1d",

  // Labor → econ.labor_1d
  UNRATE: "econ.labor_1d",
  PAYEMS: "econ.labor_1d",
  MANEMP: "econ.labor_1d",
  ICSA: "econ.labor_1d",
  CCSA: "econ.labor_1d",

  // Activity → econ.activity_1d (GDP, production, housing, trade, consumption)
  GDP: "econ.activity_1d",
  GDPC1: "econ.activity_1d",
  INDPRO: "econ.activity_1d",
  HOUST: "econ.activity_1d",
  PERMIT: "econ.activity_1d",
  RSXFS: "econ.activity_1d",
  PCE: "econ.activity_1d",
  UMCSENT: "econ.activity_1d",
  FRGSHPUSM649NCIS: "econ.activity_1d",
  BOPGSTB: "econ.activity_1d",
  EXPGS: "econ.activity_1d",
  IMPGS: "econ.activity_1d",
  BUSLOANS: "econ.activity_1d",
  // China economic data
  CHNCPIALLMINMEI: "econ.activity_1d",
  CHNPRINTO01IXPYM: "econ.activity_1d",
  CHNGDPNQDSMEI: "econ.activity_1d",
  CHNMAINLANDTPU: "econ.activity_1d",
  XTEXVA01CNM667S: "econ.activity_1d",
  XTIMVA01CNM667S: "econ.activity_1d",
  IMPCH: "econ.activity_1d",
  B235RC1Q027SBEA: "econ.activity_1d",

  // Vol Indices → econ.vol_indices_1d
  VIXCLS: "econ.vol_indices_1d",
  VXVCLS: "econ.vol_indices_1d", // VIX3M (3-month VIX)
  OVXCLS: "econ.vol_indices_1d",
  // Financial stress (weekly) - STLFSI/TEDRATE discontinued, using replacements
  STLFSI4: "econ.vol_indices_1d",
  NFCI: "econ.vol_indices_1d",
  ANFCI: "econ.vol_indices_1d",
  // Credit spreads (daily) - better than TED spread
  BAMLH0A0HYM2: "econ.vol_indices_1d",
  BAMLC0A0CM: "econ.vol_indices_1d",
  GVZCLS: "econ.vol_indices_1d",
  SP500: "econ.vol_indices_1d",
  NASDAQCOM: "econ.vol_indices_1d",
  USEPUINDXD: "econ.vol_indices_1d",
  USEPUINDXM: "econ.vol_indices_1d",
  EPUTRADE: "econ.vol_indices_1d",
  EMVTRADEPOLEMV: "econ.vol_indices_1d",

  // Commodities → econ.commodities_1d
  DCOILWTICO: "econ.commodities_1d",
  DCOILBRENTEU: "econ.commodities_1d",
  DHHNGSP: "econ.commodities_1d",
  DHOILNYH: "econ.commodities_1d",
  PNGASEUUSDM: "econ.commodities_1d",
  DDFUELUSGULF: "econ.commodities_1d",
  DGASUSGULF: "econ.commodities_1d",
  DJFUELUSGULF: "econ.commodities_1d",
  DPROPANEMBTX: "econ.commodities_1d",
  WPU057303: "econ.commodities_1d",
  PCU32411032411012: "econ.commodities_1d",
  APU000074714: "econ.commodities_1d",
  GASREGW: "econ.commodities_1d",
  GASDESW: "econ.commodities_1d",
  WPU06140341: "econ.commodities_1d",
  PSOILUSDM: "econ.commodities_1d",
  PSOYBUSDM: "econ.commodities_1d",
  PCU311224311224: "econ.commodities_1d",
  PMAIZMTUSDM: "econ.commodities_1d",
  PWHEAMTUSDM: "econ.commodities_1d",
  PBARLUSDM: "econ.commodities_1d",
  PPOILUSDM: "econ.commodities_1d",
  PROILUSDM: "econ.commodities_1d",
  PCOPPUSDM: "econ.commodities_1d",
  PRICENPQUSDM: "econ.commodities_1d",
  PSUNOUSDM: "econ.commodities_1d",
  POLVOILUSDM: "econ.commodities_1d",
  PSUGAISAUSDM: "econ.commodities_1d",
  WPU01830161: "econ.commodities_1d",
  WPU01830171: "econ.commodities_1d",

  // Money → econ.money_1d
  M2SL: "econ.money_1d",
  WALCL: "econ.money_1d",
  BOGMBASE: "econ.money_1d",
  WRESBAL: "econ.money_1d",
  RRPONTSYD: "econ.money_1d",
  TOTRESNS: "econ.money_1d",
  MYAGM2CNM189N: "econ.money_1d",
  IR3TIB01CNM156N: "econ.money_1d",
};

/**
 * Get target table for a FRED series.
 * Default: econ.rates_1d for interest rates and unmapped series.
 */
function getTargetTable(seriesId: string): string {
  return FRED_TABLE_MAP[seriesId] || "econ.rates_1d";
}

const DEFAULT_FRED_RATE_LIMIT_MS = 500;
const DEFAULT_FRED_FETCH_TIMEOUT_MS = 15000;
const DEFAULT_FRED_FETCH_RETRIES = 2;
const DEFAULT_FRED_FETCH_BACKOFF_MS = 750;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const FRED_SEGMENT_CONFIGS: Record<string, FredSegmentConfig> = {
  fed: {
    segment: "fed",
    id: "fred-daily-fed",
    jobName: "fred-daily-fed",
    displayName: "FRED Daily - Fed",
    cron: "0 */8 * * *", // Every 8 hours (0:00, 8:00, 16:00 UTC)
    series: FRED_FED_SERIES,
    rateLimitMs: 500,
    fetchTimeoutMs: 15000,
    fetchRetries: 2,
  },
  fx: {
    segment: "fx",
    id: "fred-daily-fx",
    jobName: "fred-daily-fx",
    displayName: "FRED Daily - FX",
    cron: "5 */8 * * *", // Every 8 hours at :05
    series: FRED_FX_SERIES,
    rateLimitMs: 500,
    fetchTimeoutMs: 15000,
    fetchRetries: 2,
  },
  energy: {
    segment: "energy",
    id: "fred-daily-energy",
    jobName: "fred-daily-energy",
    displayName: "FRED Daily - Energy",
    cron: "10 */8 * * *", // Every 8 hours at :10
    series: FRED_ENERGY_SERIES,
    rateLimitMs: 450,
    fetchTimeoutMs: 12000,
    fetchRetries: 2,
  },
  biofuel: {
    segment: "biofuel",
    id: "fred-daily-biofuel",
    jobName: "fred-daily-biofuel",
    displayName: "FRED Daily - Biofuel",
    cron: "15 */8 * * *", // Every 8 hours at :15
    series: FRED_BIOFUEL_SERIES,
    rateLimitMs: 350,
    fetchTimeoutMs: 10000,
    fetchRetries: 2,
  },
  crush: {
    segment: "crush",
    id: "fred-daily-crush",
    jobName: "fred-daily-crush",
    displayName: "FRED Daily - Crush",
    cron: "20 */8 * * *", // Every 8 hours at :20
    series: FRED_CRUSH_SERIES,
    rateLimitMs: 450,
    fetchTimeoutMs: 12000,
    fetchRetries: 2,
  },
  palm: {
    segment: "palm",
    id: "fred-daily-palm",
    jobName: "fred-daily-palm",
    displayName: "FRED Daily - Palm",
    cron: "25 */8 * * *", // Every 8 hours at :25
    series: FRED_PALM_SERIES,
    rateLimitMs: 350,
    fetchTimeoutMs: 10000,
    fetchRetries: 2,
  },
  volatility: {
    segment: "volatility",
    id: "fred-daily-volatility",
    jobName: "fred-daily-volatility",
    displayName: "FRED Daily - Volatility",
    cron: "30 */8 * * *", // Every 8 hours at :30
    series: FRED_VOLATILITY_SERIES,
    rateLimitMs: 400,
    fetchTimeoutMs: 12000,
    fetchRetries: 2,
  },
  trump_effect: {
    segment: "trump_effect",
    id: "fred-daily-trump-effect",
    jobName: "fred-daily-trump-effect",
    displayName: "FRED Daily - Trump Effect",
    cron: "35 */8 * * *", // Every 8 hours at :35
    series: FRED_TRUMP_EFFECT_SERIES,
    rateLimitMs: 400,
    fetchTimeoutMs: 10000,
    fetchRetries: 2,
  },
  china: {
    segment: "china",
    id: "fred-daily-china",
    jobName: "fred-daily-china",
    displayName: "FRED Daily - China",
    cron: "40 */8 * * *", // Every 8 hours at :40
    series: FRED_CHINA_SERIES,
    rateLimitMs: 400,
    fetchTimeoutMs: 12000,
    fetchRetries: 2,
  },
  general: {
    segment: "general",
    id: "fred-daily-general",
    jobName: "fred-daily-general",
    displayName: "FRED Daily - General",
    cron: "45 */8 * * *", // Every 8 hours at :45
    series: FRED_GENERAL_SERIES,
    rateLimitMs: 350,
    fetchTimeoutMs: 10000,
    fetchRetries: 2,
  },
};

// =============================================================================
// BRONZE HELPER FUNCTIONS
// =============================================================================

/**
 * Compute SHA256 hash of observation payload for idempotency
 */
function computeRowHash(seriesId: string, date: string, value: number): string {
  const payload = `${seriesId}|${date}|${value}`;
  return createHash("sha256").update(payload).digest("hex");
}

/**
 * Create a new ingest run record
 */
async function createIngestRun(client: PoolClient, jobName: string): Promise<string> {
  const result = await client.query(
    `INSERT INTO ops.ingest_run (job_name, status, started_at)
     VALUES ($1, 'running', NOW())
     RETURNING id`,
    [jobName]
  );
  return result.rows[0].id;
}

/**
 * Update ingest run with final counts
 */
async function updateIngestRun(
  client: PoolClient,
  runId: string,
  status: string,
  rowsAttempted: number,
  rowsInserted: number,
  rowsSkipped: number,
  rowsQuarantined: number,
  errorMessage?: string
): Promise<void> {
  await client.query(
    `UPDATE ops.ingest_run
     SET status = $2,
         completed_at = NOW(),
         rows_attempted = $3,
         rows_inserted = $4,
         rows_skipped = $5,
         rows_quarantined = $6,
         error_message = $7
     WHERE id = $1`,
    [runId, status, rowsAttempted, rowsInserted, rowsSkipped, rowsQuarantined, errorMessage]
  );
}

/**
 * Quarantine an invalid record
 */
async function quarantineRecord(
  client: PoolClient,
  runId: string,
  sourceTable: string,
  payload: object,
  errors: string[],
  severity: string = "error"
): Promise<void> {
  await client.query(
    `INSERT INTO ops.quarantined_record 
       (ingest_run_id, source_table, raw_payload, validation_errors, severity)
     VALUES ($1, $2, $3, $4, $5)`,
    [runId, sourceTable, JSON.stringify(payload), errors, severity]
  );
}

/**
 * Check if row hash already exists in database
 */
async function hashExists(client: PoolClient, rowHash: string, targetTable: string): Promise<boolean> {
  const result = await client.query(
    `SELECT 1 FROM ${targetTable} WHERE row_hash = $1 LIMIT 1`,
    [rowHash]
  );
  return result.rows.length > 0;
}

// =============================================================================
// FRED API FETCH
// =============================================================================

interface FredObservation {
  date: string;
  value: string;
}

interface FredApiResponse {
  observations?: FredObservation[];
}

interface FredFetchOptions {
  timeoutMs: number;
  retries: number;
  backoffMs: number;
}

type FredFetchResult =
  | { status: "ok"; observation: FredObservation }
  | { status: "no_data" }
  | { status: "not_found" };

function isRetryableStatus(status: number): boolean {
  return status === 429 || (status >= 500 && status <= 599);
}

function isNotFoundResponse(status: number, bodyText: string): boolean {
  if (status === 404) return true;
  if (status !== 400) return false;
  const lowered = bodyText.toLowerCase();
  return lowered.includes("series") && lowered.includes("not");
}

function getRetryDelayMs(retryAfter: string | null, attempt: number, baseBackoffMs: number): number {
  const retryAfterSeconds = retryAfter ? Number(retryAfter) : Number.NaN;
  const baseDelay = Number.isFinite(retryAfterSeconds)
    ? retryAfterSeconds * 1000
    : baseBackoffMs * Math.pow(2, attempt);
  const jitter = Math.floor(Math.random() * 250);
  return baseDelay + jitter;
}

/**
 * Fetch latest observation from FRED API
 */
async function fetchFredSeries(
  seriesId: string,
  apiKey: string,
  options: FredFetchOptions
): Promise<FredFetchResult> {
  const url = `https://api.stlouisfed.org/fred/series/observations?series_id=${seriesId}&api_key=${apiKey}&file_type=json&sort_order=desc&limit=5`;
  let attempt = 0;

  while (true) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), options.timeoutMs);

    try {
      const response = await fetch(url, { signal: controller.signal });
      const bodyText = await response.text();

      if (!response.ok) {
        if (isNotFoundResponse(response.status, bodyText)) {
          return { status: "not_found" };
        }

        if (isRetryableStatus(response.status) && attempt < options.retries) {
          const delayMs = getRetryDelayMs(
            response.headers.get("retry-after"),
            attempt,
            options.backoffMs
          );
          attempt += 1;
          await sleep(delayMs);
          continue;
        }

        throw new Error(`FRED API error: ${response.status} ${response.statusText}`);
      }

      if (!bodyText) {
        return { status: "no_data" };
      }

      let json: FredApiResponse;
      try {
        json = JSON.parse(bodyText) as FredApiResponse;
      } catch (error) {
        throw new Error(
          `FRED API invalid JSON: ${error instanceof Error ? error.message : String(error)}`
        );
      }

      const observations = json.observations || [];

      // Find first valid observation (skip "." values)
      for (const obs of observations) {
        if (obs.value !== "." && obs.value !== "") {
          return { status: "ok", observation: obs };
        }
      }

      return { status: "no_data" };
    } catch (error) {
      const isAbort = error instanceof Error && error.name === "AbortError";
      if ((isAbort || error instanceof TypeError) && attempt < options.retries) {
        const delayMs = getRetryDelayMs(null, attempt, options.backoffMs);
        attempt += 1;
        await sleep(delayMs);
        continue;
      }
      throw error;
    } finally {
      clearTimeout(timeout);
    }
  }
}

// =============================================================================
// SEGMENTED INGEST HELPERS
// =============================================================================

async function ingestFredSegment(
  client: PoolClient,
  runId: string,
  apiKey: string,
  seriesList: FredSeriesConfig[],
  options: FredFetchOptions & { rateLimitMs: number }
): Promise<FredSegmentSummary> {
  const results: FredIngestResult[] = [];
  let attempted = 0;
  let inserted = 0;
  let skipped = 0;
  let quarantined = 0;

  for (const series of seriesList) {
    attempted++;
    const targetTable = getTargetTable(series.id);

    try {
      const fetchResult = await fetchFredSeries(series.id, apiKey, options);

      if (fetchResult.status === "not_found") {
        results.push({ series: series.id, status: "not_found" });
        skipped++;
        continue;
      }

      if (fetchResult.status === "no_data") {
        results.push({ series: series.id, status: "no_data" });
        skipped++;
        continue;
      }

      const obs = fetchResult.observation;
      const value = parseFloat(obs.value);

      if (isNaN(value)) {
        await quarantineRecord(
          client,
          runId,
          targetTable,
          { series_id: series.id, date: obs.date, raw_value: obs.value },
          ["Invalid numeric value: " + obs.value],
          "error"
        );
        results.push({ series: series.id, status: "quarantined_invalid_value" });
        quarantined++;
        continue;
      }

      const rowHash = computeRowHash(series.id, obs.date, value);

      if (await hashExists(client, rowHash, targetTable)) {
        results.push({ series: series.id, status: "skipped_duplicate" });
        skipped++;
        continue;
      }

      // Use simplified column set that matches actual econ.* table structure
      await client.query(
        `INSERT INTO ${targetTable} (
           series_id,
           value,
           event_date,
           knowledge_time,
           source,
           row_hash
         ) VALUES ($1, $2, $3, NOW(), $4, $5)
         ON CONFLICT (series_id, event_date) DO UPDATE SET
           value = EXCLUDED.value,
           knowledge_time = NOW(),
           source = EXCLUDED.source`,
        [
          series.id,
          value,
          obs.date,
          "fred_api",
          rowHash,
        ]
      );

      results.push({
        series: series.id,
        status: "inserted",
        value,
        tags: series.tags,
      });
      inserted++;

    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error);

      await quarantineRecord(
        client,
        runId,
        targetTable,
        { series_id: series.id, error: errorMsg },
        ["Fetch/insert error: " + errorMsg],
        "error"
      );

      results.push({ series: series.id, status: "error" });
      quarantined++;
    }

    await sleep(options.rateLimitMs);
  }

  return {
    results,
    attempted,
    inserted,
    skipped,
    quarantined,
  };
}

// =============================================================================
// MAIN INNGEST FUNCTIONS (SEGMENTED)
// =============================================================================

function createFredSegmentJob(config: FredSegmentConfig) {
  return inngest.createFunction(
    {
      id: config.id,
      name: config.displayName,
      retries: config.retries ?? DEFAULT_JOB_RETRIES,
    },
    { cron: config.cron },
    async ({ step, logger }) => {
      const apiKey = process.env.FRED_API_KEY;
      if (!apiKey) {
        return { status: "error", message: "FRED_API_KEY not configured" };
      }

      const client = await pool.connect();
      let runId: string | null = null;

      let rowsAttempted = 0;
      let rowsInserted = 0;
      let rowsSkipped = 0;
      let rowsQuarantined = 0;
      let results: FredIngestResult[] = [];

      try {
        runId = await step.run("create-ingest-run", async () => {
          return await createIngestRun(client, config.jobName);
        });

        logger.info(`Started ingest run: ${runId} (${config.segment})`);

        const segmentSummary = await step.run(`fetch-${config.segment}`, async () => {
          const rateLimitMs = config.rateLimitMs ?? DEFAULT_FRED_RATE_LIMIT_MS;
          const timeoutMs = config.fetchTimeoutMs ?? DEFAULT_FRED_FETCH_TIMEOUT_MS;
          const retries = config.fetchRetries ?? DEFAULT_FRED_FETCH_RETRIES;
          const backoffMs = config.fetchBackoffMs ?? DEFAULT_FRED_FETCH_BACKOFF_MS;
          return await ingestFredSegment(
            client,
            runId!,
            apiKey,
            config.series,
            {
              rateLimitMs,
              timeoutMs,
              retries,
              backoffMs,
            }
          );
        });

        rowsAttempted = segmentSummary.attempted;
        rowsInserted = segmentSummary.inserted;
        rowsSkipped = segmentSummary.skipped;
        rowsQuarantined = segmentSummary.quarantined;
        results = segmentSummary.results;

        await step.run("complete-ingest-run", async () => {
          await updateIngestRun(
            client,
            runId!,
            "success",
            rowsAttempted,
            rowsInserted,
            rowsSkipped,
            rowsQuarantined
          );
        });

        logger.info(`Completed ingest run: ${runId}`);
        logger.info(`  Attempted: ${rowsAttempted}`);
        logger.info(`  Inserted: ${rowsInserted}`);
        logger.info(`  Skipped: ${rowsSkipped}`);
        logger.info(`  Quarantined: ${rowsQuarantined}`);

        return {
          status: "success",
          runId,
          segment: config.segment,
          date: new Date().toISOString().split("T")[0],
          summary: {
            attempted: rowsAttempted,
            inserted: rowsInserted,
            skipped: rowsSkipped,
            quarantined: rowsQuarantined,
          },
          results,
        };
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error);

        if (runId) {
          await updateIngestRun(
            client,
            runId,
            "failed",
            rowsAttempted,
            rowsInserted,
            rowsSkipped,
            rowsQuarantined,
            errorMsg
          );
        }

        logger.error(`Ingest run failed: ${errorMsg}`);

        return {
          status: "failed",
          runId,
          segment: config.segment,
          error: errorMsg,
          summary: {
            attempted: rowsAttempted,
            inserted: rowsInserted,
            skipped: rowsSkipped,
            quarantined: rowsQuarantined,
          },
        };
      } finally {
        client.release();
      }
    }
  );
}

export const fredDailyFed = createFredSegmentJob(FRED_SEGMENT_CONFIGS.fed);
export const fredDailyFx = createFredSegmentJob(FRED_SEGMENT_CONFIGS.fx);
export const fredDailyEnergy = createFredSegmentJob(FRED_SEGMENT_CONFIGS.energy);
export const fredDailyBiofuel = createFredSegmentJob(FRED_SEGMENT_CONFIGS.biofuel);
export const fredDailyCrush = createFredSegmentJob(FRED_SEGMENT_CONFIGS.crush);
export const fredDailyPalm = createFredSegmentJob(FRED_SEGMENT_CONFIGS.palm);
export const fredDailyVolatility = createFredSegmentJob(FRED_SEGMENT_CONFIGS.volatility);
export const fredDailyTrumpEffect = createFredSegmentJob(FRED_SEGMENT_CONFIGS.trump_effect);
export const fredDailyChina = createFredSegmentJob(FRED_SEGMENT_CONFIGS.china);
export const fredDailyGeneral = createFredSegmentJob(FRED_SEGMENT_CONFIGS.general);
