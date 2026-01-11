/**
 * Test script for federal-register.ts Inngest job
 * Simulates the job locally without Inngest infrastructure
 */
require('dotenv').config({ path: '.env.local' });
const { Pool } = require('pg');
const { createHash } = require('crypto');

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

// Tag rules (copied from federal-register.ts)
const TAG_RULES = [
  { pattern: /section[\s_-]?301/i, tags: ["tariff"] },
  { pattern: /section[\s_-]?232/i, tags: ["tariff"] },
  { pattern: /tariff[\s_-]?(rate|schedule|exclusion|list)/i, tags: ["tariff"] },
  { pattern: /anti[\s_-]?dumping/i, tags: ["tariff"] },
  { pattern: /countervailing[\s_-]?dut/i, tags: ["tariff"] },
  { pattern: /trade[\s_-]?(deal|agreement|negotiation)/i, tags: ["tariff", "trump_effect"] },
  { pattern: /usmca|nafta/i, tags: ["tariff", "trump_effect"] },
  { pattern: /\bchina\b|\bprc\b|chinese/i, tags: ["china", "tariff"] },
  { pattern: /cofco|sinograin/i, tags: ["china"] },
  { pattern: /executive[\s_-]?order/i, tags: ["trump_effect"] },
  { pattern: /presidential[\s_-]?(action|memorandum|proclamation|determination)/i, tags: ["trump_effect"] },
  { pattern: /doge|government[\s_-]?efficiency/i, tags: ["trump_effect"] },
  { pattern: /immigration|ice[\s_-]enforcement|deportation|visa|border[\s_-]?(security|control)/i, tags: ["trump_effect", "legislation"] },
  { pattern: /renewable[\s_-]?fuel[\s_-]?standard|rfs/i, tags: ["biofuel"] },
  { pattern: /\brin\b|renewable[\s_-]?identification[\s_-]?number/i, tags: ["biofuel"] },
  { pattern: /biodiesel|renewable[\s_-]?diesel/i, tags: ["biofuel"] },
  { pattern: /\b45z\b|lcfs|clean[\s_-]?fuel/i, tags: ["biofuel"] },
  { pattern: /epa.*fuel|fuel.*epa/i, tags: ["biofuel"] },
  { pattern: /blending[\s_-]?mandate|blender/i, tags: ["biofuel"] },
  { pattern: /petroleum|crude[\s_-]?oil|refiner/i, tags: ["energy"] },
  { pattern: /natural[\s_-]?gas|lng/i, tags: ["energy"] },
  { pattern: /opec|oil[\s_-]?export/i, tags: ["energy"] },
  { pattern: /soybean|soy[\s_-]?oil|soy[\s_-]?meal/i, tags: ["crush"] },
  { pattern: /usda|department[\s_-]?of[\s_-]?agriculture/i, tags: ["crush"] },
  { pattern: /grain|corn|wheat/i, tags: ["crush", "substitutes"] },
  { pattern: /federal[\s_-]?reserve|fomc|monetary[\s_-]?policy/i, tags: ["fed"] },
  { pattern: /interest[\s_-]?rate|treasury[\s_-]?yield/i, tags: ["fed"] },
  { pattern: /sanctions|ofac|export[\s_-]?control/i, tags: ["tariff", "china"] },
  { pattern: /.*/, tags: ["legislation"] },
];

function assignTags(title, abstract, docType, agencies) {
  const content = `${title} ${abstract} ${agencies.join(" ")}`.toLowerCase();
  const tags = new Set();
  
  if (docType === "PRESDOCU" || docType === "Presidential Document") {
    tags.add("trump_effect");
  }
  
  for (const rule of TAG_RULES) {
    if (rule.pattern.test(content)) {
      rule.tags.forEach(tag => tags.add(tag));
    }
  }
  
  tags.add("legislation");
  return Array.from(tags);
}

function computeRowHash(documentNumber, pubDate) {
  return createHash("sha256").update(`${documentNumber}|${pubDate}`).digest("hex");
}

async function test() {
  const client = await pool.connect();
  
  try {
    // 1. Fetch documents
    const endDate = new Date();
    const startDate = new Date();
    startDate.setDate(startDate.getDate() - 7);
    const formatDate = (d) => d.toISOString().split('T')[0];
    
    const baseUrl = 'https://www.federalregister.gov/api/v1/documents.json';
    const params = new URLSearchParams({
      'per_page': '20',
      'order': 'newest',
      'conditions[publication_date][gte]': formatDate(startDate),
      'conditions[publication_date][lte]': formatDate(endDate),
    });
    ['RULE', 'PRORULE', 'NOTICE', 'PRESDOCU'].forEach(type => {
      params.append('conditions[type][]', type);
    });
    
    console.log('Fetching Federal Register documents...');
    const response = await fetch(`${baseUrl}?${params.toString()}`);
    const json = await response.json();
    console.log(`Fetched ${json.results.length} documents (${json.count} total available)\n`);
    
    // 2. Create ingest run
    const runResult = await client.query(
      `INSERT INTO ops.ingest_run (job_name, status, started_at)
       VALUES ($1, 'running', NOW())
       RETURNING id`,
      ['federal-register-daily-test']
    );
    const runId = runResult.rows[0].id;
    console.log(`Created ingest run: ${runId}\n`);
    
    // 3. Process documents
    let inserted = 0, skipped = 0, quarantined = 0;
    const tagCounts = {};
    
    for (const doc of json.results) {
      const rowHash = computeRowHash(doc.document_number, doc.publication_date);
      
      // Check duplicate
      const exists = await client.query(
        'SELECT 1 FROM raw.legislation_federal_register_1d WHERE row_hash = $1 LIMIT 1',
        [rowHash]
      );
      
      if (exists.rows.length > 0) {
        skipped++;
        continue;
      }
      
      const agencies = (doc.agencies || []).map(a => a.name);
      const tags = assignTags(doc.title || '', doc.abstract || '', doc.type, agencies);
      
      // Count tags
      tags.forEach(tag => { tagCounts[tag] = (tagCounts[tag] || 0) + 1; });
      
      try {
        await client.query(
          `INSERT INTO raw.legislation_federal_register_1d (
             event_date, document_number, document_type, title, abstract,
             agency, publication_date, effective_date,
             knowledge_time, revision_no, is_preliminary, validation_status,
             source_url, raw_payload, ingestion_batch_id, row_hash, specialist_tags
           ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), 1, false, 'validated', $9, $10, $11, $12, $13)`,
          [
            doc.publication_date,
            doc.document_number,
            doc.type,
            doc.title,
            doc.abstract,
            agencies,
            doc.publication_date,
            doc.effective_on,
            doc.html_url,
            JSON.stringify(doc),
            runId,
            rowHash,
            tags,
          ]
        );
        inserted++;
        console.log(`✅ Inserted: ${doc.document_number} [${tags.join(', ')}]`);
      } catch (err) {
        quarantined++;
        console.log(`❌ Error inserting ${doc.document_number}: ${err.message}`);
      }
    }
    
    // 4. Update ingest run
    await client.query(
      `UPDATE ops.ingest_run
       SET status = 'success', completed_at = NOW(),
           rows_attempted = $2, rows_inserted = $3,
           rows_skipped = $4, rows_quarantined = $5
       WHERE id = $1`,
      [runId, json.results.length, inserted, skipped, quarantined]
    );
    
    // 5. Summary
    console.log('\n=== Summary ===');
    console.log(`Attempted: ${json.results.length}`);
    console.log(`Inserted: ${inserted}`);
    console.log(`Skipped (duplicates): ${skipped}`);
    console.log(`Quarantined: ${quarantined}`);
    console.log('\nTag distribution:', tagCounts);
    
    // 6. Verify table
    const count = await client.query('SELECT COUNT(*) FROM raw.legislation_federal_register_1d');
    console.log(`\nTotal rows in table: ${count.rows[0].count}`);
    
  } finally {
    client.release();
    await pool.end();
  }
}

test().catch(console.error);
