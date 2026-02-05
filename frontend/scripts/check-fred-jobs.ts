import { Pool } from "pg";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false }
});

async function main() {
  const client = await pool.connect();
  try {
    // Check FRED jobs recent insertions
    const res = await client.query(`
      SELECT job_name, started_at::date as run_date, rows_inserted, rows_skipped
      FROM ops.ingest_run
      WHERE job_name LIKE 'fred-%' AND started_at > NOW() - INTERVAL '7 days'
      ORDER BY job_name, started_at DESC
    `);
    console.log("FRED jobs - last 7 days:");
    let currentJob = "";
    res.rows.forEach((r: any) => {
      if (r.job_name !== currentJob) {
        currentJob = r.job_name;
        console.log(`\n${r.job_name}:`);
      }
      const dateStr = r.run_date instanceof Date ? r.run_date.toISOString().slice(0, 10) : String(r.run_date).slice(0, 10);
      console.log(`  ${dateStr} | ins:${r.rows_inserted} skip:${r.rows_skipped}`);
    });
  } finally {
    client.release();
    await pool.end();
  }
}
main();
