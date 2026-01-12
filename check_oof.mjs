import { config } from 'dotenv';
config();
import { PrismaClient } from './prisma/generated/prisma/index.js';

async function check() {
  const prisma = new PrismaClient({ accelerateUrl: process.env.PRISMA_DATABASE_URL });
  
  try {
    // Check OOF predictions by specialist
    const oofStats = await prisma.$queryRaw`
      SELECT 
        specialist,
        horizon,
        COUNT(*)::int as row_count,
        MIN(event_date)::date as earliest,
        MAX(event_date)::date as latest
      FROM model.oof_predictions
      GROUP BY specialist, horizon
      ORDER BY specialist, horizon
    `;
    console.log('=== OOF PREDICTIONS BY SPECIALIST ===');
    console.table(oofStats);

    // Check model registry
    const modelReg = await prisma.$queryRaw`
      SELECT 
        model_name,
        model_type,
        horizon,
        trained_at::date as trained,
        mape,
        status
      FROM model.model_registry
      ORDER BY trained_at DESC
      LIMIT 20
    `;
    console.log('\n=== MODEL REGISTRY (LATEST 20) ===');
    console.table(modelReg);

  } catch (e) {
    console.error(e.message);
  } finally {
    await prisma.$disconnect();
  }
}

check();
