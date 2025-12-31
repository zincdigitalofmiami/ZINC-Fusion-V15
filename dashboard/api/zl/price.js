import pg from 'pg';

const pool = new pg.Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false }
});

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET');

  const days = parseInt(req.query.days) || 90;

  try {
    const result = await pool.query(`
      SELECT
        as_of_date as time,
        open::float,
        high::float,
        low::float,
        close::float,
        volume::int
      FROM raw.market_futures_1d
      WHERE symbol = 'ZL'
      ORDER BY as_of_date DESC
      LIMIT $1
    `, [days]);

    if (result.rows.length === 0) {
      return res.status(404).json({ success: false, error: 'No ZL price data found' });
    }

    // Format for LightweightCharts - reverse to chronological order
    const series = result.rows.reverse().map(row => ({
      time: row.time.toISOString().split('T')[0],
      open: row.open,
      high: row.high,
      low: row.low,
      close: row.close,
      volume: row.volume
    }));

    res.status(200).json({
      success: true,
      series,
      latest: series[series.length - 1],
      count: series.length
    });
  } catch (error) {
    console.error('Price API error:', error);
    res.status(500).json({ success: false, error: error.message });
  }
}
