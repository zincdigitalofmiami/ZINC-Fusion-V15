import { config } from 'dotenv';
config();
import { PrismaClient } from './prisma/generated/prisma/index.js';

async function check() {
  const prisma = new PrismaClient({ accelerateUrl: process.env.PRISMA_DATABASE_URL });
  
  try {
    // List all tables in model schema
    const modelTables = await prisma.$queryRaw`
      SELECT table_name, 
             (SELECT COUNT(*)::int FROM information_schema.columns WHERE table_schema = 'model' AND table_name = t.table_name) as columns
      FROM information_schema.tables t
      WHERE table_schema = 'model'
      ORDER BY table_name
    `;
    console.log('=== MODEL SCHEMA TABLES ===');
    console.table(modelTables);

    // List all tables in training schema
    const trainingTables = await prisma.$queryRaw`
      SELECT table_name,
             (SELECT COUNT(*)::int FROM information_schema.columns WHERE table_schema = 'training' AND table_name = t.table_name) as columns
      FROM information_schema.tables t
      WHERE table_schema = 'training'
      ORDER BY table_name
    `;
    console.log('\n=== TRAINING SCHEMA TABLES ===');
    console.table(trainingTables);

  } catch (e) {
    console.error(e.message);
  } finally {
    await prisma.$disconnect();
  }
}

check();
