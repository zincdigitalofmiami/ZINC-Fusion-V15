import { config } from 'dotenv';
config();
import { PrismaClient } from './prisma/generated/prisma/index.js';

async function check() {
  const prisma = new PrismaClient({ accelerateUrl: process.env.PRISMA_DATABASE_URL });
  
  try {
    // Check OOF predictions
    const oofCount = await prisma.$queryRaw`SELECT COUNT(*)::int as cnt FROM model.oof_predictions`;
    console.log('OOF Predictions total:', oofCount[0].cnt);

    if (oofCount[0].cnt > 0) {
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
      console.log('\n=== OOF PREDICTIONS BY SPECIALIST ===');
      console.table(oofStats);
    }

    // Check model registry
    const regCount = await prisma.$queryRaw`SELECT COUNT(*)::int as cnt FROM model.model_registry`;
    console.log('\nModel Registry total:', regCount[0].cnt);

    if (regCount[0].cnt > 0) {
      const modelReg = await prisma.$queryRaw`
        SELECT 
          model_name,
          model_type,
          specialist,
          horizon,
          trained_at::date as trained,
          status
        FROM model.model_registry
        ORDER BY trained_at DESC
        LIMIT 20
      `;
      console.log('\n=== MODEL REGISTRY (LATEST 20) ===');
      console.table(modelReg);
    }

    // Check lasso coefficients
    const lassoCount = await prisma.$queryRaw`SELECT COUNT(*)::int as cnt FROM model.lasso_coefficients`;
    console.log('\nLasso Coefficients total:', lassoCount[0].cnt);
    
    if (lassoCount[0].cnt > 0) {
      const lassoStats = await prisma.$queryRaw`
        SELECT 
          specialist,
          COUNT(*)::int as features,
          MAX(created_at)::date as latest
        FROM model.lasso_coefficients
        GROUP BY specialist
        ORDER BY specialist
      `;
      console.log('\n=== LASSO COEFFICIENTS BY SPECIALIST ===');
      console.table(lassoStats);
    }

  } catch (e) {
    console.error('Error:', e.message);
  } finally {
    await prisma.$disconnect();
  }
}

check();
