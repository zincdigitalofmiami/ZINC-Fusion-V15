const puppeteer = require('puppeteer');
const path = require('path');
const crypto = require('crypto');
require('dotenv').config({ path: path.join(__dirname, '../frontend/.env.local') });

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function scrapeHistorical() {
  const user = process.env.PROFARMER_USERNAME;
  const pass = process.env.PROFARMER_PASSWORD;
  const dbUrl = process.env.DATABASE_URL;

  const { Pool } = require('pg');
  const pool = new Pool({ connectionString: dbUrl, ssl: { rejectUnauthorized: false } });

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu'],
    defaultViewport: { width: 1920, height: 1080 },
  });

  const page = await browser.newPage();
  await page.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36');

  console.log('🔐 Logging in...');
  await page.goto('https://www.profarmer.com/r/sign-in', { waitUntil: 'networkidle2' });
  await sleep(1500);

  await page.evaluate(() => {
    const forms = document.querySelectorAll('form');
    for (const form of forms) {
      const email = form.querySelector('input[type="email"]');
      if (email) {
        email.focus();
        return;
      }
    }
  });

  await page.keyboard.type(user, { delay: 80 });
  await page.keyboard.press('Tab');
  await sleep(500);
  await page.keyboard.type(pass, { delay: 80 });
  await page.keyboard.press('Enter');
  await sleep(8000);

  if (page.url().includes('sign-in')) {
    console.error('❌ LOGIN FAILED');
    await browser.close();
    await pool.end();
    process.exit(1);
  }
  console.log('✅ Logged in\n');

  let totalInserted = 0;
  let totalSkipped = 0;
  const seenUrls = new Set();

  function getSpecialists(title, url) {
    const text = (title + ' ' + url).toLowerCase();
    const specs = [];
    if (text.match(/soy|crush|bean|meal|oil/)) specs.push('crush');
    if (text.match(/china|chinese|asia|export/)) specs.push('china');
    if (text.match(/corn|ethanol|biofuel|rin|epa|biodiesel/)) specs.push('biofuel');
    if (text.match(/tariff|trade|policy|trump|washington|usda/)) specs.push('tariff', 'trump_effect');
    if (text.match(/weather|rain|drought|crop|storm/)) specs.push('palm', 'crush');
    if (text.match(/wheat|canola|palm|sunflower/)) specs.push('substitutes');
    if (text.match(/energy|crude|oil price|diesel/)) specs.push('energy');
    if (text.match(/fed|rate|dollar|currency|powell/)) specs.push('fed', 'fx');
    if (text.match(/volatil|market|risk|option/)) specs.push('volatility');
    return specs.length > 0 ? [...new Set(specs)] : ['crush'];
  }

  // DEEP HISTORICAL SCRAPING - START FROM HIGH PAGE NUMBERS
  console.log('🎯 Target: 500+ articles with complete metadata\n');
  console.log('Strategy: Start from recent pages (10-100) to find NEW historical content\n');
  console.log('=' + '='.repeat(60) + '\n');

  const START_PAGE = 10;
  const END_PAGE = 150;
  
  for (let pageNum = START_PAGE; pageNum <= END_PAGE; pageNum++) {
    const listUrl = `https://www.profarmer.com/news?page=${pageNum}`;
    
    try {
      await page.goto(listUrl, { waitUntil: 'networkidle2', timeout: 30000 });
      await sleep(400);

      const articles = await page.evaluate(() => {
        const results = [];
        document.querySelectorAll('a[href*="/news/"]').forEach(a => {
          const href = a.href;
          if (href.includes('/r/') || href.includes('subscribe') || href.includes('/topics/')) return;
          const parts = href.replace('https://www.profarmer.com', '').split('/').filter(Boolean);
          if (parts.length < 3) return;
          const title = a.textContent?.trim();
          if (title && title.length > 10 && title.length < 500) {
            results.push({ url: href, title });
          }
        });
        return results;
      });

      const newArticles = articles.filter(a => !seenUrls.has(a.url));
      newArticles.forEach(a => seenUrls.add(a.url));

      if (newArticles.length === 0) {
        console.log(`📄 Page ${pageNum}: No new articles`);
        continue;
      }

      console.log(`📄 Page ${pageNum}: ${newArticles.length} new articles`);

      for (const article of newArticles) {
        const rowHash = crypto.createHash('sha256').update(`profarmer|${article.url}`).digest('hex');

        const exists = await pool.query('SELECT 1 FROM alt.profarmer_news WHERE row_hash = $1', [rowHash]);
        if (exists.rows.length > 0) {
          totalSkipped++;
          continue;
        }

        let content = '';
        let pubDate = null;
        let author = null;

        try {
          await page.goto(article.url, { waitUntil: 'networkidle2', timeout: 25000 });
          await sleep(300);

          const pageData = await page.evaluate(() => {
            // Date
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

            // Author
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

            // Content
            let content = '';
            const contentEl = document.querySelector('.Page-articleBody');
            if (contentEl) content = contentEl.textContent?.trim().slice(0, 50000);

            return { date, content, author };
          });

          content = pageData.content;
          author = pageData.author || null;

          if (pageData.date) {
            const parsed = new Date(pageData.date);
            if (!isNaN(parsed.getTime())) {
              pubDate = parsed.toISOString().split('T')[0];
            }
          }
        } catch (e) {
          // Skip on error
        }

        if (!content || content.length < 50) continue;
        if (!pubDate) continue;

        const specialists = getSpecialists(article.title, article.url);

        try {
          await pool.query(
            `INSERT INTO alt.profarmer_news 
             (event_date, section, headline, content, url, author, specialist_tags, row_hash, raw_payload)
             VALUES ($1::date, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
             ON CONFLICT (row_hash) DO NOTHING`,
            [
              pubDate,
              'All News',
              article.title.slice(0, 1000),
              content,
              article.url,
              author,
              specialists,
              rowHash,
              JSON.stringify({ scraped_at: new Date().toISOString() })
            ]
          );
          
          totalInserted++;
          console.log(`  ✅ [${pubDate}] ${article.title.slice(0, 60)}...`);
        } catch (e) {
          if (!e.message.includes('duplicate')) {
            console.log(`  ❌ ${e.message.slice(0, 50)}`);
          }
          totalSkipped++;
        }
      }

      if (pageNum % 10 === 0) {
        console.log(`\n📊 Progress: ${totalInserted} inserted, ${totalSkipped} skipped, ${seenUrls.size} URLs seen\n`);
      }

      await sleep(300);
    } catch (e) {
      console.log(`❌ Page ${pageNum}: ${e.message.slice(0, 50)}`);
      break;
    }
  }

  console.log('\n' + '='.repeat(60));
  console.log('📈 SCRAPING COMPLETE');
  console.log('='.repeat(60));
  console.log(`✅ INSERTED:  ${totalInserted}`);
  console.log(`⏭️  SKIPPED:   ${totalSkipped}`);
  console.log(`🔗 TOTAL URLS: ${seenUrls.size}`);
  console.log('='.repeat(60));

  await browser.close();
  await pool.end();
}

scrapeHistorical().catch(e => {
  console.error('💥 FATAL:', e);
  process.exit(1);
});
