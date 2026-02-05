/**
 * Migrate elite indicators from features.elite_1d to mkt.futures_1d
 * Batched by symbol to avoid timeout
 */

const { Pool } = require('pg');
require('dotenv').config({ path: require('path').join(__dirname, '../frontend/.env.local') });

async function migrate() {
  const pool = new Pool({
    connectionString: process.env.DATABASE_URL,
    ssl: { rejectUnauthorized: false }
  });

  console.log('\n🔄 MIGRATING ELITE INDICATORS (BATCHED BY SYMBOL)\n');
  console.log('='.repeat(70) + '\n');

  // Get all symbols in features.elite_1d
  const symbols = await pool.query(`
    SELECT DISTINCT symbol, COUNT(*) as rows
    FROM features.elite_1d
    ORDER BY rows DESC
  `);

  console.log(`Processing ${symbols.rowCount} symbols...\n`);

  let totalUpdated = 0;

  for (const { symbol, rows } of symbols.rows) {
    const start = Date.now();
    
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
    
    const elapsed = ((Date.now() - start) / 1000).toFixed(1);
    totalUpdated += result.rowCount;
    
    console.log(`   ✅ ${symbol.padEnd(8)} ${result.rowCount.toString().padStart(5)} rows  (${elapsed}s)`);
  }

  console.log('\n' + '='.repeat(70));
  console.log(`✅ MIGRATION COMPLETE: ${totalUpdated} rows updated`);
  console.log('='.repeat(70) + '\n');

  await pool.end();
}

migrate().catch(e => console.error('Error:', e));
