const puppeteer = require('puppeteer');
const path = require('path');
const crypto = require('crypto');
require('dotenv').config({ path: path.join(__dirname, '../frontend/.env.local') });

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function scrape() {
  const user = process.env.PROFARMER_USERNAME;
  const pass = process.env.PROFARMER_PASSWORD;
  const { Pool } = require('pg');
  const pool = new Pool({ connectionString: process.env.DATABASE_URL, ssl: { rejectUnauthorized: false } });

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
    defaultViewport: { width: 1920, height: 1080 },
  });

  const page = await browser.newPage();
  await page.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36');

  // LOGIN
  console.log('LOGGING IN...');
  await page.goto('https://www.profarmer.com/r/sign-in', { waitUntil: 'networkidle2' });
  await sleep(1000);
  await page.evaluate(() => {
    document.querySelectorAll('form').forEach(f => {
      const e = f.querySelector('input[type="email"]');
      if (e && f.querySelector('input[type="password"]')) e.focus();
    });
  });
  await page.keyboard.type(user, { delay: 50 });
  await page.keyboard.press('Tab');
  await page.keyboard.type(pass, { delay: 50 });
  await page.keyboard.press('Enter');
  await sleep(5000);
  console.log('LOGGED IN\n');

  let total = 0;
  const seen = new Set();

  const getTags = (t) => {
    t = t.toLowerCase();
    const r = [];
    if (/soy|crush|bean|meal|oil/.test(t)) r.push('crush');
    if (/china|asia|export/.test(t)) r.push('china');
    if (/corn|ethanol|biofuel|rin|epa|e15/.test(t)) r.push('biofuel');
    if (/tariff|trade|policy|trump|usda/.test(t)) r.push('tariff','trump_effect');
    if (/weather|rain|drought|storm/.test(t)) r.push('palm','crush');
    if (/wheat|canola|palm/.test(t)) r.push('substitutes');
    if (/energy|crude/.test(t)) r.push('energy');
    if (/fed|rate|dollar/.test(t)) r.push('fed','fx');
    if (/volatil|risk/.test(t)) r.push('volatility');
    return r.length ? [...new Set(r)] : ['crush'];
  };

  // ALL POSSIBLE ARCHIVES
  const archives = [
    'https://www.profarmer.com/news',
    'https://www.profarmer.com/topics/first-thing-today',
    'https://www.profarmer.com/topics/ahead-open',
    'https://www.profarmer.com/topics/after-bell',
    'https://www.profarmer.com/topics/daily-advice-monitor',
    'https://www.profarmer.com/topics/weekly-outlook',
    'https://www.profarmer.com/topics/policy-update',
    'https://www.profarmer.com/topics/pro-farmer-editors',
    'https://www.profarmer.com/topics/pro-farmer-crop-tour',
    'https://www.profarmer.com/topics/corn',
    'https://www.profarmer.com/topics/soybeans',
    'https://www.profarmer.com/topics/wheat',
    'https://www.profarmer.com/topics/cattle',
    'https://www.profarmer.com/topics/hogs',
    'https://www.profarmer.com/topics/cotton',
    'https://www.profarmer.com/topics/energy',
    'https://www.profarmer.com/topics/weather',
    'https://www.profarmer.com/topics/trade',
    'https://www.profarmer.com/topics/markets',
    'https://www.profarmer.com/topics/usda',
    'https://www.profarmer.com/topics/exports',
    'https://www.profarmer.com/topics/planting',
    'https://www.profarmer.com/topics/harvest',
  ];

  for (const base of archives) {
    const name = base.split('/').pop();
    console.log(`\n=== ${name.toUpperCase()} ===`);
    
    for (let pg = 1; pg <= 100; pg++) {
      const url = pg === 1 ? base : `${base}?page=${pg}`;
      
      try {
        await page.goto(url, { waitUntil: 'networkidle2', timeout: 25000 });
        await sleep(200);

        const links = await page.evaluate(() => {
          const r = [];
          document.querySelectorAll('a[href*="/news/"]').forEach(a => {
            const h = a.href;
            if (h.includes('/topics/') || h.includes('/r/')) return;
            const p = h.replace('https://www.profarmer.com','').split('/').filter(Boolean);
            if (p.length < 3) return;
            const t = a.textContent?.trim();
            if (t && t.length > 10) r.push({ url: h, title: t });
          });
          return r;
        });

        const fresh = links.filter(l => !seen.has(l.url));
        fresh.forEach(l => seen.add(l.url));

        if (fresh.length === 0) {
          console.log(`  pg${pg}: done`);
          break;
        }

        for (const art of fresh) {
          const hash = crypto.createHash('sha256').update(art.url).digest('hex');

          try {
            await page.goto(art.url, { waitUntil: 'networkidle2', timeout: 15000 });
            
            const d = await page.evaluate(() => {
              let date = document.querySelector('meta[property="article:published_time"]')?.getAttribute('content') || '';
              if (!date) {
                document.querySelectorAll('script[type="application/ld+json"]').forEach(s => {
                  try {
                    const j = JSON.parse(s.textContent);
                    if (j.datePublished) date = j.datePublished;
                    if (j['@graph']) j['@graph'].forEach(i => { if (i.datePublished) date = i.datePublished; });
                  } catch {}
                });
              }
              
              let section = 'News';
              const bc = document.querySelector('.Page-breadcrumbs a, nav a');
              if (bc) section = bc.textContent?.trim() || 'News';

              let content = '';
              ['.Page-articleBody','.Page-content','article','main'].forEach(s => {
                if (!content) { const e = document.querySelector(s); if (e) content = e.textContent?.trim()?.slice(0,50000) || ''; }
              });

              return { date, section, content };
            });

            if (!d.content || d.content.length < 30) continue;
            
            let pubDate = null;
            if (d.date) {
              const dt = new Date(d.date);
              if (!isNaN(dt.getTime())) pubDate = dt.toISOString().split('T')[0];
            }
            if (!pubDate) continue;

            await pool.query(
              `INSERT INTO alt.profarmer_news (event_date,section,headline,content,url,specialist_tags,row_hash,raw_payload)
               VALUES ($1::date,$2,$3,$4,$5,$6,$7,$8::jsonb) ON CONFLICT DO NOTHING`,
              [pubDate, d.section, art.title.slice(0,1000), d.content, art.url, getTags(art.title), hash, '{}']
            );
            total++;
            console.log(`  [${total}] ${pubDate} ${art.title.slice(0,45)}`);
          } catch {}
        }
      } catch (e) {
        break;
      }
    }
    
    if (total >= 500) {
      console.log('\n*** 500+ REACHED ***');
      break;
    }
  }

  console.log(`\n========== TOTAL: ${total} ==========`);
  await browser.close();
  await pool.end();
}

scrape().catch(console.error);
