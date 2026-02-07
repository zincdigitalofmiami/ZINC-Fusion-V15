import { config } from 'dotenv';
config();
import { PrismaClient } from './prisma/generated/prisma/index.js';

async function check() {
  const prisma = new PrismaClient({ accelerateUrl: process.env.PRISMA_DATABASE_URL });
  
  try {
    // Get column names for model_registry
    const cols = await prisma.$queryRaw`
      SELECT column_name 
      FROM information_schema.columns 
      WHERE table_schema = 'model' AND table_name = 'model_registry'
      ORDER BY ordinal_position
    `;
    console.log('model_registry columns:', cols.map(c => c.column_name).join(', '));

    // Get all rows
    const rows = await prisma.$queryRaw`SELECT * FROM model.model_registry LIMIT 10`;
    console.log('\n=== MODEL REGISTRY (first 10) ===');
    rows.forEach((r, i) => {
      console.log(`\n--- Row ${i+1} ---`);
      Object.entries(r).forEach(([k, v]) => {
        if (v !== null) console.log(`  ${k}: ${v}`);
      });
    });

  } catch (e) {
    console.error('Error:', e.message);
  } finally {
    await prisma.$disconnect();
  }
}

check();
