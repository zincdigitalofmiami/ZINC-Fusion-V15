const puppeteer = require('puppeteer');
const path = require('path');
const crypto = require('crypto');
require('dotenv').config({ path: path.join(__dirname, '../frontend/.env.local') });

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function findAll() {
  const user = process.env.PROFARMER_USERNAME;
  const pass = process.env.PROFARMER_PASSWORD;
  const { Pool } = require('pg');
  const pool = new Pool({ connectionString: process.env.DATABASE_URL, ssl: { rejectUnauthorized: false } });

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox'],
    defaultViewport: { width: 1920, height: 4000 },
  });

  const page = await browser.newPage();
  await page.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36');

  // LOGIN
  console.log('LOGIN...');
  await page.goto('https://www.profarmer.com/r/sign-in', { waitUntil: 'networkidle2' });
  await sleep(1000);
  await page.evaluate(() => {
    document.querySelectorAll('form').forEach(f => {
      const e = f.querySelector('input[type="email"]');
      if (e && f.querySelector('input[type="password"]')) e.focus();
    });
  });
  await page.keyboard.type(user, { delay: 40 });
  await page.keyboard.press('Tab');
  await page.keyboard.type(pass, { delay: 40 });
  await page.keyboard.press('Enter');
  await sleep(5000);
  console.log('OK\n');

  // Check sitemap
  console.log('=== CHECKING SITEMAP ===');
  try {
    await page.goto('https://www.profarmer.com/sitemap.xml', { waitUntil: 'networkidle2', timeout: 10000 });
    const sitemapContent = await page.content();
    const urlCount = (sitemapContent.match(/<loc>/g) || []).length;
    console.log('Sitemap URLs found:', urlCount);
  } catch (e) {
    console.log('No sitemap.xml');
  }

  // Check robots.txt for sitemaps
  console.log('\n=== CHECKING ROBOTS ===');
  try {
    await page.goto('https://www.profarmer.com/robots.txt', { waitUntil: 'networkidle2', timeout: 10000 });
    const robots = await page.evaluate(() => document.body.innerText);
    console.log(robots.slice(0, 500));
  } catch (e) {
    console.log('No robots.txt');
  }

  // Try search functionality
  console.log('\n=== TRYING SEARCH ===');
  await page.goto('https://www.profarmer.com/search?q=soybean', { waitUntil: 'networkidle2' });
  await sleep(2000);
  
  // Scroll down multiple times to load more
  for (let i = 0; i < 10; i++) {
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await sleep(1000);
  }
  
  const searchResults = await page.evaluate(() => {
    const links = [];
    document.querySelectorAll('a[href*="/news/"]').forEach(a => {
      if (!a.href.includes('/topics/') && !a.href.includes('/r/')) {
        links.push(a.href);
      }
    });
    return [...new Set(links)];
  });
  console.log('Search results for "soybean":', searchResults.length);

  // Try the main /news with infinite scroll
  console.log('\n=== SCROLLING /news ===');
  await page.goto('https://www.profarmer.com/news', { waitUntil: 'networkidle2' });
  
  let lastCount = 0;
  for (let i = 0; i < 50; i++) {
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await sleep(800);
    
    const count = await page.evaluate(() => {
      return document.querySelectorAll('a[href*="/news/"]').length;
    });
    
    if (count === lastCount) {
      // Try clicking "load more" button if exists
      const clicked = await page.evaluate(() => {
        const btn = document.querySelector('button[class*="load"], a[class*="load"], [class*="more"]');
        if (btn) { btn.click(); return true; }
        return false;
      });
      if (!clicked) break;
    }
    lastCount = count;
    if (i % 10 === 0) console.log(`  Scroll ${i}: ${count} links`);
  }

  const allNewsLinks = await page.evaluate(() => {
    const links = [];
    document.querySelectorAll('a[href*="/news/"]').forEach(a => {
      const h = a.href;
      if (!h.includes('/topics/') && !h.includes('/r/')) {
        const parts = h.replace('https://www.profarmer.com', '').split('/').filter(Boolean);
        if (parts.length >= 3) links.push(h);
      }
    });
    return [...new Set(links)];
  });
  console.log('Total unique /news links after scroll:', allNewsLinks.length);

  // Try archive by year
  console.log('\n=== TRYING YEAR ARCHIVES ===');
  const years = ['2026', '2025', '2024', '2023', '2022', '2021', '2020'];
  for (const year of years) {
    try {
      await page.goto(`https://www.profarmer.com/news/${year}`, { waitUntil: 'networkidle2', timeout: 10000 });
      const count = await page.evaluate(() => document.querySelectorAll('a[href*="/news/"]').length);
      console.log(`  ${year}: ${count} links`);
    } catch {
      console.log(`  ${year}: no archive`);
    }
  }

  // Try archive path
  console.log('\n=== TRYING /archive ===');
  try {
    await page.goto('https://www.profarmer.com/archive', { waitUntil: 'networkidle2', timeout: 10000 });
    const count = await page.evaluate(() => document.querySelectorAll('a[href*="/news/"]').length);
    console.log('Archive links:', count);
  } catch {
    console.log('No /archive');
  }

  await browser.close();
  await pool.end();
}

findAll().catch(console.error);
