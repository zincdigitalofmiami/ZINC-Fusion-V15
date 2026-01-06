#!/bin/bash
# =============================================================================
# ZINC-FUSION Social Media Intelligence - cURL Scripts
# =============================================================================
# Production-ready cURL commands for ScrapeCreators API
#
# USAGE:
#   export SCRAPECREATORS_API_KEY="your-api-key"
#   ./scripts/curl_social_scrape.sh [tier]
#
# TIERS:
#   high        - Trump, USTR, China (market-moving)
#   regulatory  - Government agencies, exchanges
#   discovery   - Industry, associations, media
#   all         - Everything (default)
#
# OUTPUT:
#   JSON files saved to data/social_scrapes/
# =============================================================================

set -e

# Check API key
if [ -z "$SCRAPECREATORS_API_KEY" ]; then
    echo "ERROR: SCRAPECREATORS_API_KEY not set"
    echo "Run: export SCRAPECREATORS_API_KEY='your-key'"
    exit 1
fi

SC_API_KEY="$SCRAPECREATORS_API_KEY"
SC_BASE="https://api.scrapecreators.com/v2"
TIER="${1:-all}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="data/social_scrapes/${TIMESTAMP}"

mkdir -p "$OUTPUT_DIR/twitter" "$OUTPUT_DIR/truthsocial" "$OUTPUT_DIR/facebook" "$OUTPUT_DIR/linkedin"

echo "=============================================="
echo "SOCIAL MEDIA INTELLIGENCE SCRAPER"
echo "=============================================="
echo "Tier: $TIER"
echo "Output: $OUTPUT_DIR"
echo ""

# Rate limiting helper
rate_limit() {
    sleep 2
}

# =============================================================================
# HIGH-ALPHA TIER - Market-Moving Sources
# =============================================================================

scrape_high_alpha() {
    echo ">>> HIGH-ALPHA TIER: Trump, USTR, China <<<"
    echo ""

    # Trump Administration
    for handle in realDonaldTrump DonaldJTrumpJr EricTrump POTUS VP WhiteHouse; do
        echo "  Twitter: @${handle}"
        curl -sS -H "x-api-key: $SC_API_KEY" \
            "${SC_BASE}/twitter/user/tweets?username=${handle}&limit=20" \
            > "$OUTPUT_DIR/twitter/${handle}.json" 2>/dev/null || echo "    (failed)"
        rate_limit
    done

    # Trade Policy
    for handle in USTR USTreasury SecYellen; do
        echo "  Twitter: @${handle}"
        curl -sS -H "x-api-key: $SC_API_KEY" \
            "${SC_BASE}/twitter/user/tweets?username=${handle}&limit=20" \
            > "$OUTPUT_DIR/twitter/${handle}.json" 2>/dev/null || echo "    (failed)"
        rate_limit
    done

    # Immigration/Border
    for handle in ICEgov CBP DHSgov; do
        echo "  Twitter: @${handle}"
        curl -sS -H "x-api-key: $SC_API_KEY" \
            "${SC_BASE}/twitter/user/tweets?username=${handle}&limit=20" \
            > "$OUTPUT_DIR/twitter/${handle}.json" 2>/dev/null || echo "    (failed)"
        rate_limit
    done

    # China Trade
    for handle in MOFCOMChina GACC_China cofcointl sinochem_news sinograin_china MFA_China ChinaEmbinUS; do
        echo "  Twitter: @${handle}"
        curl -sS -H "x-api-key: $SC_API_KEY" \
            "${SC_BASE}/twitter/user/tweets?username=${handle}&limit=20" \
            > "$OUTPUT_DIR/twitter/${handle}.json" 2>/dev/null || echo "    (failed)"
        rate_limit
    done

    # Truth Social
    echo "  Truth Social: @realDonaldTrump"
    curl -sS -H "x-api-key: $SC_API_KEY" \
        "${SC_BASE}/truthsocial/user/posts?username=realDonaldTrump&limit=20" \
        > "$OUTPUT_DIR/truthsocial/realDonaldTrump.json" 2>/dev/null || echo "    (failed)"
    rate_limit

    echo ""
}

# =============================================================================
# REGULATORY TIER - Government & Exchanges
# =============================================================================

scrape_regulatory() {
    echo ">>> REGULATORY TIER: Government, Exchanges <<<"
    echo ""

    # US Agriculture
    for handle in USDA SecVilsack USDA_NASS; do
        echo "  Twitter: @${handle}"
        curl -sS -H "x-api-key: $SC_API_KEY" \
            "${SC_BASE}/twitter/user/tweets?username=${handle}&limit=20" \
            > "$OUTPUT_DIR/twitter/${handle}.json" 2>/dev/null || echo "    (failed)"
        rate_limit
    done

    # Biofuel/Energy
    for handle in EPA EnergyGov CleanFuelsDA BiodieselNow EthanolRFA CARB; do
        echo "  Twitter: @${handle}"
        curl -sS -H "x-api-key: $SC_API_KEY" \
            "${SC_BASE}/twitter/user/tweets?username=${handle}&limit=20" \
            > "$OUTPUT_DIR/twitter/${handle}.json" 2>/dev/null || echo "    (failed)"
        rate_limit
    done

    # Exchanges
    for handle in CMEGroup ICE_Markets nasdaq CBOTExchange; do
        echo "  Twitter: @${handle}"
        curl -sS -H "x-api-key: $SC_API_KEY" \
            "${SC_BASE}/twitter/user/tweets?username=${handle}&limit=20" \
            > "$OUTPUT_DIR/twitter/${handle}.json" 2>/dev/null || echo "    (failed)"
        rate_limit
    done

    # Congress Ag
    for handle in SenateAg HouseAg ChairmanThompson SenBooker RepAustin SenJoniErnst ChuckGrassley SenAmyKlobuchar SenatorFischer RepFeenstra; do
        echo "  Twitter: @${handle}"
        curl -sS -H "x-api-key: $SC_API_KEY" \
            "${SC_BASE}/twitter/user/tweets?username=${handle}&limit=20" \
            > "$OUTPUT_DIR/twitter/${handle}.json" 2>/dev/null || echo "    (failed)"
        rate_limit
    done

    # Brazil
    for handle in MinAgricultura abioveoficial AprosojaBrasil conab_oficial anpbrasil ubrabio; do
        echo "  Twitter: @${handle}"
        curl -sS -H "x-api-key: $SC_API_KEY" \
            "${SC_BASE}/twitter/user/tweets?username=${handle}&limit=20" \
            > "$OUTPUT_DIR/twitter/${handle}.json" 2>/dev/null || echo "    (failed)"
        rate_limit
    done

    # Argentina
    for handle in CIARA_CEC ArgentinaGob BCRAmercados MAGyPArgentina INDEC_Argentina CancelleriaArg; do
        echo "  Twitter: @${handle}"
        curl -sS -H "x-api-key: $SC_API_KEY" \
            "${SC_BASE}/twitter/user/tweets?username=${handle}&limit=20" \
            > "$OUTPUT_DIR/twitter/${handle}.json" 2>/dev/null || echo "    (failed)"
        rate_limit
    done

    # Palm Oil
    for handle in mpobmalaysia gapki_id icopalmoil; do
        echo "  Twitter: @${handle}"
        curl -sS -H "x-api-key: $SC_API_KEY" \
            "${SC_BASE}/twitter/user/tweets?username=${handle}&limit=20" \
            > "$OUTPUT_DIR/twitter/${handle}.json" 2>/dev/null || echo "    (failed)"
        rate_limit
    done

    # EU Policy
    for handle in EU_Commission EU_CouncilEU; do
        echo "  Twitter: @${handle}"
        curl -sS -H "x-api-key: $SC_API_KEY" \
            "${SC_BASE}/twitter/user/tweets?username=${handle}&limit=20" \
            > "$OUTPUT_DIR/twitter/${handle}.json" 2>/dev/null || echo "    (failed)"
        rate_limit
    done

    # China Media
    for handle in CCTVNews XinhuaNews PDChina CGTNOfficial ChinaDaily; do
        echo "  Twitter: @${handle}"
        curl -sS -H "x-api-key: $SC_API_KEY" \
            "${SC_BASE}/twitter/user/tweets?username=${handle}&limit=20" \
            > "$OUTPUT_DIR/twitter/${handle}.json" 2>/dev/null || echo "    (failed)"
        rate_limit
    done

    # Analysts
    for handle in kannbwx ArlanFF101 ScottIrwinUIUC SoybeanCorn JavierBlas; do
        echo "  Twitter: @${handle}"
        curl -sS -H "x-api-key: $SC_API_KEY" \
            "${SC_BASE}/twitter/user/tweets?username=${handle}&limit=20" \
            > "$OUTPUT_DIR/twitter/${handle}.json" 2>/dev/null || echo "    (failed)"
        rate_limit
    done

    # Facebook - Institutional
    for profile in USDA EPA AmericanSoybeanAssociation NationalBiodieselBoard CMEGroup; do
        echo "  Facebook: ${profile}"
        curl -sS -H "x-api-key: $SC_API_KEY" \
            "${SC_BASE}/facebook/profile/posts?profile=${profile}&limit=10" \
            > "$OUTPUT_DIR/facebook/${profile}.json" 2>/dev/null || echo "    (failed)"
        sleep 3
    done

    echo ""
}

# =============================================================================
# DISCOVERY TIER - Industry & Associations
# =============================================================================

scrape_discovery() {
    echo ">>> DISCOVERY TIER: Industry, Associations <<<"
    echo ""

    # Commodity Majors
    for handle in ADMCorp BungeGlobal Cargill LouisDreyfus Viterra_Global OilWorld FCStoneGlobal Informa_Agri; do
        echo "  Twitter: @${handle}"
        curl -sS -H "x-api-key: $SC_API_KEY" \
            "${SC_BASE}/twitter/user/tweets?username=${handle}&limit=20" \
            > "$OUTPUT_DIR/twitter/${handle}.json" 2>/dev/null || echo "    (failed)"
        rate_limit
    done

    # Farm Associations
    for handle in FarmBureau NationalCorn ASA_Soybeans NOPA_News NationalGrange NFUnion USGrains USSEC; do
        echo "  Twitter: @${handle}"
        curl -sS -H "x-api-key: $SC_API_KEY" \
            "${SC_BASE}/twitter/user/tweets?username=${handle}&limit=20" \
            > "$OUTPUT_DIR/twitter/${handle}.json" 2>/dev/null || echo "    (failed)"
        rate_limit
    done

    # Ag Media
    for handle in corn_soydigest SuccessfulFarm FarmProgress AgWeb dtnpf canalrural noticiasagri agrolink ruralbr; do
        echo "  Twitter: @${handle}"
        curl -sS -H "x-api-key: $SC_API_KEY" \
            "${SC_BASE}/twitter/user/tweets?username=${handle}&limit=20" \
            > "$OUTPUT_DIR/twitter/${handle}.json" 2>/dev/null || echo "    (failed)"
        rate_limit
    done

    # Weather
    for handle in NOAA NWS NOAAClimate WorldWeather AccuWeather WeatherChannel CommodityWX DroughtGov; do
        echo "  Twitter: @${handle}"
        curl -sS -H "x-api-key: $SC_API_KEY" \
            "${SC_BASE}/twitter/user/tweets?username=${handle}&limit=20" \
            > "$OUTPUT_DIR/twitter/${handle}.json" 2>/dev/null || echo "    (failed)"
        rate_limit
    done

    # Think Tanks
    for handle in Heritage AEI BrookingsInst CatoInstitute EconomicPolicy taxpolicyctr CropLifeAmerica bioenergyassoc GrowthEnergy; do
        echo "  Twitter: @${handle}"
        curl -sS -H "x-api-key: $SC_API_KEY" \
            "${SC_BASE}/twitter/user/tweets?username=${handle}&limit=20" \
            > "$OUTPUT_DIR/twitter/${handle}.json" 2>/dev/null || echo "    (failed)"
        rate_limit
    done

    # Financial Media
    for handle in CNBC BloombergNews Reuters WSJ MarketWatch FT AgFunderNews foodandagtech AgriPulse FarmFutures ProFarmer DowJonesAgNews; do
        echo "  Twitter: @${handle}"
        curl -sS -H "x-api-key: $SC_API_KEY" \
            "${SC_BASE}/twitter/user/tweets?username=${handle}&limit=20" \
            > "$OUTPUT_DIR/twitter/${handle}.json" 2>/dev/null || echo "    (failed)"
        rate_limit
    done

    # Facebook - Industry
    for profile in BungeGlobal CargillInc ADM; do
        echo "  Facebook: ${profile}"
        curl -sS -H "x-api-key: $SC_API_KEY" \
            "${SC_BASE}/facebook/profile/posts?profile=${profile}&limit=10" \
            > "$OUTPUT_DIR/facebook/${profile}.json" 2>/dev/null || echo "    (failed)"
        sleep 3
    done

    # LinkedIn - Corporate
    for company in usda epa adm bunge cargill louis-dreyfus-company cme-group ice-intercontinental-exchange; do
        echo "  LinkedIn: ${company}"
        curl -sS -H "x-api-key: $SC_API_KEY" \
            "${SC_BASE}/linkedin/company/posts?company=${company}&limit=10" \
            > "$OUTPUT_DIR/linkedin/${company}.json" 2>/dev/null || echo "    (failed)"
        sleep 3
    done

    echo ""
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================

case "$TIER" in
    high)
        scrape_high_alpha
        ;;
    regulatory)
        scrape_regulatory
        ;;
    discovery)
        scrape_discovery
        ;;
    all)
        scrape_high_alpha
        scrape_regulatory
        scrape_discovery
        ;;
    *)
        echo "Unknown tier: $TIER"
        echo "Usage: $0 [high|regulatory|discovery|all]"
        exit 1
        ;;
esac

# Summary
echo "=============================================="
echo "SCRAPE COMPLETE"
echo "=============================================="
echo ""
echo "Files saved to: $OUTPUT_DIR"
echo ""
echo "File counts:"
echo "  Twitter:      $(ls -1 $OUTPUT_DIR/twitter/*.json 2>/dev/null | wc -l | tr -d ' ') files"
echo "  Truth Social: $(ls -1 $OUTPUT_DIR/truthsocial/*.json 2>/dev/null | wc -l | tr -d ' ') files"
echo "  Facebook:     $(ls -1 $OUTPUT_DIR/facebook/*.json 2>/dev/null | wc -l | tr -d ' ') files"
echo "  LinkedIn:     $(ls -1 $OUTPUT_DIR/linkedin/*.json 2>/dev/null | wc -l | tr -d ' ') files"
echo ""
echo "Total data size: $(du -sh $OUTPUT_DIR | cut -f1)"
echo ""
echo "To process into database, run:"
echo "  python scripts/scrape_social_intel.py --tier $TIER"
