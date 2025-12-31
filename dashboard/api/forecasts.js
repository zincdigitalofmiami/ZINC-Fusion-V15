import pg from 'pg';

const pool = new pg.Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false }
});

export default async function handler(req, res) {
  // CORS headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET');
  
  const { horizon = '21' } = req.query;
  
  try {
    // Get ZL prices + forecasts
    const result = await pool.query(`
      SELECT 
        m.as_of_date,
        m.open, m.high, m.low, m.close, m.volume
      FROM raw.market_futures_1d m
      WHERE m.symbol = 'ZL'
      ORDER BY m.as_of_date DESC
      LIMIT 252
    `);
    
    res.status(200).json({
      success: true,
      data: result.rows,
      horizon: horizon
    });
  } catch (error) {
    res.status(500).json({ success: false, error: error.message });
  }
}
