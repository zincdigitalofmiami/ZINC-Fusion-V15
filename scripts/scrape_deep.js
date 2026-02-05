const puppeteer = require('puppeteer');
const path = require('path');
const crypto = require('crypto');
require('dotenv').config({ path: path.join(__dirname, '../frontend/.env.local') });

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function scrape() {
  const user = process.env.PROFARMER_USERNAME;
  const pass = process.env.PROFARMER_PASSWORD;
  const dbUrl = process.env.DATABASE_URL;

  const { Pool } = require('pg');
  const pool = new Pool({ connectionString: dbUrl, ssl: { rejectUnauthorized: false } });

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
    defaultViewport: { width: 1920, height: 1080 },
  });

  const page = await browser.newPage();
  await page.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36');

  // LOGIN
  console.log('=== LOGIN ===');
  await page.goto('https://www.profarmer.com/r/sign-in', { waitUntil: 'networkidle2' });
  await sleep(1000);
  await page.evaluate(() => {
    const forms = document.querySelectorAll('form');
    for (const form of forms) {
      const e = form.querySelector('input[type="email"]');
      if (e && form.querySelector('input[type="password"]')) { e.focus(); return; }
    }
  });
  await page.keyboard.type(user, { delay: 60 });
  await page.keyboard.press('Tab');
  await page.keyboard.type(pass, { delay: 60 });
  await page.keyboard.press('Enter');
  await sleep(6000);

  if (page.url().includes('sign-in')) {
    console.log('LOGIN FAILED');
    process.exit(1);
  }
  console.log('LOGIN OK\n');

  let total = 0;
  const seen = new Set();

  function getTags(text) {
    text = text.toLowerCase();
    const t = [];
    if (text.match(/soy|crush|bean|meal|oil/)) t.push('crush');
    if (text.match(/china|chinese|asia|export/)) t.push('china');
    if (text.match(/corn|ethanol|biofuel|rin|epa|e15|rfs/)) t.push('biofuel');
    if (text.match(/tariff|trade|policy|trump|usda/)) t.push('tariff', 'trump_effect');
    if (text.match(/weather|rain|drought|crop|storm/)) t.push('palm', 'crush');
    if (text.match(/wheat|canola|palm/)) t.push('substitutes');
    if (text.match(/energy|crude/)) t.push('energy');
    if (text.match(/fed|rate|dollar|currency/)) t.push('fed', 'fx');
    if (text.match(/volatil|market|risk/)) t.push('volatility');
    return t.length > 0 ? [...new Set(t)] : ['crush'];
  }

  // Main news archive - go DEEP
  console.log('=== SCRAPING /news ARCHIVE ===');
  
  for (let pg = 1; pg <= 500; pg++) {
    const url = pg === 1 ? 'https://www.profarmer.com/news' : `https://www.profarmer.com/news?page=${pg}`;
    
    try {
      await page.goto(url, { waitUntil: 'networkidle2', timeout: 30000 });
      await sleep(400);

      // Get all article links on page
      const links = await page.evaluate(() => {
        const results = [];
        document.querySelectorAll('a').forEach(a => {
          const href = a.href;
          if (!href.includes('/news/')) return;
          if (href.includes('/topics/') || href.includes('/r/') || href.includes('subscribe')) return;
          const parts = href.replace('https://www.profarmer.com', '').split('/').filter(Boolean);
          if (parts.length < 3) return;
          const title = a.textContent?.trim();
          if (!title || title.length < 10) return;
          results.push({ url: href, title });
        });
        return results;
      });

      const newLinks = links.filter(l => !seen.has(l.url));
      newLinks.forEach(l => seen.add(l.url));

      if (newLinks.length === 0) {
        console.log(`Page ${pg}: END OF ARCHIVE`);
        break;
      }

      console.log(`Page ${pg}: ${newLinks.length} articles`);

      for (const art of newLinks) {
        const hash = crypto.createHash('sha256').update(`pf|${art.url}`).digest('hex');

        try {
          await page.goto(art.url, { waitUntil: 'networkidle2', timeout: 20000 });
          await sleep(150);

          const data = await page.evaluate(() => {
            // Get published date
            let date = '';
            const meta = document.querySelector('meta[property="article:published_time"]');
            if (meta) date = meta.getAttribute('content') || '';
            
            if (!date) {
              document.querySelectorAll('script[type="application/ld+json"]').forEach(s => {
                try {
                  const j = JSON.parse(s.textContent);
                  if (j.datePublished) date = j.datePublished;
                  if (j['@graph']) j['@graph'].forEach(i => { if (i.datePublished) date = i.datePublished; });
                } catch {}
              });
            }

            // Get section from breadcrumb or URL
            let section = 'General';
            const bc = document.querySelector('.Page-breadcrumbs a:last-child, .breadcrumb a:last-child');
            if (bc) section = bc.textContent?.trim() || 'General';

            // Get author
            let author = '';
            const au = document.querySelector('.Page-authorName a, [rel="author"], .author');
            if (au) author = au.textContent?.trim() || '';

            // Get content
            let content = '';
            ['.Page-articleBody', '.RichTextArticleBody', '.Page-content', 'article'].forEach(sel => {
              if (!content || content.length < 200) {
                const el = document.querySelector(sel);
                if (el) content = el.textContent?.trim()?.slice(0, 50000) || '';
              }
            });

            return { date, section, author, content };
          });

          if (!data.content || data.content.length < 50) continue;

          let pubDate = null;
          if (data.date) {
            const d = new Date(data.date);
            if (!isNaN(d.getTime())) pubDate = d.toISOString().split('T')[0];
          }
          if (!pubDate) continue;

          await pool.query(
            `INSERT INTO alt.profarmer_news 
             (event_date, section, headline, content, url, author, specialist_tags, row_hash, raw_payload)
             VALUES ($1::date, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
             ON CONFLICT (row_hash) DO NOTHING`,
            [pubDate, data.section, art.title.slice(0, 1000), data.content, art.url, data.author || null, getTags(art.title + ' ' + art.url), hash, JSON.stringify({ ts: new Date().toISOString() })]
          );
          total++;
          
          if (total % 25 === 0) {
            console.log(`  [${total}] ${pubDate} - ${art.title.slice(0, 40)}...`);
          }
        } catch {}
      }

      await sleep(250);
    } catch (e) {
      console.log(`Page ${pg}: ${e.message.slice(0, 30)}`);
      break;
    }
  }

  console.log(`\n=== DONE: ${total} articles inserted ===`);
  await browser.close();
  await pool.end();
}

scrape().catch(e => { console.error(e); process.exit(1); });
