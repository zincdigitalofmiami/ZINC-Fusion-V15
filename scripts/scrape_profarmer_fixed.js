const puppeteer = require('puppeteer');
const path = require('path');
const crypto = require('crypto');
require('dotenv').config({ path: path.join(__dirname, '../frontend/.env.local') });

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function scrapeAll() {
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
  console.log('=== LOGGING IN ===');
  await page.goto('https://www.profarmer.com/r/sign-in', { waitUntil: 'networkidle2' });
  await sleep(1000);
  await page.evaluate(() => {
    const forms = document.querySelectorAll('form');
    for (const form of forms) {
      const e = form.querySelector('input[type="email"]');
      if (e && form.querySelector('input[type="password"]')) { e.focus(); return; }
    }
  });
  await page.keyboard.type(user, { delay: 30 });
  await page.keyboard.press('Tab');
  await page.keyboard.type(pass, { delay: 30 });
  await page.keyboard.press('Enter');
  await sleep(5000);

  if (page.url().includes('sign-in')) {
    console.log('LOGIN FAILED!');
    process.exit(1);
  }
  console.log('LOGIN SUCCESS!\n');

  let totalInserted = 0;
  let totalSkipped = 0;
  const seenUrls = new Set();

  function getSpecialists(title, url) {
    const text = (title + ' ' + url).toLowerCase();
    const specs = [];
    if (text.match(/soy|crush|bean|meal|oil/)) specs.push('crush');
    if (text.match(/china|chinese|asia|export/)) specs.push('china');
    if (text.match(/corn|ethanol|biofuel|rin|epa|e15|rfs/)) specs.push('biofuel');
    if (text.match(/tariff|trade|policy|trump|washington|usda/)) specs.push('tariff', 'trump_effect');
    if (text.match(/weather|rain|drought|crop|storm|winter/)) specs.push('palm', 'crush');
    if (text.match(/wheat|canola|palm/)) specs.push('substitutes');
    if (text.match(/energy|crude|oil price/)) specs.push('energy');
    if (text.match(/fed|rate|dollar|currency|warsh/)) specs.push('fed', 'fx');
    if (text.match(/volatil|market|risk/)) specs.push('volatility');
    return specs.length > 0 ? [...new Set(specs)] : ['crush'];
  }

  // ALL CONTENT SECTIONS TO SCRAPE
  const sections = [
    { name: 'First Thing Today', listUrl: 'https://www.profarmer.com/topics/first-thing-today' },
    { name: 'Ahead of the Open', listUrl: 'https://www.profarmer.com/topics/ahead-open' },
    { name: 'Daily Advice Monitor', listUrl: 'https://www.profarmer.com/news/advice-monitor/pro-farmers-daily-advice-monitor' },
    { name: 'Washington/Ag Policy', listUrl: 'https://www.profarmer.com/news/policy-update' },
    { name: 'Pro Farmer Editors', listUrl: 'https://www.profarmer.com/topics/pro-farmer-editors' },
    { name: 'Crop Tour', listUrl: 'https://www.profarmer.com/topics/pro-farmer-crop-tour' },
    { name: 'Home', listUrl: 'https://www.profarmer.com/' },
  ];

  for (const section of sections) {
    console.log(`\n=== ${section.name} ===`);
    
    // Navigate through pagination
    for (let pageNum = 1; pageNum <= 200; pageNum++) {
      const listUrl = pageNum === 1 ? section.listUrl : `${section.listUrl}?page=${pageNum}`;
      
      try {
        await page.goto(listUrl, { waitUntil: 'networkidle2', timeout: 30000 });
        await sleep(500);

        // Find article links - pattern: /news/category/article-slug
        const articles = await page.evaluate(() => {
          const results = [];
          const links = document.querySelectorAll('a[href*="/news/"]');
          
          for (const a of links) {
            const href = a.href;
            // Skip category pages (only 2 path segments after /news/)
            const pathParts = href.replace('https://www.profarmer.com', '').split('/').filter(Boolean);
            if (pathParts.length < 3) continue; // Need: news / category / article-slug
            if (href.includes('/r/') || href.includes('subscribe')) continue;
            
            const title = a.textContent?.trim();
            if (!title || title.length < 15) continue;
            
            results.push({ url: href, title });
          }
          return results;
        });

        // Dedupe
        const newArticles = articles.filter(a => !seenUrls.has(a.url));
        newArticles.forEach(a => seenUrls.add(a.url));

        if (newArticles.length === 0) {
          console.log(`  Page ${pageNum}: No new articles, moving on`);
          break;
        }

        console.log(`  Page ${pageNum}: ${newArticles.length} new articles`);

        // Scrape each article
        for (const article of newArticles) {
          const rowHash = crypto.createHash('sha256')
            .update(`${article.url}|${article.title}`)
            .digest('hex');

          // Check if exists
          const exists = await pool.query(
            'SELECT 1 FROM alt.news_1d WHERE row_hash = $1 LIMIT 1',
            [rowHash]
          );

          if (exists.rows.length > 0) {
            totalSkipped++;
            continue;
          }

          // Get full content and date
          let content = '';
          let pubDate = new Date().toISOString().split('T')[0];
          
          try {
            await page.goto(article.url, { waitUntil: 'networkidle2', timeout: 25000 });
            await sleep(300);

            const pageData = await page.evaluate(() => {
              // Get date
              let date = '';
              const dateEl = document.querySelector('.PagePromo-date, time, [datetime], .date');
              if (dateEl) {
                date = dateEl.getAttribute('datetime') || dateEl.textContent?.trim() || '';
              }
              
              // Get content from RichTextBody
              let content = '';
              const contentEl = document.querySelector('.RichTextArticleBody, .RichTextBody, article');
              if (contentEl) {
                content = contentEl.textContent?.trim()?.slice(0, 25000) || '';
              }
              
              if (!content) {
                content = Array.from(document.querySelectorAll('p'))
                  .map(p => p.textContent?.trim())
                  .filter(t => t && t.length > 30)
                  .join('\n\n')
                  .slice(0, 25000);
              }
              
              return { date, content };
            });

            content = pageData.content;
            if (pageData.date) {
              // Parse date
              const parsed = new Date(pageData.date);
              if (!isNaN(parsed.getTime())) {
                pubDate = parsed.toISOString().split('T')[0];
              }
            }
          } catch (e) {
            console.log(`    ! Error: ${e.message.slice(0, 50)}`);
          }

          if (content.length < 100) {
            continue;
          }

          const specialists = getSpecialists(article.title, article.url);

          try {
            await pool.query(
              `INSERT INTO alt.news_1d (event_date, source, headline, content, url, specialist_tags, raw_payload, row_hash)
               VALUES ($1::date, 'profarmer', $2, $3, $4, $5, $6::jsonb, $7)`,
              [
                pubDate,
                article.title.slice(0, 500),
                content,
                article.url,
                specialists,
                JSON.stringify({ section: section.name, scraped_at: new Date().toISOString() }),
                rowHash
              ]
            );
            totalInserted++;
            console.log(`    + [${pubDate}] ${article.title.slice(0, 50)}...`);
          } catch (e) {
            console.log(`    ! DB: ${e.message.slice(0, 60)}`);
          }
        }

        await sleep(600);
      } catch (e) {
        console.log(`  Page ${pageNum} error: ${e.message.slice(0, 50)}`);
        break;
      }
    }
  }

  console.log('\n================================');
  console.log(`TOTAL INSERTED: ${totalInserted}`);
  console.log(`TOTAL SKIPPED:  ${totalSkipped}`);
  console.log(`TOTAL UNIQUE:   ${seenUrls.size}`);
  console.log('================================');

  await browser.close();
  await pool.end();
}

scrapeAll().catch(e => {
  console.error('FATAL:', e);
  process.exit(1);
});
