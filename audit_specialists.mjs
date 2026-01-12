import { config } from 'dotenv';
config();

import { PrismaClient } from './prisma/generated/prisma/index.js';

async function audit() {
  const prisma = new PrismaClient({
    accelerateUrl: process.env.PRISMA_DATABASE_URL
  });
  
  try {
    // Check news_articles_1d specialist tags
    const newsTagStats = await prisma.$queryRaw`
      SELECT 
        unnest(specialist_tags) as specialist,
        COUNT(*)::int as row_count,
        MIN(event_date)::date as earliest,
        MAX(event_date)::date as latest
      FROM raw.news_articles_1d
      WHERE specialist_tags IS NOT NULL AND array_length(specialist_tags, 1) > 0
      GROUP BY 1
      ORDER BY 1
    `;
    console.log('=== NEWS ARTICLES BY SPECIALIST TAG ===');
    console.table(newsTagStats);

    // Check news by bucket_name (legacy)
    const newsBucketStats = await prisma.$queryRaw`
      SELECT 
        bucket_name,
        COUNT(*)::int as row_count,
        MIN(event_date)::date as earliest,
        MAX(event_date)::date as latest
      FROM raw.news_articles_1d
      WHERE bucket_name IS NOT NULL
      GROUP BY 1
      ORDER BY 1
    `;
    console.log('\n=== NEWS ARTICLES BY BUCKET (LEGACY) ===');
    console.table(newsBucketStats);

    // Check CFTC data by symbol
    const cftcStats = await prisma.$queryRaw`
      SELECT 
        symbol,
        COUNT(*)::int as row_count,
        MIN(event_date)::date as earliest,
        MAX(event_date)::date as latest
      FROM raw.cftc_cot_1w
      GROUP BY symbol
      ORDER BY row_count DESC
      LIMIT 20
    `;
    console.log('\n=== CFTC COT (TOP 20 SYMBOLS) ===');
    console.table(cftcStats);

    // Check FRED data
    const fredStats = await prisma.$queryRaw`
      SELECT 
        COUNT(*)::int as row_count,
        COUNT(DISTINCT series_id)::int as series,
        MIN(event_date)::date as earliest,
        MAX(event_date)::date as latest
      FROM raw.fred_observations_1d
    `;
    console.log('\n=== FRED DATA ===');
    console.table(fredStats);

    // Check market futures
    const futuresStats = await prisma.$queryRaw`
      SELECT 
        symbol,
        COUNT(*)::int as row_count,
        MIN(event_date)::date as earliest,
        MAX(event_date)::date as latest
      FROM raw.market_futures_1d
      GROUP BY symbol
      ORDER BY symbol
    `;
    console.log('\n=== MARKET FUTURES 1D ===');
    console.table(futuresStats);

    // Check weather
    const weatherStats = await prisma.$queryRaw`
      SELECT 
        COUNT(*)::int as row_count,
        COUNT(DISTINCT station_id)::int as stations,
        MIN(event_date)::date as earliest,
        MAX(event_date)::date as latest
      FROM raw.weather_noaa_1d
    `;
    console.log('\n=== WEATHER DATA ===');
    console.table(weatherStats);

    // Check EPA RIN
    const rinStats = await prisma.$queryRaw`
      SELECT 
        rin_type,
        COUNT(*)::int as row_count,
        MIN(event_date)::date as earliest,
        MAX(event_date)::date as latest
      FROM raw.epa_rin_prices_1d
      GROUP BY rin_type
      ORDER BY rin_type
    `;
    console.log('\n=== EPA RIN PRICES ===');
    console.table(rinStats);

    // Check FX
    const fxStats = await prisma.$queryRaw`
      SELECT 
        pair,
        COUNT(*)::int as row_count,
        MIN(event_date)::date as earliest,
        MAX(event_date)::date as latest
      FROM raw.fx_spot_1d
      GROUP BY pair
      ORDER BY pair
    `;
    console.log('\n=== FX SPOT ===');
    console.table(fxStats);

    // Check legislation
    const legStats = await prisma.$queryRaw`
      SELECT 
        document_type,
        COUNT(*)::int as row_count,
        MIN(event_date)::date as earliest,
        MAX(event_date)::date as latest
      FROM raw.legislation_federal_register_1d
      GROUP BY document_type
      ORDER BY row_count DESC
    `;
    console.log('\n=== FEDERAL REGISTER ===');
    console.table(legStats);

    // Check USDA export sales
    const exportStats = await prisma.$queryRaw`
      SELECT 
        commodity,
        COUNT(*)::int as row_count,
        MIN(event_date)::date as earliest,
        MAX(event_date)::date as latest
      FROM raw.usda_export_sales_1w
      GROUP BY commodity
      ORDER BY commodity
    `;
    console.log('\n=== USDA EXPORT SALES ===');
    console.table(exportStats);

    // Check USDA WASDE
    const wasdeStats = await prisma.$queryRaw`
      SELECT 
        commodity,
        COUNT(*)::int as row_count,
        MIN(event_date)::date as earliest,
        MAX(event_date)::date as latest
      FROM raw.usda_wasde_1m
      GROUP BY commodity
      ORDER BY row_count DESC
      LIMIT 15
    `;
    console.log('\n=== USDA WASDE (TOP 15) ===');
    console.table(wasdeStats);

    // Check White House actions
    const whStats = await prisma.$queryRaw`
      SELECT 
        action_type,
        COUNT(*)::int as row_count,
        MIN(action_date)::date as earliest,
        MAX(action_date)::date as latest
      FROM raw.whitehouse_actions_event
      GROUP BY action_type
      ORDER BY row_count DESC
    `;
    console.log('\n=== WHITE HOUSE ACTIONS ===');
    console.table(whStats);

    // Yahoo equity
    const yahooStats = await prisma.$queryRaw`
      SELECT 
        symbol,
        COUNT(*)::int as row_count,
        MIN(event_date)::date as earliest,
        MAX(event_date)::date as latest
      FROM raw.yahoo_equity_1d
      GROUP BY symbol
      ORDER BY symbol
    `;
    console.log('\n=== YAHOO EQUITY ===');
    console.table(yahooStats);

  } catch (e) {
    console.error(e);
  } finally {
    await prisma.$disconnect();
  }
}

audit();
