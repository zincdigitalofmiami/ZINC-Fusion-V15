// DEPRECATED — features.elite_1d has been consolidated into mkt.futures_1d.
// Migration is complete. This script is retained for historical reference only. DO NOT RUN.

const { Pool } = require('pg');
require('dotenv').config({ path: require('path').join(__dirname, '../frontend/.env.local') });

async function migrate() {
  const pool = new Pool({
    connectionString: process.env.DATABASE_URL,
    ssl: { rejectUnauthorized: false }
  });

  console.log('\n🔄 MIGRATING ALL ELITE INDICATORS TO mkt.futures_1d\n');
  console.log('='.repeat(70) + '\n');

  const symbols = await pool.query('SELECT DISTINCT symbol FROM features.elite_1d ORDER BY symbol');
  
  console.log(`Migrating ${symbols.rowCount} symbols...\n`);

  let total = 0;

  for (const row of symbols.rows) {
    const symbol = row.symbol;
    
    const result = await pool.query(`
      UPDATE mkt.futures_1d f
      SET 
        hurst_exponent = e.hurst_exponent,
        hurst_regime = e.hurst_regime,
        connors_rsi = e.connors_rsi,
        fisher_transform = e.fisher_transform,
        fisher_signal = e.fisher_signal,
        mcginley_dynamic = e.mcginley_dynamic,
        ttm_squeeze_on = e.ttm_squeeze_on,
        ttm_squeeze_momentum = e.ttm_squeeze_momentum,
        schaff_trend_cycle = e.schaff_trend_cycle,
        rvi = e.rvi,
        rvi_signal = e.rvi_signal,
        elder_force_index = e.elder_force_index,
        kama_10 = e.kama_10,
        hma_20 = e.hma_20,
        alma_50 = e.alma_50,
        rsi_2 = e.rsi_2,
        rsi_14 = e.rsi_14,
        cumulative_rsi = e.cumulative_rsi,
        macd = e.macd,
        macd_signal = e.macd_signal,
        macd_histogram = e.macd_histogram,
        cci_14 = e.cci_14,
        cci_50 = e.cci_50,
        atr_10 = e.atr_10,
        atr_50 = e.atr_50,
        atr_ratio = e.atr_ratio,
        garman_klass_vol = e.garman_klass_vol,
        yang_zhang_vol = e.yang_zhang_vol,
        bb_percent_b = e.bb_percent_b,
        cmf_21 = e.cmf_21,
        volume_zscore = e.volume_zscore,
        unusual_volume = e.unusual_volume,
        returns_1d = e.returns_1d,
        log_returns_1d = e.log_returns_1d,
        range_pct = e.range_pct
      FROM features.elite_1d e
      WHERE f.symbol = e.symbol 
        AND f.event_date = e.trade_date
        AND f.symbol = $1
    `, [symbol]);
    
    total += result.rowCount;
    console.log(`   ✅ ${symbol.padEnd(10)} ${result.rowCount.toString().padStart(6)} rows`);
  }

  console.log('\n' + '='.repeat(70));
  console.log(`🎉 COMPLETE: ${total.toLocaleString()} total rows updated`);
  console.log('='.repeat(70));
  console.log('\nAll elite indicators now in mkt.futures_1d');
  console.log('Training can query ONE table with everything included');
  console.log('='.repeat(70) + '\n');

  await pool.end();
}

migrate().catch(e => console.error('Error:', e));
