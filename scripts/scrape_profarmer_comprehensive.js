const puppeteer = require('puppeteer');
const path = require('path');
const crypto = require('crypto');
require('dotenv').config({ path: path.join(__dirname, '../frontend/.env.local') });

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function scrapeComprehensive() {
  const user = process.env.PROFARMER_USERNAME;
  const pass = process.env.PROFARMER_PASSWORD;
  const dbUrl = process.env.DATABASE_URL;

  if (!user || !pass || !dbUrl) {
    console.error('Missing env vars: PROFARMER_USERNAME, PROFARMER_PASSWORD, DATABASE_URL');
    process.exit(1);
  }

  const { Pool } = require('pg');
  const pool = new Pool({ connectionString: dbUrl, ssl: { rejectUnauthorized: false } });

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu'],
    defaultViewport: { width: 1920, height: 1080 },
  });

  const page = await browser.newPage();
  await page.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');

  // === LOGIN (KEYBOARD METHOD) ===
  console.log('=== LOGGING IN TO PROFARMER ===');
  await page.goto('https://www.profarmer.com/r/sign-in', { waitUntil: 'networkidle2' });
  await sleep(1500);

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
  await sleep(500);
  await page.keyboard.press('Tab');
  await sleep(500);
  await page.keyboard.type(pass, { delay: 80 });
  await sleep(500);
  await page.keyboard.press('Enter');
  await sleep(8000);

  if (page.url().includes('sign-in')) {
    console.error('❌ LOGIN FAILED! URL:', page.url());
    await browser.close();
    await pool.end();
    process.exit(1);
  }
  console.log('✅ LOGIN SUCCESS!\n');

  let totalInserted = 0;
  let totalSkipped = 0;
  let totalErrors = 0;
  const seenUrls = new Set();

  function getSpecialists(title, url) {
    const text = (title + ' ' + url).toLowerCase();
    const specs = [];
    if (text.match(/soy|crush|bean|meal|oil/)) specs.push('crush');
    if (text.match(/china|chinese|asia|export|beijing/)) specs.push('china');
    if (text.match(/corn|ethanol|biofuel|rin|epa|e15|rfs|biodiesel/)) specs.push('biofuel');
    if (text.match(/tariff|trade|policy|trump|washington|usda|section 301/)) specs.push('tariff', 'trump_effect');
    if (text.match(/weather|rain|drought|crop|storm|winter|forecast/)) specs.push('palm', 'crush');
    if (text.match(/wheat|canola|palm|sunflower|rapeseed/)) specs.push('substitutes');
    if (text.match(/energy|crude|oil price|refin|diesel/)) specs.push('energy');
    if (text.match(/fed|rate|dollar|currency|warsh|powell|interest/)) specs.push('fed', 'fx');
    if (text.match(/volatil|market|risk|option|hedge/)) specs.push('volatility');
    return specs.length > 0 ? [...new Set(specs)] : ['crush'];
  }

  // COMPREHENSIVE SECTION LIST - ALL CONTENT AREAS + PAGINATION
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
    { name: 'Markets', listUrl: 'https://www.profarmer.com/topics/markets' },
    { name: 'All News', listUrl: 'https://www.profarmer.com/news' },
  ];

  for (const section of sections) {
    console.log(`\n${'='.repeat(60)}`);
    console.log(`📁 SECTION: ${section.name}`);
    console.log(`${'='.repeat(60)}`);
    
    let emptyPages = 0;
    let sectionInserted = 0;
    
    for (let pageNum = 1; pageNum <= 100; pageNum++) {
      const listUrl = pageNum === 1 ? section.listUrl : `${section.listUrl}?page=${pageNum}`;
      
      try {
        await page.goto(listUrl, { waitUntil: 'networkidle2', timeout: 30000 });
        await sleep(400);

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
          if (emptyPages >= 3) {
            console.log(`  📄 Page ${pageNum}: No more new articles (stopped after ${emptyPages} empty pages)`);
            break;
          }
          console.log(`  📄 Page ${pageNum}: No new articles (${emptyPages}/3 empty)`);
          continue;
        }
        
        emptyPages = 0;
        console.log(`  📄 Page ${pageNum}: Found ${newArticles.length} new articles`);

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
            await sleep(300);

            const pageData = await page.evaluate(() => {
              // PRIORITY 1: Meta tags (most reliable)
              let date = '';
              const metaDate = document.querySelector('meta[property="article:published_time"]');
              if (metaDate) date = metaDate.getAttribute('content') || '';
              
              // PRIORITY 2: JSON-LD structured data
              if (!date) {
                const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                for (const s of scripts) {
                  try {
                    const json = JSON.parse(s.textContent);
                    if (json.datePublished) { 
                      date = json.datePublished; 
                      break; 
                    }
                    if (json['@graph']) {
                      for (const item of json['@graph']) {
                        if (item.datePublished) { 
                          date = item.datePublished; 
                          break; 
                        }
                      }
                      if (date) break;
                    }
                  } catch {}
                }
              }
              
              // PRIORITY 3: Page elements with datetime
              if (!date) {
                const dateEl = document.querySelector('.Page-datePublished, time[datetime], [datetime]');
                if (dateEl) date = dateEl.getAttribute('datetime') || dateEl.textContent?.trim() || '';
              }
              
              // PRIORITY 4: URL pattern extraction
              if (!date) {
                const urlMatch = window.location.pathname.match(/\/(\d{4})\/(\d{2})\/(\d{2})\//);
                if (urlMatch) date = `${urlMatch[1]}-${urlMatch[2]}-${urlMatch[3]}`;
              }
              
              // Author extraction
              let author = '';
              const authorEl = document.querySelector('.Page-authorName a, .byline a, [rel="author"], .author, .Page-authorName');
              if (authorEl) author = authorEl.textContent?.trim() || '';
              
              // Content extraction (multiple fallbacks)
              let content = '';
              const selectors = [
                '.Page-articleBody', 
                '.RichTextArticleBody', 
                '.RichTextBody', 
                '.Page-content article',
                '.Page-content',
                'article .content',
                'main article',
                'article'
              ];
              
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
            
            // Date parsing with multiple fallback strategies
            if (pageData.date) {
              let parsed = new Date(pageData.date);
              
              // Try ISO format first
              if (isNaN(parsed.getTime())) {
                // Try "Month DD, YYYY" format
                const match1 = pageData.date.match(/(\w+)\s+(\d+),?\s+(\d{4})/);
                if (match1) parsed = new Date(`${match1[1]} ${match1[2]}, ${match1[3]}`);
              }
              
              // Try "YYYY-MM-DD" format
              if (isNaN(parsed.getTime())) {
                const match2 = pageData.date.match(/(\d{4})-(\d{2})-(\d{2})/);
                if (match2) parsed = new Date(`${match2[1]}-${match2[2]}-${match2[3]}`);
              }
              
              if (!isNaN(parsed.getTime())) {
                pubDate = parsed.toISOString().split('T')[0];
              }
            }
          } catch (e) {
            totalErrors++;
            // Continue to next article on error
          }

          // Validation checks
          if (!content || content.length < 50) {
            console.log(`    ⚠️  No content: ${article.title.slice(0, 40)}...`);
            continue;
          }
          
          if (!pubDate) {
            console.log(`    ⚠️  No date: ${article.title.slice(0, 40)}...`);
            continue;
          }

          const specialists = getSpecialists(article.title, article.url);

          try {
            await pool.query(
              `INSERT INTO alt.profarmer_news 
               (event_date, section, headline, content, url, author, specialist_tags, row_hash, raw_payload)
               VALUES ($1::date, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
               ON CONFLICT (row_hash) DO NOTHING`,
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
            sectionInserted++;
            
            if (totalInserted % 10 === 0 || sectionInserted <= 3) {
              console.log(`    ✅ [${pubDate}] ${article.title.slice(0, 50)}...`);
            }
          } catch (e) {
            if (!e.message.includes('duplicate')) {
              console.log(`    ❌ DB error: ${e.message.slice(0, 60)}`);
              totalErrors++;
            } else {
              totalSkipped++;
            }
          }
        }

        await sleep(300);
      } catch (e) {
        console.log(`  ❌ Page ${pageNum} error: ${e.message.slice(0, 50)}`);
        totalErrors++;
        break;
      }
    }
    
    console.log(`  📊 Section total: ${sectionInserted} articles inserted`);
  }

  console.log('\n' + '='.repeat(60));
  console.log('📈 SCRAPING COMPLETE');
  console.log('='.repeat(60));
  console.log(`✅ TOTAL INSERTED:  ${totalInserted}`);
  console.log(`⏭️  TOTAL SKIPPED:   ${totalSkipped}`);
  console.log(`❌ TOTAL ERRORS:    ${totalErrors}`);
  console.log(`🔗 UNIQUE URLS SEEN: ${seenUrls.size}`);
  console.log('='.repeat(60));

  await browser.close();
  await pool.end();
}

scrapeComprehensive().catch(e => { 
  console.error('💥 FATAL ERROR:', e); 
  process.exit(1); 
});
