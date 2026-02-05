const puppeteer = require('puppeteer');
const path = require('path');
const crypto = require('crypto');
require('dotenv').config({ path: path.join(__dirname, '../frontend/.env.local') });

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function scrapeDeep() {
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

  // === LOGIN ===
  console.log('🔐 Logging in to ProFarmer...');
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
    console.error('❌ LOGIN FAILED');
    await browser.close();
    await pool.end();
    process.exit(1);
  }
  console.log('✅ Login successful\n');

  let totalInserted = 0;
  let totalSkipped = 0;
  let failedDate = 0;
  let failedContent = 0;
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

  // AGGRESSIVE DEEP SCRAPING - ALL SECTIONS WITH DEEP PAGINATION
  const sections = [
    { name: 'All News', listUrl: 'https://www.profarmer.com/news', maxPages: 250 },
    { name: 'First Thing Today', listUrl: 'https://www.profarmer.com/topics/first-thing-today', maxPages: 100 },
    { name: 'Ahead of the Open', listUrl: 'https://www.profarmer.com/topics/ahead-open', maxPages: 100 },
    { name: 'After the Bell', listUrl: 'https://www.profarmer.com/topics/after-bell', maxPages: 100 },
    { name: 'Washington/Ag Policy', listUrl: 'https://www.profarmer.com/topics/policy-update', maxPages: 100 },
    { name: 'Pro Farmer Editors', listUrl: 'https://www.profarmer.com/topics/pro-farmer-editors', maxPages: 100 },
    { name: 'Corn', listUrl: 'https://www.profarmer.com/topics/corn', maxPages: 100 },
    { name: 'Soybeans', listUrl: 'https://www.profarmer.com/topics/soybeans', maxPages: 100 },
    { name: 'Wheat', listUrl: 'https://www.profarmer.com/topics/wheat', maxPages: 100 },
    { name: 'Energy', listUrl: 'https://www.profarmer.com/topics/energy', maxPages: 100 },
    { name: 'Weather', listUrl: 'https://www.profarmer.com/topics/weather', maxPages: 100 },
    { name: 'Trade', listUrl: 'https://www.profarmer.com/topics/trade', maxPages: 100 },
  ];

  for (const section of sections) {
    console.log(`\n${'='.repeat(60)}`);
    console.log(`📁 ${section.name.toUpperCase()}`);
    console.log(`${'='.repeat(60)}`);
    
    let emptyPages = 0;
    let sectionInserted = 0;
    
    for (let pageNum = 1; pageNum <= section.maxPages; pageNum++) {
      const listUrl = pageNum === 1 ? section.listUrl : `${section.listUrl}?page=${pageNum}`;
      
      try {
        await page.goto(listUrl, { waitUntil: 'networkidle2', timeout: 30000 });
        await sleep(400);

        const articles = await page.evaluate(() => {
          const results = [];
          const links = document.querySelectorAll('a');
          
          for (const a of links) {
            const href = a.href;
            if (!href || !href.includes('profarmer.com/news/')) continue;
            if (href.includes('/r/') || href.includes('subscribe') || href.includes('/topics/')) continue;
            
            // Must have at least 3 path segments after domain
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
          if (emptyPages >= 5) {
            console.log(`  Page ${pageNum}: Stopping after 5 empty pages`);
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
            await sleep(300);

            const pageData = await page.evaluate(() => {
              // COMPREHENSIVE DATE EXTRACTION
              let date = '';
              
              // 1. Meta tags
              const metaDate = document.querySelector('meta[property="article:published_time"]');
              if (metaDate) date = metaDate.getAttribute('content') || '';
              
              // 2. JSON-LD
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
              
              // 3. Page elements
              if (!date) {
                const selectors = [
                  '.Page-datePublished',
                  'time[datetime]',
                  '[datetime]',
                  '.published-date',
                  '.entry-date',
                  '.post-date',
                  '.article-date'
                ];
                for (const sel of selectors) {
                  const el = document.querySelector(sel);
                  if (el) {
                    date = el.getAttribute('datetime') || el.textContent?.trim() || '';
                    if (date) break;
                  }
                }
              }
              
              // 4. URL pattern
              if (!date) {
                const urlMatch = window.location.pathname.match(/\/(\d{4})\/(\d{2})\/(\d{2})\//);
                if (urlMatch) date = `${urlMatch[1]}-${urlMatch[2]}-${urlMatch[3]}`;
              }
              
              // 5. Text content date patterns
              if (!date) {
                const bodyText = document.body.textContent;
                const patterns = [
                  /Published[:\s]+(\w+\s+\d{1,2},?\s+\d{4})/i,
                  /(\w+\s+\d{1,2},?\s+\d{4})/,
                  /(\d{1,2}\/\d{1,2}\/\d{4})/,
                ];
                for (const pattern of patterns) {
                  const match = bodyText.match(pattern);
                  if (match && match[1]) {
                    date = match[1];
                    break;
                  }
                }
              }
              
              // Author extraction
              let author = '';
              const authorSelectors = [
                '.Page-authorName a',
                '.Page-authorName',
                '.byline a',
                '[rel="author"]',
                '.author a',
                '.author'
              ];
              for (const sel of authorSelectors) {
                const el = document.querySelector(sel);
                if (el) {
                  author = el.textContent?.trim() || '';
                  if (author) break;
                }
              }
              
              // Content extraction
              let content = '';
              const contentSelectors = [
                '.Page-articleBody', 
                '.RichTextArticleBody', 
                '.RichTextBody',
                '.Page-content article',
                '.article-content',
                '.entry-content',
                '.post-content',
                '.Page-content',
                'article .content',
                'main article',
                'article'
              ];
              
              for (const sel of contentSelectors) {
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
            
            // ENHANCED DATE PARSING
            if (pageData.date) {
              let parsed = null;
              
              // Try ISO format
              parsed = new Date(pageData.date);
              
              // Try "Month DD, YYYY"
              if (isNaN(parsed?.getTime())) {
                const match1 = pageData.date.match(/(\w+)\s+(\d+),?\s+(\d{4})/);
                if (match1) {
                  parsed = new Date(`${match1[1]} ${match1[2]}, ${match1[3]}`);
                }
              }
              
              // Try "YYYY-MM-DD"
              if (isNaN(parsed?.getTime())) {
                const match2 = pageData.date.match(/(\d{4})-(\d{2})-(\d{2})/);
                if (match2) {
                  parsed = new Date(`${match2[1]}-${match2[2]}-${match2[3]}`);
                }
              }
              
              // Try "MM/DD/YYYY"
              if (isNaN(parsed?.getTime())) {
                const match3 = pageData.date.match(/(\d{1,2})\/(\d{1,2})\/(\d{4})/);
                if (match3) {
                  parsed = new Date(`${match3[3]}-${match3[1].padStart(2, '0')}-${match3[2].padStart(2, '0')}`);
                }
              }
              
              if (parsed && !isNaN(parsed.getTime())) {
                pubDate = parsed.toISOString().split('T')[0];
              }
            }
          } catch (e) {
            // Continue to next article
          }

          // Validation with detailed tracking
          if (!content || content.length < 50) {
            failedContent++;
            if (totalInserted + totalSkipped < 20) {
              console.log(`    ⚠️  No content: ${article.title.slice(0, 40)}...`);
            }
            continue;
          }
          
          if (!pubDate) {
            failedDate++;
            if (totalInserted + totalSkipped < 20) {
              console.log(`    ⚠️  No date: ${article.title.slice(0, 40)}...`);
            }
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
            
            console.log(`    ✅ [${pubDate}] ${article.title.slice(0, 50)}...`);
          } catch (e) {
            if (!e.message.includes('duplicate')) {
              console.log(`    ❌ DB error: ${e.message.slice(0, 60)}`);
            } else {
              totalSkipped++;
            }
          }
        }

        await sleep(300);
      } catch (e) {
        console.log(`  ❌ Page ${pageNum}: ${e.message.slice(0, 50)}`);
        break;
      }
      
      // Progress update every 20 pages
      if (pageNum % 20 === 0) {
        console.log(`  📊 Progress: ${totalInserted} inserted, ${totalSkipped} skipped, ${failedDate} no-date, ${failedContent} no-content`);
      }
    }
    
    console.log(`  📊 Section: ${sectionInserted} articles inserted`);
  }

  console.log('\n' + '='.repeat(60));
  console.log('📈 FINAL RESULTS');
  console.log('='.repeat(60));
  console.log(`✅ INSERTED:     ${totalInserted}`);
  console.log(`⏭️  SKIPPED:      ${totalSkipped}`);
  console.log(`📅 FAILED DATE:  ${failedDate}`);
  console.log(`📝 FAILED CONTENT: ${failedContent}`);
  console.log(`🔗 UNIQUE URLS:  ${seenUrls.size}`);
  console.log('='.repeat(60));

  await browser.close();
  await pool.end();
}

scrapeDeep().catch(e => { 
  console.error('💥 FATAL:', e); 
  process.exit(1); 
});
