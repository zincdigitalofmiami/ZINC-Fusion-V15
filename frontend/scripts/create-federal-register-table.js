const { Pool } = require('pg');
require('dotenv').config({ path: '.env.local' });

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false }
});

/**
 * DEPRECATED: raw.legislation_federal_register_1d no longer exists.
 * Federal Register data now lives in alt.legislation_1d (managed by Prisma schema).
 *
 * This script is kept for historical reference only.
 * DO NOT RUN - will fail with "schema raw does not exist".
 */

console.error(`
❌ DEPRECATED SCRIPT - DO NOT RUN

Federal Register legislation data is now in:
  alt.legislation_1d

This table is managed by Prisma migrations.
The 'raw' schema was removed per v2 schema architecture.

To check legislation data, use:
  node frontend/scripts/check-federal-register-data.js
`);

process.exit(1);
