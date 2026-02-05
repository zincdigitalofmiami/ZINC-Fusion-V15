const puppeteer = require('puppeteer');
const path = require('path');
const crypto = require('crypto');
const axios = require('axios');
const xml2js = require('xml2js');
require('dotenv').config({ path: path.join(__dirname, '../frontend/.env.local') });

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function scrapeSitemap() {
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

  console.log('🔐 Logging in...');
  await page.goto('https://www.profarmer.com/r/sign-in', { waitUntil: 'networkidle2' });
  await sleep(1500);

  await page.evaluate(() => {
    const email = document.querySelector('input[type="email"]');
    if (email) email.focus();
  });

  await page.keyboard.type(user, { delay: 80 });
  await page.keyboard.press('Tab');
  await sleep(500);
  await page.keyboard.type(pass, { delay: 80 });
  await page.keyboard.press('Enter');
  await sleep(8000);

  console.log('✅ Logged in\n');

  let totalInserted = 0;
  let totalSkipped = 0;
  const seenUrls = new Set();

  function getSpecialists(title, url) {
    const text = (title + ' ' + url).toLowerCase();
    const specs = [];
    if (text.match(/soy|crush|bean|meal|oil/)) specs.push('crush');
    if (text.match(/china|chinese|asia|export/)) specs.push('china');
    if (text.match(/corn|ethanol|biofuel|rin|epa/)) specs.push('biofuel');
    if (text.match(/tariff|trade|policy|trump|washington/)) specs.push('tariff', 'trump_effect');
    if (text.match(/weather|rain|drought|crop/)) specs.push('palm', 'crush');
    if (text.match(/wheat|canola|palm/)) specs.push('substitutes');
    if (text.match(/energy|crude|oil/)) specs.push('energy');
    if (text.match(/fed|rate|dollar|currency/)) specs.push('fed', 'fx');
    if (text.match(/volatil|market|risk/)) specs.push('volatility');
    return specs.length > 0 ? [...new Set(specs)] : ['crush'];
  }

  // Generate sitemap URLs for relevant periods (2024-2026 for recent content)
  const sitemaps = [];
  for (let year = 2024; year <= 2026; year++) {
    for (let month = 1; month <= 12; month++) {
      if (year === 2026 && month > 1) break; // Only Jan 2026
      const ym = `${year}${String(month).padStart(2, '0')}`;
      sitemaps.push(`https://www.profarmer.com/sitemap-${ym}.xml`);
    }
  }

  // Also add 2023 for more historical depth
  for (let month = 1; month <= 12; month++) {
    const ym = `2023${String(month).padStart(2, '0')}`;
    sitemaps.push(`https://www.profarmer.com/sitemap-${ym}.xml`);
  }

  console.log(`🗺️  Processing ${sitemaps.length} monthly sitemaps (2023-2026)\n`);
  console.log(`🎯 TARGET: 500+ articles with full metadata\n`);
  console.log('='.repeat(70) + '\n');

  for (const sitemapUrl of sitemaps) {
    const yearMonth = sitemapUrl.match(/sitemap-(\d{6})/)[1];
    console.log(`📅 ${yearMonth.slice(0, 4)}-${yearMonth.slice(4)}`);

    try {
      const response = await axios.get(sitemapUrl, { timeout: 30000 });
      const parser = new xml2js.Parser();
      const result = await parser.parseStringPromise(response.data);

      const urls = result.urlset?.url || [];
      const newsUrls = urls
        .map(u => u.loc[0])
        .filter(url => url.includes('/news/') && !url.includes('/topics/'));

      console.log(`  Found ${newsUrls.length} news URLs`);

      let monthInserted = 0;

      for (const articleUrl of newsUrls) {
        if (seenUrls.has(articleUrl)) {
          totalSkipped++;
          continue;
        }
        seenUrls.add(articleUrl);

        const rowHash = crypto.createHash('sha256').update(`profarmer|${articleUrl}`).digest('hex');

        const exists = await pool.query('SELECT 1 FROM alt.profarmer_news WHERE row_hash = $1', [rowHash]);
        if (exists.rows.length > 0) {
          totalSkipped++;
          continue;
        }

        try {
          await page.goto(articleUrl, { waitUntil: 'networkidle2', timeout: 25000 });
          await sleep(250);

          const data = await page.evaluate(() => {
            let date = '';
            const meta = document.querySelector('meta[property="article:published_time"]');
            if (meta) date = meta.getAttribute('content');

            if (!date) {
              const scripts = document.querySelectorAll('script[type="application/ld+json"]');
              for (const s of scripts) {
                try {
                  const json = JSON.parse(s.textContent);
                  if (json.datePublished) {
                    date = json.datePublished;
                    break;
                  }
                } catch {}
              }
            }

            let author = '';
            const scripts = document.querySelectorAll('script[type="application/ld+json"]');
            for (const s of scripts) {
              try {
                const json = JSON.parse(s.textContent);
                if (json.author && json.author[0] && json.author[0].name) {
                  author = json.author[0].name;
                  break;
                }
              } catch {}
            }

            let content = '';
            const contentEl = document.querySelector('.Page-articleBody');
            if (contentEl) content = contentEl.textContent?.trim().slice(0, 50000);

            let title = '';
            const h1 = document.querySelector('h1');
            if (h1) title = h1.textContent?.trim();

            return { date, author, content, title };
          });

          if (!data.content || data.content.length < 50) continue;
          if (!data.date) continue;

          const pubDate = new Date(data.date).toISOString().split('T')[0];
          const title = data.title || articleUrl.split('/').pop();
          const specialists = getSpecialists(title, articleUrl);

          await pool.query(
            `INSERT INTO alt.profarmer_news 
             (event_date, section, headline, content, url, author, specialist_tags, row_hash, raw_payload)
             VALUES ($1::date, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
             ON CONFLICT (row_hash) DO NOTHING`,
            [
              pubDate,
              yearMonth.slice(0, 4) + '-' + yearMonth.slice(4),
              title.slice(0, 1000),
              data.content,
              articleUrl,
              data.author,
              specialists,
              rowHash,
              JSON.stringify({ scraped_at: new Date().toISOString(), source: 'sitemap' })
            ]
          );

          totalInserted++;
          monthInserted++;

          if (totalInserted <= 20 || totalInserted % 50 === 0) {
            console.log(`  ✅ [${pubDate}] ${title.slice(0, 60)}...`);
          }
        } catch (e) {
          // Continue on error
        }

        if (totalInserted >= 500) {
          console.log(`\n🎯 TARGET REACHED: 500+ articles!\n`);
          break;
        }
      }

      console.log(`  📊 Month total: ${monthInserted} articles (${totalInserted} total)\n`);

      if (totalInserted >= 500) break;

    } catch (e) {
      console.log(`  ❌ Error: ${e.message.slice(0, 60)}\n`);
    }
  }

  console.log('='.repeat(70));
  console.log('📈 FINAL RESULTS');
  console.log('='.repeat(70));
  console.log(`✅ INSERTED:  ${totalInserted}`);
  console.log(`⏭️  SKIPPED:   ${totalSkipped}`);
  console.log(`🔗 TOTAL SEEN: ${seenUrls.size}`);
  console.log('='.repeat(70));

  await browser.close();
  await pool.end();
}

scrapeSitemap().catch(e => {
  console.error('💥 ERROR:', e);
  process.exit(1);
});
