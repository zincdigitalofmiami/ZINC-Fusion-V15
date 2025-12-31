import pg from 'pg';

const pool = new pg.Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false }
});

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  
  try {
    const result = await pool.query(`
      SELECT posture, confidence, regime, tail_risk_prob
      FROM analytics.market_posture
      WHERE as_of_date = (SELECT MAX(as_of_date) FROM analytics.market_posture)
      AND horizon = 21 LIMIT 1
    `);
    
    if (result.rows.length > 0) {
      const row = result.rows[0];
      return res.status(200).json({
        success: true, level: row.posture,
        confidence: parseFloat(row.confidence),
        regime: { current: row.regime, probability: 0.68 },
        tailRiskProb: parseFloat(row.tail_risk_prob)
      });
    }
    
    res.status(200).json({
      success: true, level: 'WAIT', confidence: 0.72,
      regime: { current: 'contango', probability: 0.68 },
      tailRiskProb: 0.15, source: 'mock'
    });
  } catch (error) {
    res.status(500).json({ success: false, error: error.message });
  }
}
