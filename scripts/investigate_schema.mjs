/**
 * Schema Investigation Script
 * Read-only - investigates actual database schema vs expected
 */
import { config } from 'dotenv';
config();

import { PrismaClient } from '../prisma/generated/prisma/index.js';

async function investigate() {
  const prisma = new PrismaClient({
    accelerateUrl: process.env.PRISMA_DATABASE_URL
  });
  
  try {
    console.log('=== SCHEMA INVESTIGATION ===\n');
    
    // 1. Check CFTC table actual columns
    const cftcCols = await prisma.$queryRaw`
      SELECT column_name, data_type 
      FROM information_schema.columns 
      WHERE table_schema = 'raw' AND table_name = 'cftc_cot_1w'
      ORDER BY ordinal_position
    `;
    console.log('raw.cftc_cot_1w COLUMNS:');
    cftcCols.forEach(c => console.log(`  ${c.column_name}: ${c.data_type}`));
    
    // 2. Check CFTC most recent data
    const cftcRecent = await prisma.$queryRaw`
      SELECT event_date, symbol, open_interest 
      FROM raw.cftc_cot_1w 
      ORDER BY event_date DESC 
      LIMIT 5
    `;
    console.log('\nraw.cftc_cot_1w RECENT DATA:');
    cftcRecent.forEach(r => console.log(`  ${r.event_date} | ${r.symbol} | OI: ${r.open_interest}`));
    
    // 3. Check FX table columns
    const fxCols = await prisma.$queryRaw`
      SELECT column_name, data_type 
      FROM information_schema.columns 
      WHERE table_schema = 'raw' AND table_name = 'fx_spot_1d'
      ORDER BY ordinal_position
    `;
    console.log('\nraw.fx_spot_1d COLUMNS:');
    fxCols.forEach(c => console.log(`  ${c.column_name}: ${c.data_type}`));
    
    // 4. Check FX recent data
    const fxRecent = await prisma.$queryRaw`
      SELECT event_date, pair, rate 
      FROM raw.fx_spot_1d 
      ORDER BY event_date DESC 
      LIMIT 5
    `;
    console.log('\nraw.fx_spot_1d RECENT DATA:');
    fxRecent.forEach(r => console.log(`  ${r.event_date} | ${r.pair} | ${r.rate}`));
    
    // 5. Check EPA RIN columns
    const rinCols = await prisma.$queryRaw`
      SELECT column_name, data_type 
      FROM information_schema.columns 
      WHERE table_schema = 'raw' AND table_name = 'epa_rin_prices_1d'
      ORDER BY ordinal_position
    `;
    console.log('\nraw.epa_rin_prices_1d COLUMNS:');
    rinCols.forEach(c => console.log(`  ${c.column_name}: ${c.data_type}`));
    
    // 6. Check EPA RIN recent data
    const rinRecent = await prisma.$queryRaw`
      SELECT event_date, rin_type, price 
      FROM raw.epa_rin_prices_1d 
      ORDER BY event_date DESC 
      LIMIT 5
    `;
    console.log('\nraw.epa_rin_prices_1d RECENT DATA:');
    rinRecent.forEach(r => console.log(`  ${r.event_date} | ${r.rin_type} | $${r.price}`));
    
    // 7. Check market_futures_1d columns (critical for Yahoo job)
    const mktCols = await prisma.$queryRaw`
      SELECT column_name, data_type 
      FROM information_schema.columns 
      WHERE table_schema = 'raw' AND table_name = 'market_futures_1d'
      ORDER BY ordinal_position
      LIMIT 20
    `;
    console.log('\nraw.market_futures_1d COLUMNS (first 20):');
    mktCols.forEach(c => console.log(`  ${c.column_name}: ${c.data_type}`));
    
    console.log('\n=== INVESTIGATION COMPLETE ===');
    
  } catch (e) {
    console.error('Error:', e);
  } finally {
    await prisma.$disconnect();
  }
}

investigate();
