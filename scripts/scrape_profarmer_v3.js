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
  await page.keyboard.type(user, { delay: 25 });
  await page.keyboard.press('Tab');
  await page.keyboard.type(pass, { delay: 25 });
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
    
    for (let pageNum = 1; pageNum <= 500; pageNum++) {
      const listUrl = pageNum === 1 ? section.listUrl : `${section.listUrl}?page=${pageNum}`;
      
      try {
        await page.goto(listUrl, { waitUntil: 'networkidle2', timeout: 30000 });
        await sleep(400);

        // Find article links
        const articles = await page.evaluate(() => {
          const results = [];
          const links = document.querySelectorAll('a[href*="/news/"]');
          
          for (const a of links) {
            const href = a.href;
            const pathParts = href.replace('https://www.profarmer.com', '').split('/').filter(Boolean);
            if (pathParts.length < 3) continue;
            if (href.includes('/r/') || href.includes('subscribe')) continue;
            
            const title = a.textContent?.trim();
            if (!title || title.length < 15) continue;
            
            results.push({ url: href, title });
          }
          return results;
        });

        const newArticles = articles.filter(a => !seenUrls.has(a.url));
        newArticles.forEach(a => seenUrls.add(a.url));

        if (newArticles.length === 0) {
          console.log(`  Page ${pageNum}: No new articles`);
          break;
        }

        console.log(`  Page ${pageNum}: ${newArticles.length} articles to scrape`);

        for (const article of newArticles) {
          const rowHash = crypto.createHash('sha256')
            .update(`profarmer|${article.url}`)
            .digest('hex');

          // Check if exists in NEW table
          const exists = await pool.query(
            'SELECT 1 FROM alt.profarmer_news WHERE row_hash = $1 LIMIT 1',
            [rowHash]
          );

          if (exists.rows.length > 0) {
            totalSkipped++;
            continue;
          }

          let content = '';
          let pubDate = null;
          let author = null;
          
          try {
            await page.goto(article.url, { waitUntil: 'networkidle2', timeout: 20000 });
            await sleep(200);

            const pageData = await page.evaluate(() => {
              // Get date from meta tag (ISO format)
              let date = '';
              const metaDate = document.querySelector('meta[property="article:published_time"]');
              if (metaDate) {
                date = metaDate.getAttribute('content') || '';
              }
              
              // Fallback to JSON-LD
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
              
              // Fallback to .Page-datePublished
              if (!date) {
                const dateEl = document.querySelector('.Page-datePublished');
                if (dateEl) date = dateEl.textContent?.trim() || '';
              }
              
              // Get author
              let author = '';
              const authorEl = document.querySelector('.Page-authorName, .byline a, [rel="author"]');
              if (authorEl) author = authorEl.textContent?.trim() || '';
              
              // Get content
              let content = '';
              const contentEl = document.querySelector('.RichTextArticleBody, .RichTextBody');
              if (contentEl) {
                content = contentEl.textContent?.trim()?.slice(0, 50000) || '';
              }
              
              if (!content || content.length < 100) {
                const article = document.querySelector('article');
                if (article) content = article.textContent?.trim()?.slice(0, 50000) || '';
              }
              
              return { date, content, author };
            });

            content = pageData.content;
            author = pageData.author || null;
            
            // Parse date
            if (pageData.date) {
              let parsed = new Date(pageData.date);
              if (isNaN(parsed.getTime())) {
                // Try natural language: "January 30, 2026 06:15 AM"
                const match = pageData.date.match(/(\w+)\s+(\d+),?\s+(\d{4})/);
                if (match) {
                  parsed = new Date(`${match[1]} ${match[2]}, ${match[3]}`);
                }
              }
              if (!isNaN(parsed.getTime())) {
                pubDate = parsed.toISOString().split('T')[0];
              }
            }
          } catch (e) {
            console.log(`    ! Error: ${e.message.slice(0, 40)}`);
          }

          if (!content || content.length < 100) {
            console.log(`    - No content: ${article.title.slice(0, 35)}`);
            continue;
          }
          if (!pubDate) {
            console.log(`    - No date: ${article.title.slice(0, 35)}`);
            continue;
          }

          const specialists = getSpecialists(article.title, article.url);

          try {
            await pool.query(
              `INSERT INTO alt.profarmer_news 
               (event_date, section, headline, content, url, author, specialist_tags, row_hash, raw_payload)
               VALUES ($1::date, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)`,
              [
                pubDate,
                section.name,
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
            console.log(`    + [${pubDate}] ${article.title.slice(0, 45)}...`);
          } catch (e) {
            if (e.message.includes('duplicate')) {
              totalSkipped++;
            } else {
              console.log(`    ! ${e.message.slice(0, 50)}`);
            }
          }
        }

        await sleep(400);
      } catch (e) {
        console.log(`  Page ${pageNum}: ${e.message.slice(0, 40)}`);
        break;
      }
    }
  }

  console.log('\n========================================');
  console.log(`TOTAL INSERTED: ${totalInserted}`);
  console.log(`TOTAL SKIPPED:  ${totalSkipped}`);
  console.log(`TOTAL SEEN:     ${seenUrls.size}`);
  console.log('========================================');

  await browser.close();
  await pool.end();
}

scrapeAll().catch(e => {
  console.error('FATAL:', e);
  process.exit(1);
});
