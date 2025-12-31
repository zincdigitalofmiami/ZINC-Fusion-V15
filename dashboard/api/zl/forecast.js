import pg from 'pg';

const pool = new pg.Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false }
});

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET');

  const horizon = parseInt(req.query.horizon) || 21;

  try {
    // First try to get real forecast data from model.forecast_quantiles
    const forecastResult = await pool.query(`
      SELECT target_date, p10::float, p50::float, p90::float
      FROM model.forecast_quantiles
      WHERE forecast_date = (SELECT MAX(forecast_date) FROM model.forecast_quantiles)
      ORDER BY target_date
      LIMIT $1
    `, [horizon]);

    if (forecastResult.rows.length > 0) {
      const p10 = forecastResult.rows.map(r => ({
        time: r.target_date.toISOString().split('T')[0],
        value: r.p10
      }));
      const p50 = forecastResult.rows.map(r => ({
        time: r.target_date.toISOString().split('T')[0],
        value: r.p50
      }));
      const p90 = forecastResult.rows.map(r => ({
        time: r.target_date.toISOString().split('T')[0],
        value: r.p90
      }));

      return res.status(200).json({
        success: true,
        p10, p50, p90,
        cone: {
          p10: p10[p10.length - 1]?.value.toFixed(2),
          p90: p90[p90.length - 1]?.value.toFixed(2)
        },
        source: 'model'
      });
    }

    // Fallback: Generate forecast cone from historical volatility
    const priceResult = await pool.query(`
      SELECT as_of_date, close::float
      FROM raw.market_futures_1d
      WHERE symbol = 'ZL'
      ORDER BY as_of_date DESC
      LIMIT 252
    `);

    if (priceResult.rows.length < 30) {
      return res.status(404).json({ success: false, error: 'Insufficient price data' });
    }

    const prices = priceResult.rows.reverse();
    const lastPrice = prices[prices.length - 1].close;
    const lastDate = new Date(prices[prices.length - 1].as_of_date);

    // Calculate historical volatility (annualized)
    const returns = [];
    for (let i = 1; i < prices.length; i++) {
      const ret = Math.log(prices[i].close / prices[i - 1].close);
      returns.push(ret);
    }
    const meanReturn = returns.reduce((a, b) => a + b, 0) / returns.length;
    const variance = returns.reduce((a, b) => a + Math.pow(b - meanReturn, 2), 0) / returns.length;
    const dailyVol = Math.sqrt(variance);
    const annualizedVol = dailyVol * Math.sqrt(252);

    // Calculate drift from recent trend (30-day)
    const recentPrices = prices.slice(-30);
    const drift = (recentPrices[recentPrices.length - 1].close - recentPrices[0].close) / recentPrices[0].close / 30;

    // Generate forecast cone
    const p10 = [], p50 = [], p90 = [];

    for (let i = 1; i <= horizon; i++) {
      const futureDate = new Date(lastDate);
      futureDate.setDate(futureDate.getDate() + i);
      const dateStr = futureDate.toISOString().split('T')[0];

      // Geometric Brownian Motion parameters
      const t = i / 252; // Time in years
      const volTerm = annualizedVol * Math.sqrt(t);
      const driftTerm = drift * i;

      // P10, P50, P90 using normal quantiles (-1.28, 0, +1.28)
      p10.push({
        time: dateStr,
        value: lastPrice * Math.exp(driftTerm - 1.28 * volTerm)
      });
      p50.push({
        time: dateStr,
        value: lastPrice * Math.exp(driftTerm)
      });
      p90.push({
        time: dateStr,
        value: lastPrice * Math.exp(driftTerm + 1.28 * volTerm)
      });
    }

    res.status(200).json({
      success: true,
      p10, p50, p90,
      cone: {
        p10: p10[p10.length - 1].value.toFixed(2),
        p90: p90[p90.length - 1].value.toFixed(2)
      },
      volatility: {
        daily: (dailyVol * 100).toFixed(2) + '%',
        annualized: (annualizedVol * 100).toFixed(1) + '%'
      },
      source: 'historical_vol'
    });
  } catch (error) {
    console.error('Forecast API error:', error);
    res.status(500).json({ success: false, error: error.message });
  }
}
