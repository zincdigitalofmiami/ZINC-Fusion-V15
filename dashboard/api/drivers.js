import pg from 'pg';

const pool = new pg.Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false }
});

// Specialist configurations for signal calculation
const SPECIALIST_CONFIG = {
  crush: {
    name: 'Crush',
    description: 'Processor margins & meal/oil ratio',
    // Signal: ZL/ZM spread relative to historical
    query: `
      SELECT
        zl.as_of_date,
        zl.close::float as zl_price,
        zm.close::float as zm_price,
        (zl.close / NULLIF(zm.close, 0))::float as ratio
      FROM training.specialist_crush_1d zl
      JOIN training.specialist_crush_1d zm
        ON zl.as_of_date = zm.as_of_date AND zm.symbol = 'ZM'
      WHERE zl.symbol = 'ZL'
      ORDER BY zl.as_of_date DESC
      LIMIT 60
    `
  },
  china: {
    name: 'China',
    description: 'Import demand & stockpiles',
    query: `
      SELECT as_of_date, close::float as value
      FROM training.specialist_china_1d
      WHERE symbol = 'ZL'
      ORDER BY as_of_date DESC
      LIMIT 60
    `
  },
  energy: {
    name: 'Energy',
    description: 'Crude & Diesel correlation',
    query: `
      SELECT
        zl.as_of_date,
        zl.close::float as zl_price,
        cl.close::float as cl_price
      FROM training.specialist_energy_1d zl
      JOIN training.specialist_energy_1d cl
        ON zl.as_of_date = cl.as_of_date AND cl.symbol = 'CL'
      WHERE zl.symbol = 'ZL'
      ORDER BY zl.as_of_date DESC
      LIMIT 60
    `
  },
  fx: {
    name: 'FX',
    description: 'USD Strength & EM Crosses',
    query: `
      SELECT as_of_date, close::float as value
      FROM training.specialist_fx_1d
      WHERE symbol = 'DX'
      ORDER BY as_of_date DESC
      LIMIT 60
    `
  },
  fed: {
    name: 'Fed',
    description: 'Yield Curve & Liquidity',
    query: `
      SELECT as_of_date, close::float as value
      FROM training.specialist_fed_1d
      WHERE symbol = 'ZN'
      ORDER BY as_of_date DESC
      LIMIT 60
    `
  },
  tariff: {
    name: 'Tariff',
    description: 'Trade Policy & Duties',
    query: `
      SELECT as_of_date, close::float as value
      FROM training.specialist_tariff_1d
      WHERE symbol = 'ZL'
      ORDER BY as_of_date DESC
      LIMIT 60
    `
  },
  biofuel: {
    name: 'Biofuel',
    description: 'RINs & Mandates',
    query: `
      SELECT as_of_date, close::float as value
      FROM training.specialist_biofuel_1d
      WHERE symbol = 'ZL'
      ORDER BY as_of_date DESC
      LIMIT 60
    `
  },
  palm: {
    name: 'Palm',
    description: 'Malaysian Supply',
    query: `
      SELECT as_of_date, close::float as value
      FROM training.specialist_palm_1d
      WHERE symbol = 'ZL'
      ORDER BY as_of_date DESC
      LIMIT 60
    `
  },
  volatility: {
    name: 'Volatility',
    description: 'Regime Detection',
    query: `
      SELECT as_of_date, close::float as value
      FROM training.specialist_volatility_1d
      WHERE symbol = 'ZL'
      ORDER BY as_of_date DESC
      LIMIT 60
    `
  },
  substitutes: {
    name: 'Substitutes',
    description: 'Canola/Sunflower Spreads',
    query: `
      SELECT as_of_date, close::float as value
      FROM training.specialist_substitutes_1d
      WHERE symbol = 'ZL'
      ORDER BY as_of_date DESC
      LIMIT 60
    `
  }
};

// Calculate z-score signal from price series
function calculateSignal(data, type = 'momentum') {
  if (!data || data.length < 20) return { signal: 0, direction: 'neutral', history: [] };

  const values = data.map(d => d.ratio || d.value || d.zl_price).filter(v => v != null);
  if (values.length < 20) return { signal: 0, direction: 'neutral', history: [] };

  // Reverse to chronological order
  values.reverse();

  // Calculate 20-day returns
  const returns = [];
  for (let i = 1; i < Math.min(21, values.length); i++) {
    returns.push((values[values.length - 1] - values[values.length - 1 - i]) / values[values.length - 1 - i]);
  }

  // Calculate momentum signal (normalized return)
  const recentReturn = returns[0] || 0;
  const avgReturn = returns.reduce((a, b) => a + b, 0) / returns.length;
  const stdReturn = Math.sqrt(returns.reduce((a, b) => a + Math.pow(b - avgReturn, 2), 0) / returns.length);

  // Z-score of recent return
  const signal = stdReturn > 0 ? (recentReturn - avgReturn) / stdReturn / 10 : 0;

  // Clamp signal to reasonable range
  const clampedSignal = Math.max(-0.1, Math.min(0.1, signal));

  // Direction based on signal
  let direction = 'neutral';
  if (clampedSignal > 0.01) direction = 'bullish';
  else if (clampedSignal < -0.01) direction = 'bearish';

  // Generate history for sparkline (last 30 days of normalized values)
  const history = [];
  const baseValue = values[values.length - 30] || values[0];
  for (let i = Math.max(0, values.length - 30); i < values.length; i++) {
    const idx = i - Math.max(0, values.length - 30);
    const normalizedValue = (values[i] - baseValue) / baseValue;
    const date = data[data.length - 1 - (values.length - 1 - i)]?.as_of_date;
    if (date) {
      history.push({
        time: new Date(date).toISOString().split('T')[0],
        value: normalizedValue
      });
    }
  }

  return { signal: clampedSignal, direction, history };
}

// Special calculation for crush spread
function calculateCrushSignal(data) {
  if (!data || data.length < 20) return { signal: 0, direction: 'neutral', history: [] };

  const ratios = data.map(d => d.ratio).filter(v => v != null);
  if (ratios.length < 20) return { signal: 0, direction: 'neutral', history: [] };

  ratios.reverse();

  // Calculate z-score of current ratio vs 60-day mean
  const mean = ratios.reduce((a, b) => a + b, 0) / ratios.length;
  const std = Math.sqrt(ratios.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / ratios.length);
  const currentRatio = ratios[ratios.length - 1];

  const zScore = std > 0 ? (currentRatio - mean) / std : 0;
  const signal = Math.max(-0.1, Math.min(0.1, zScore / 30)); // Normalize to ~0.03 range

  let direction = 'neutral';
  if (signal > 0.01) direction = 'bullish';
  else if (signal < -0.01) direction = 'bearish';

  // History
  const history = [];
  for (let i = Math.max(0, ratios.length - 30); i < ratios.length; i++) {
    const idx = i - Math.max(0, ratios.length - 30);
    const date = data[data.length - 1 - (ratios.length - 1 - i)]?.as_of_date;
    if (date) {
      history.push({
        time: new Date(date).toISOString().split('T')[0],
        value: (ratios[i] - mean) / mean
      });
    }
  }

  return { signal, direction, history };
}

// Special calculation for FX (inverse - strong dollar is bearish for ZL)
function calculateFxSignal(data) {
  const result = calculateSignal(data);
  return {
    signal: -result.signal, // Inverse
    direction: result.signal > 0.01 ? 'bearish' : result.signal < -0.01 ? 'bullish' : 'neutral',
    history: result.history.map(h => ({ ...h, value: -h.value }))
  };
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET');

  try {
    // First check for pre-computed driver scores
    const precomputedResult = await pool.query(`
      SELECT specialist, signal::float, direction, confidence::float, shap_contribution::float
      FROM analytics.driver_scores
      WHERE as_of_date = (SELECT MAX(as_of_date) FROM analytics.driver_scores)
      ORDER BY ABS(signal) DESC
    `);

    if (precomputedResult.rows.length >= 10) {
      const drivers = precomputedResult.rows.map(row => ({
        id: row.specialist,
        name: SPECIALIST_CONFIG[row.specialist]?.name || row.specialist,
        description: SPECIALIST_CONFIG[row.specialist]?.description || '',
        signal: row.signal,
        direction: row.direction,
        weight: row.shap_contribution || 0.1
      }));
      return res.status(200).json({ success: true, drivers, source: 'precomputed' });
    }

    // Calculate signals from specialist training data
    const drivers = [];

    for (const [id, config] of Object.entries(SPECIALIST_CONFIG)) {
      try {
        const result = await pool.query(config.query);

        let signalData;
        if (id === 'crush') {
          signalData = calculateCrushSignal(result.rows);
        } else if (id === 'fx') {
          signalData = calculateFxSignal(result.rows);
        } else {
          signalData = calculateSignal(result.rows);
        }

        drivers.push({
          id,
          name: config.name,
          description: config.description,
          signal: signalData.signal,
          direction: signalData.direction,
          history: signalData.history
        });
      } catch (err) {
        console.error(`Error calculating ${id} signal:`, err.message);
        drivers.push({
          id,
          name: config.name,
          description: config.description,
          signal: 0,
          direction: 'neutral',
          history: []
        });
      }
    }

    // Sort by absolute signal strength
    drivers.sort((a, b) => Math.abs(b.signal) - Math.abs(a.signal));

    res.status(200).json({
      success: true,
      drivers,
      source: 'computed',
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Drivers API error:', error);
    res.status(500).json({ success: false, error: error.message });
  }
}
