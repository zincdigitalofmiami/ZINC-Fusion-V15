import { config } from 'dotenv';
config();
import { PrismaClient } from './prisma/generated/prisma/index.js';

async function check() {
  const prisma = new PrismaClient({ accelerateUrl: process.env.PRISMA_DATABASE_URL });
  
  try {
    // Note: model_registry uses dataset_end_date (not training_end_date) and artifact_path (not model_path)
    // specialist column doesn't exist - use model_type instead
    const modelReg = await prisma.$queryRaw`
      SELECT
        model_name,
        model_type,
        horizon,
        trained_at,
        dataset_end_date,
        status,
        mape,
        rmse,
        artifact_path
      FROM model.model_registry
      ORDER BY trained_at DESC
    `;
    console.log('=== ALL REGISTERED MODELS ===');
    console.table(modelReg);

    // Check training features tables row counts
    const featureCounts = await prisma.$queryRaw`
      SELECT 
        'specialist_crush_1d' as tbl, COUNT(*)::int as rows FROM training.specialist_crush_1d
      UNION ALL
      SELECT 'specialist_china_1d', COUNT(*)::int FROM training.specialist_china_1d
      UNION ALL
      SELECT 'specialist_energy_1d', COUNT(*)::int FROM training.specialist_energy_1d
      UNION ALL
      SELECT 'specialist_trump_effect_1d', COUNT(*)::int FROM training.specialist_trump_effect_1d
      UNION ALL
      SELECT 'core_features', COUNT(*)::int FROM training.core_features
      ORDER BY tbl
    `;
    console.log('\n=== TRAINING FEATURE TABLE COUNTS ===');
    console.table(featureCounts);

  } catch (e) {
    console.error('Error:', e.message);
  } finally {
    await prisma.$disconnect();
  }
}

check();
