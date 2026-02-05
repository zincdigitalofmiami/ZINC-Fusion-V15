const puppeteer = require('puppeteer');
const path = require('path');
const crypto = require('crypto');
require('dotenv').config({ path: path.join(__dirname, '../frontend/.env.local') });

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function main() {
  const user = process.env.PROFARMER_USERNAME;
  const pass = process.env.PROFARMER_PASSWORD;
  const { Pool } = require('pg');
  const pool = new Pool({ connectionString: process.env.DATABASE_URL, ssl: { rejectUnauthorized: false } });

  const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'], defaultViewport: { width: 1920, height: 2000 } });
  const page = await browser.newPage();
  await page.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36');

  // LOGIN
  console.log('LOGIN...');
  await page.goto('https://www.profarmer.com/r/sign-in', { waitUntil: 'networkidle2' });
  await sleep(1000);
  await page.evaluate(() => { document.querySelectorAll('form').forEach(f => { const e = f.querySelector('input[type="email"]'); if (e && f.querySelector('input[type="password"]')) e.focus(); }); });
  await page.keyboard.type(user, { delay: 40 });
  await page.keyboard.press('Tab');
  await page.keyboard.type(pass, { delay: 40 });
  await page.keyboard.press('Enter');
  await sleep(5000);
  console.log('OK\n');

  const allUrls = new Set();
  const terms = ['soybean','corn','wheat','cattle','hogs','cotton','weather','USDA','trade','tariff','China','export','biofuel','grain','crop','farm','price','market','futures','drought','rain','harvest','planting','beef','pork','livestock','dairy','milk','oilseed','meal','oil','crush','spread','storage','2024','2025','2026','January','February','March','April','May','June','July','August','September','October','November','December','Trump','Biden','policy','EPA','RFS','RIN','E15','newsletter'];

  console.log('SEARCHING...');
  for (const term of terms) {
    try {
      await page.goto(`https://www.profarmer.com/search?q=${encodeURIComponent(term)}`, { waitUntil: 'networkidle2', timeout: 15000 });
      for (let i = 0; i < 5; i++) { await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight)); await sleep(200); }
      const links = await page.evaluate(() => [...document.querySelectorAll('a[href*="/news/"]')].map(a => a.href).filter(h => !h.includes('/topics/') && !h.includes('/r/')));
      links.forEach(u => allUrls.add(u));
    } catch {}
  }
  console.log(`Found ${allUrls.size} URLs\n`);

  // Also get from topic pages
  const topics = ['/news','/topics/first-thing-today','/topics/ahead-open','/topics/after-bell','/topics/corn','/topics/soybeans','/topics/wheat','/topics/cattle','/topics/weather','/topics/trade','/topics/pro-farmer-crop-tour','/newsletter'];
  for (const t of topics) {
    try {
      await page.goto(`https://www.profarmer.com${t}`, { waitUntil: 'networkidle2', timeout: 15000 });
      const links = await page.evaluate(() => [...document.querySelectorAll('a[href*="/news/"]')].map(a => a.href).filter(h => !h.includes('/topics/')));
      links.forEach(u => allUrls.add(u));
    } catch {}
  }
  console.log(`Total: ${allUrls.size} URLs\n`);

  let inserted = 0;
  const urlArray = [...allUrls];

  console.log('SCRAPING...');
  for (let i = 0; i < urlArray.length; i++) {
    const url = urlArray[i];
    const rowHash = crypto.createHash('sha256').update(`profarmer|${url}`).digest('hex');

    try {
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 15000 });
      await sleep(500);

      const data = await page.evaluate(() => {
        const pub = document.querySelector('meta[property="article:published_time"]')?.getAttribute('content');
        const h1 = document.querySelector('h1')?.textContent?.trim();
        const desc = document.querySelector('meta[name="description"]')?.getAttribute('content');
        const og = document.querySelector('meta[property="og:description"]')?.getAttribute('content');
        const sec = document.querySelector('meta[property="article:section"]')?.getAttribute('content');
        const tags = [...document.querySelectorAll('meta[property="article:tag"]')].map(m => m.getAttribute('content')).filter(Boolean);
        const author = document.querySelector('.Page-authorName a, .Page-authorName, [rel="author"]')?.textContent?.trim();
        let content = '';
        ['.Page-articleBody','.RichTextArticleBody','.Page-content','article'].forEach(s => { if (!content) { const e = document.querySelector(s); if (e) content = e.textContent?.trim()?.slice(0,60000); } });
        const topics = [...document.querySelectorAll('.Page-breadcrumbs a')].map(a => a.textContent?.trim()).filter(t => t && t !== 'Home' && t !== 'News');
        const id = window.location.pathname.split('/').filter(Boolean).pop();
        return { pub, h1, desc, og, sec, tags, author, content, topics, id };
      });

      if (!data.content || data.content.length < 30) continue;
      if (!data.pub) continue;

      const pubDate = new Date(data.pub);
      if (isNaN(pubDate.getTime())) continue;
      const eventDate = pubDate.toISOString().split('T')[0];

      const fullText = (data.h1 + ' ' + data.desc + ' ' + data.tags?.join(' ') + ' ' + data.topics?.join(' ')).toLowerCase();
      const specialistTags = [];
      if (/soy|crush|bean|meal|oil/.test(fullText)) specialistTags.push('crush');
      if (/china|asia|export/.test(fullText)) specialistTags.push('china');
      if (/corn|ethanol|biofuel|rin|epa|e15/.test(fullText)) specialistTags.push('biofuel');
      if (/tariff|trade|policy|trump|usda/.test(fullText)) specialistTags.push('tariff','trump_effect');
      if (/weather|rain|drought|storm/.test(fullText)) specialistTags.push('palm','crush');
      if (/wheat|canola|palm/.test(fullText)) specialistTags.push('substitutes');
      if (/energy|crude/.test(fullText)) specialistTags.push('energy');
      if (/fed|rate|dollar/.test(fullText)) specialistTags.push('fed','fx');
      if (!specialistTags.length) specialistTags.push('crush');

      const isTrump = /trump|tariff|trade war/i.test(fullText);
      const payload = { desc: data.desc, og: data.og, sec: data.sec, tags: data.tags, topics: data.topics, scraped: new Date().toISOString() };

      await pool.query(
        `INSERT INTO alt.news_1d (article_id, event_date, published_at, headline, content, url, author, source, is_trump_related, specialist_tags, row_hash, raw_payload, knowledge_time, ingested_at)
         VALUES ($1,$2::date,$3::timestamptz,$4,$5,$6,$7,'profarmer',$8,$9,$10,$11::jsonb,NOW(),NOW()) ON CONFLICT (row_hash) DO NOTHING`,
        [data.id, eventDate, data.pub, data.h1?.slice(0,1000), data.content, url, data.author, isTrump, [...new Set(specialistTags)], rowHash, JSON.stringify(payload)]
      );
      inserted++;
      if (inserted % 10 === 0 || inserted < 5) console.log(`[${inserted}] ${eventDate} | ${(data.h1||'').slice(0,50)}`);
    } catch (e) {
      // skip
    }
  }

  console.log(`\n=== DONE: ${inserted} INSERTED ===`);
  const cnt = await pool.query("SELECT COUNT(*), MIN(event_date), MAX(event_date) FROM alt.news_1d WHERE source='profarmer'");
  console.log(`DB: ${cnt.rows[0].count} articles | ${cnt.rows[0].min} to ${cnt.rows[0].max}`);

  await browser.close();
  await pool.end();
}

main().catch(e => { console.error(e); process.exit(1); });
