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
      const emailInput = form.querySelector('input[type="email"]');
      if (emailInput && form.querySelector('input[type="password"]')) {
        emailInput.focus();
        return;
      }
    }
  });

  await page.keyboard.type(user, { delay: 40 });
  await page.keyboard.press('Tab');
  await sleep(100);
  await page.keyboard.type(pass, { delay: 40 });
  await page.keyboard.press('Enter');
  await sleep(5000);

  if (page.url().includes('sign-in')) {
    console.log('LOGIN FAILED!');
    await browser.close();
    return;
  }
  console.log('LOGIN SUCCESS!\n');

  let totalInserted = 0;
  let totalSkipped = 0;
  const seenUrls = new Set();
  
  // Specialist mapping based on keywords
  function getSpecialists(title, url) {
    const text = (title + ' ' + url).toLowerCase();
    const specs = [];
    if (text.match(/soy|crush|bean|meal|oil/)) specs.push('crush');
    if (text.match(/china|chinese|asia|export/)) specs.push('china');
    if (text.match(/corn|ethanol|biofuel|rin|epa/)) specs.push('biofuel');
    if (text.match(/tariff|trade|policy|trump|washington/)) specs.push('tariff', 'trump_effect');
    if (text.match(/weather|rain|drought|crop/)) specs.push('palm', 'crush');
    if (text.match(/wheat|canola|palm/)) specs.push('substitutes');
    if (text.match(/energy|crude|oil price/)) specs.push('energy');
    if (text.match(/fed|rate|dollar|currency/)) specs.push('fed', 'fx');
    if (text.match(/volatil|market|technical/)) specs.push('volatility');
    return specs.length > 0 ? [...new Set(specs)] : ['crush'];
  }

  // SCRAPE BY FINDING ALL ARTICLE LINKS
  const startUrls = [
    'https://www.profarmer.com/',
    'https://www.profarmer.com/topics/first-thing-today',
    'https://www.profarmer.com/topics/ahead-open',
    'https://www.profarmer.com/topics/pro-farmer-editors',
  ];

  for (const startUrl of startUrls) {
    console.log(`\n=== CRAWLING FROM: ${startUrl} ===`);
    
    for (let pageNum = 1; pageNum <= 100; pageNum++) {
      const pageUrl = pageNum === 1 ? startUrl : `${startUrl}/page/${pageNum}/`;
      
      try {
        await page.goto(pageUrl, { waitUntil: 'networkidle2', timeout: 30000 });
        await sleep(500);
        
        // Find ALL article links (any link with a date pattern in URL)
        const articleUrls = await page.evaluate(() => {
          const urls = [];
          document.querySelectorAll('a[href*="profarmer.com"]').forEach(a => {
            const href = a.href;
            // Match article URLs: /YYYY/MM/DD/ or /YYYY/MM/
            if (href.match(/profarmer\.com\/\d{4}\/\d{2}\//) && 
                !href.includes('/r/') && 
                !href.includes('subscribe')) {
              const title = a.textContent?.trim() || '';
              if (title.length > 10) {
                urls.push({ url: href, title });
              }
            }
          });
          return urls;
        });

        // Dedupe
        const newArticles = articleUrls.filter(a => !seenUrls.has(a.url));
        newArticles.forEach(a => seenUrls.add(a.url));

        if (newArticles.length === 0) {
          console.log(`  Page ${pageNum}: No new articles, stopping`);
          break;
        }

        console.log(`  Page ${pageNum}: ${newArticles.length} new articles`);

        // Scrape each article
        for (const article of newArticles) {
          // Extract date from URL
          const dateMatch = article.url.match(/\/(\d{4})\/(\d{2})\/(\d{2})\//);
          const pubDate = dateMatch ? `${dateMatch[1]}-${dateMatch[2]}-${dateMatch[3]}` : 
                          new Date().toISOString().split('T')[0];

          const rowHash = crypto.createHash('sha256')
            .update(`${article.url}|${article.title}|${pubDate}`)
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

          // Get full content
          let content = '';
          try {
            await page.goto(article.url, { waitUntil: 'networkidle2', timeout: 25000 });
            await sleep(200);

            content = await page.evaluate(() => {
              // Try multiple content selectors
              const selectors = [
                '.RichTextArticleBody',
                '.RichTextBody', 
                '.entry-content',
                '.article-body',
                '.post-content',
                'article .content',
                'main article',
                'article'
              ];
              for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el && el.textContent.length > 100) {
                  return el.textContent.trim().slice(0, 20000);
                }
              }
              // Fallback: get all paragraphs
              const paras = Array.from(document.querySelectorAll('p'))
                .map(p => p.textContent.trim())
                .filter(t => t.length > 50)
                .join('\n\n');
              return paras.slice(0, 20000);
            });
          } catch (e) {
            console.log(`    ! Failed to get content: ${e.message}`);
          }

          if (content.length < 50) {
            console.log(`    - Skipping (no content): ${article.title.slice(0, 50)}`);
            continue;
          }

          const specialists = getSpecialists(article.title, article.url);

          // Insert
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
                JSON.stringify({ scraped_at: new Date().toISOString() }),
                rowHash
              ]
            );
            totalInserted++;
            console.log(`    + [${pubDate}] ${article.title.slice(0, 55)}...`);
          } catch (e) {
            console.log(`    ! DB error: ${e.message.slice(0, 80)}`);
          }
        }

        await sleep(800);
      } catch (e) {
        console.log(`  Page ${pageNum}: ${e.message}`);
        break;
      }
    }
  }

  console.log('\n=============================');
  console.log(`TOTAL INSERTED: ${totalInserted}`);
  console.log(`TOTAL SKIPPED:  ${totalSkipped}`);
  console.log(`TOTAL SEEN:     ${seenUrls.size}`);
  console.log('=============================');

  await browser.close();
  await pool.end();
}

scrapeAll().catch(e => {
  console.error('FATAL:', e);
  process.exit(1);
});
