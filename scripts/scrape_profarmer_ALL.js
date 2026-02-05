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
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu'],
    defaultViewport: { width: 1920, height: 1080 },
  });

  const page = await browser.newPage();
  await page.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');

  // === LOGIN ===
  console.log('=== LOGGING IN ===');
  await page.goto('https://www.profarmer.com/r/sign-in', { waitUntil: 'networkidle2' });
  await sleep(1000);
  await page.evaluate(() => {
    const forms = document.querySelectorAll('form');
    for (const form of forms) {
      const emailInput = form.querySelector('input[type="email"]');
      if (emailInput && form.querySelector('input[type="password"]')) {
        emailInput.focus();
        emailInput.click();
        return;
      }
    }
  });
  await page.keyboard.type(user, { delay: 80 });
  await sleep(400);
  await page.keyboard.press('Tab');
  await sleep(400);
  await page.keyboard.type(pass, { delay: 80 });
  await sleep(400);
  await page.keyboard.press('Enter');
  await sleep(8000);

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

  // COMPREHENSIVE SECTION LIST - ALL CONTENT AREAS
  const sections = [
    { name: 'First Thing Today', listUrl: 'https://www.profarmer.com/topics/first-thing-today' },
    { name: 'Ahead of the Open', listUrl: 'https://www.profarmer.com/topics/ahead-open' },
    { name: 'After the Bell', listUrl: 'https://www.profarmer.com/topics/after-bell' },
    { name: 'Daily Advice Monitor', listUrl: 'https://www.profarmer.com/topics/daily-advice-monitor' },
    { name: 'Weekly Outlook', listUrl: 'https://www.profarmer.com/topics/weekly-outlook' },
    { name: 'Washington/Ag Policy', listUrl: 'https://www.profarmer.com/topics/policy-update' },
    { name: 'Pro Farmer Editors', listUrl: 'https://www.profarmer.com/topics/pro-farmer-editors' },
    { name: 'Crop Tour', listUrl: 'https://www.profarmer.com/topics/pro-farmer-crop-tour' },
    { name: 'Corn', listUrl: 'https://www.profarmer.com/topics/corn' },
    { name: 'Soybeans', listUrl: 'https://www.profarmer.com/topics/soybeans' },
    { name: 'Wheat', listUrl: 'https://www.profarmer.com/topics/wheat' },
    { name: 'Cattle', listUrl: 'https://www.profarmer.com/topics/cattle' },
    { name: 'Hogs', listUrl: 'https://www.profarmer.com/topics/hogs' },
    { name: 'Cotton', listUrl: 'https://www.profarmer.com/topics/cotton' },
    { name: 'Energy', listUrl: 'https://www.profarmer.com/topics/energy' },
    { name: 'Weather', listUrl: 'https://www.profarmer.com/topics/weather' },
    { name: 'Trade', listUrl: 'https://www.profarmer.com/topics/trade' },
    { name: 'All News', listUrl: 'https://www.profarmer.com/news' },
  ];

  for (const section of sections) {
    console.log(`\n=== ${section.name} ===`);
    let emptyPages = 0;
    
    for (let pageNum = 1; pageNum <= 200; pageNum++) {
      const listUrl = pageNum === 1 ? section.listUrl : `${section.listUrl}?page=${pageNum}`;
      
      try {
        await page.goto(listUrl, { waitUntil: 'networkidle2', timeout: 30000 });
        await sleep(300);

        const articles = await page.evaluate(() => {
          const results = [];
          const links = document.querySelectorAll('a[href*="/news/"]');
          for (const a of links) {
            const href = a.href;
            if (href.includes('/r/') || href.includes('subscribe') || href.includes('/topics/')) continue;
            const pathParts = href.replace('https://www.profarmer.com', '').split('/').filter(Boolean);
            if (pathParts.length < 3) continue;
            const title = a.textContent?.trim();
            if (!title || title.length < 10) continue;
            results.push({ url: href, title });
          }
          return results;
        });

        const newArticles = articles.filter(a => !seenUrls.has(a.url));
        newArticles.forEach(a => seenUrls.add(a.url));

        if (newArticles.length === 0) {
          emptyPages++;
          if (emptyPages >= 2) {
            console.log(`  Page ${pageNum}: No more articles`);
            break;
          }
          continue;
        }
        emptyPages = 0;

        console.log(`  Page ${pageNum}: ${newArticles.length} new articles`);

        for (const article of newArticles) {
          const rowHash = crypto.createHash('sha256').update(`profarmer|${article.url}`).digest('hex');

          const exists = await pool.query('SELECT 1 FROM alt.profarmer_news WHERE row_hash = $1 LIMIT 1', [rowHash]);
          if (exists.rows.length > 0) {
            totalSkipped++;
            continue;
          }

          let content = '';
          let pubDate = null;
          let author = null;
          
          try {
            await page.goto(article.url, { waitUntil: 'networkidle2', timeout: 25000 });
            await sleep(200);

            const pageData = await page.evaluate(() => {
              let date = '';
              const metaDate = document.querySelector('meta[property="article:published_time"]');
              if (metaDate) date = metaDate.getAttribute('content') || '';
              
              if (!date) {
                const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                for (const s of scripts) {
                  try {
                    const json = JSON.parse(s.textContent);
                    if (json.datePublished) { date = json.datePublished; break; }
                    if (json['@graph']) {
                      for (const item of json['@graph']) {
                        if (item.datePublished) { date = item.datePublished; break; }
                      }
                    }
                  } catch {}
                }
              }
              
              if (!date) {
                const dateEl = document.querySelector('.Page-datePublished, time, [datetime]');
                if (dateEl) date = dateEl.getAttribute('datetime') || dateEl.textContent?.trim() || '';
              }
              
              let author = '';
              const authorEl = document.querySelector('.Page-authorName a, .byline a, [rel="author"], .author');
              if (authorEl) author = authorEl.textContent?.trim() || '';
              
              let content = '';
              const selectors = ['.Page-articleBody', '.RichTextArticleBody', '.RichTextBody', '.Page-content', 'article', 'main'];
              for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el && el.textContent?.length > 200) {
                  content = el.textContent.trim().slice(0, 50000);
                  break;
                }
              }
              
              return { date, content, author };
            });

            content = pageData.content;
            author = pageData.author || null;
            
            if (pageData.date) {
              let parsed = new Date(pageData.date);
              if (isNaN(parsed.getTime())) {
                const match = pageData.date.match(/(\w+)\s+(\d+),?\s+(\d{4})/);
                if (match) parsed = new Date(`${match[1]} ${match[2]}, ${match[3]}`);
              }
              if (!isNaN(parsed.getTime())) pubDate = parsed.toISOString().split('T')[0];
            }
          } catch (e) {
            // Skip errors silently for speed
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
              [pubDate, section.name, article.title.slice(0, 1000), content, article.url, author, specialists, rowHash, JSON.stringify({ scraped_at: new Date().toISOString() })]
            );
            totalInserted++;
            if (totalInserted % 10 === 0) {
              console.log(`    [${totalInserted}] ${pubDate} - ${article.title.slice(0, 40)}...`);
            }
          } catch (e) {
            totalSkipped++;
          }
        }

        await sleep(200);
      } catch (e) {
        console.log(`  Page ${pageNum}: Error - ${e.message.slice(0, 30)}`);
        break;
      }
    }
  }

  console.log('\n========================================');
  console.log(`TOTAL INSERTED: ${totalInserted}`);
  console.log(`TOTAL SKIPPED:  ${totalSkipped}`);
  console.log(`TOTAL URLS SEEN: ${seenUrls.size}`);
  console.log('========================================');

  await browser.close();
  await pool.end();
}

scrapeAll().catch(e => { console.error('FATAL:', e); process.exit(1); });
