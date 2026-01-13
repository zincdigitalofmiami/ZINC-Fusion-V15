const { PrismaClient } = require('@prisma/client');
const prisma = new PrismaClient();

async function audit() {
  const tables = [
    { name: 'raw.market_futures_1d', dateCol: 'event_date' },
    { name: 'raw.market_futures_1h', dateCol: 'event_time' },
    { name: 'raw.fx_spot_1d', dateCol: 'event_date' },
    { name: 'raw.fred_observations_1d', dateCol: 'event_date' },
    { name: 'raw.cftc_cot_1w', dateCol: 'event_date' },
    { name: 'raw.whitehouse_actions_event', dateCol: 'event_date' },
    { name: 'raw.legislation_federal_register_1d', dateCol: 'event_date' },
    { name: 'ops.ingest_run', dateCol: 'started_at' }
  ];
  
  console.log('=== DATA FRESHNESS AUDIT ===');
  const today = new Date().toISOString().split('T')[0];
  console.log('Today:', today);
  console.log('');
  
  for (const t of tables) {
    try {
      const result = await prisma.$queryRawUnsafe(`
        SELECT 
          COUNT(*) as rows,
          MIN(${t.dateCol})::date as earliest,
          MAX(${t.dateCol})::date as latest
        FROM ${t.name}
      `);
      const r = result[0];
      console.log(`${t.name}: ${r.rows} rows, ${r.earliest} → ${r.latest}`);
    } catch (e) {
      console.log(`${t.name}: ERROR - ${e.message.split('\n')[0]}`);
    }
  }
}

audit().then(() => prisma.$disconnect());
