const puppeteer = require('puppeteer');
const path = require('path');
const crypto = require('crypto');
require('dotenv').config({ path: path.join(__dirname, '../frontend/.env.local') });

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function scrapeEverything() {
  const user = process.env.PROFARMER_USERNAME;
  const pass = process.env.PROFARMER_PASSWORD;
  const dbUrl = process.env.DATABASE_URL;

  const { Pool } = require('pg');
  const pool = new Pool({ connectionString: dbUrl, ssl: { rejectUnauthorized: false } });

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
    defaultViewport: { width: 1920, height: 1080 },
  });

  const page = await browser.newPage();
  await page.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36');

  // LOGIN
  console.log('=== LOGGING INTO PROFARMER ===');
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

  await page.keyboard.type(user, { delay: 50 });
  await sleep(200);
  await page.keyboard.press('Tab');
  await sleep(200);
  await page.keyboard.type(pass, { delay: 50 });
  await sleep(300);
  await page.keyboard.press('Enter');
  await sleep(5000);

  if (page.url().includes('sign-in')) {
    console.log('LOGIN FAILED!');
    await browser.close();
    return;
  }
  console.log('LOGIN SUCCESS!\n');

  // DISCOVER ALL REPORT SECTIONS
  console.log('=== DISCOVERING CONTENT SECTIONS ===');
  await page.goto('https://www.profarmer.com/', { waitUntil: 'networkidle2' });
  
  const sections = await page.evaluate(() => {
    const links = new Set();
    document.querySelectorAll('a[href*="profarmer.com"]').forEach(a => {
      const href = a.href;
      // Find topic/category pages
      if (href.match(/profarmer\.com\/(topics|tag|category)\//) || 
          href.match(/profarmer\.com\/[a-z-]+\/$/) && !href.includes('/r/')) {
        links.add(href);
      }
    });
    return Array.from(links);
  });
  
  console.log('Found sections:', sections.slice(0, 20));

  // COMPREHENSIVE REPORT LIST
  const reports = [
    // Main reports
    { name: 'Daily Advice Monitor', url: 'https://www.profarmer.com/daily-advice-monitor/', specialists: ['crush', 'china', 'energy'] },
    { name: 'First Thing Today', url: 'https://www.profarmer.com/first-thing-today/', specialists: ['crush', 'china'] },
    { name: 'Washington Ag Policy', url: 'https://www.profarmer.com/washington-ag-policy/', specialists: ['tariff', 'biofuel', 'trump_effect'] },
    { name: 'After the Bell', url: 'https://www.profarmer.com/after-the-bell/', specialists: ['crush', 'volatility'] },
    { name: 'Ahead of the Open', url: 'https://www.profarmer.com/ahead-of-the-open/', specialists: ['crush', 'volatility'] },
    // Weekly reports  
    { name: 'Weekly Wrap', url: 'https://www.profarmer.com/weekly-wrap/', specialists: ['crush', 'china', 'energy'] },
    { name: 'Pro Farmer Editors', url: 'https://www.profarmer.com/topics/pro-farmer-editors/', specialists: ['crush'] },
    // Commodity specific
    { name: 'Corn', url: 'https://www.profarmer.com/topics/corn/', specialists: ['crush', 'biofuel'] },
    { name: 'Soybeans', url: 'https://www.profarmer.com/topics/soybeans/', specialists: ['crush', 'china'] },
    { name: 'Wheat', url: 'https://www.profarmer.com/topics/wheat/', specialists: ['substitutes'] },
    // Special topics
    { name: 'Exports', url: 'https://www.profarmer.com/topics/exports/', specialists: ['china', 'tariff'] },
    { name: 'USDA', url: 'https://www.profarmer.com/topics/usda/', specialists: ['crush', 'china'] },
    { name: 'Weather', url: 'https://www.profarmer.com/topics/weather/', specialists: ['crush', 'palm'] },
    { name: 'Policy', url: 'https://www.profarmer.com/topics/policy/', specialists: ['tariff', 'biofuel', 'trump_effect'] },
    { name: 'Trade', url: 'https://www.profarmer.com/topics/trade/', specialists: ['china', 'tariff'] },
    { name: 'Biofuels', url: 'https://www.profarmer.com/topics/biofuels/', specialists: ['biofuel', 'energy'] },
    { name: 'Livestock', url: 'https://www.profarmer.com/topics/livestock/', specialists: ['crush'] },
    // Analysis
    { name: 'Market Analysis', url: 'https://www.profarmer.com/topics/market-analysis/', specialists: ['crush', 'volatility'] },
    { name: 'Technical Analysis', url: 'https://www.profarmer.com/topics/technical-analysis/', specialists: ['volatility'] },
  ];

  let totalInserted = 0;
  let totalSkipped = 0;
  let totalAttempted = 0;

  for (const report of reports) {
    console.log(`\n=== SCRAPING: ${report.name} ===`);
    
    // Scrape multiple pages
    for (let pageNum = 1; pageNum <= 30; pageNum++) {
      const pageUrl = pageNum === 1 ? report.url : `${report.url}page/${pageNum}/`;
      
      try {
        await page.goto(pageUrl, { waitUntil: 'networkidle2', timeout: 30000 });
        await sleep(500);
        
        // Check if page exists
        const is404 = await page.evaluate(() => {
          return document.body.innerText.includes('Page not found') || 
                 document.body.innerText.includes('404');
        });
        if (is404) break;

        // Extract all article links and content
        const articles = await page.evaluate(() => {
          const results = [];
          
          // Find article containers
          const containers = document.querySelectorAll('article, .post, .entry, [class*="PromoSmall"], [class*="PromoMedium"], [class*="PromoLarge"]');
          
          for (const container of containers) {
            try {
              // Find link
              const link = container.querySelector('a[href*="profarmer.com"]');
              if (!link) continue;
              
              const href = link.href;
              if (href.includes('/r/') || href.includes('sign-in') || href.includes('subscribe')) continue;
              if (!href.match(/\/\d{4}\/\d{2}\//)) continue; // Must be dated article
              
              // Find title
              const titleEl = container.querySelector('h1, h2, h3, h4, .title, [class*="title"]');
              const title = titleEl?.textContent?.trim() || link.textContent?.trim();
              if (!title || title.length < 10) continue;
              
              // Find date
              let pubDate = '';
              const timeEl = container.querySelector('time, [datetime], .date, [class*="date"]');
              if (timeEl) {
                pubDate = timeEl.getAttribute('datetime') || timeEl.textContent?.trim() || '';
              }
              
              // Extract from URL
              if (!pubDate) {
                const match = href.match(/\/(\d{4})\/(\d{2})\/(\d{2})\//);
                if (match) pubDate = `${match[1]}-${match[2]}-${match[3]}`;
              }
              
              // Get excerpt
              const excerptEl = container.querySelector('.excerpt, .description, p, [class*="excerpt"]');
              const excerpt = excerptEl?.textContent?.trim()?.slice(0, 1000) || '';
              
              results.push({ url: href, title, pubDate, excerpt });
            } catch (e) {
              continue;
            }
          }
          
          return results;
        });

        if (articles.length === 0) {
          console.log(`  Page ${pageNum}: No articles found, stopping pagination`);
          break;
        }

        console.log(`  Page ${pageNum}: ${articles.length} articles found`);

        // Insert into database
        for (const article of articles) {
          totalAttempted++;
          
          const rowHash = crypto.createHash('sha256')
            .update(`${article.url}|${article.title}|${article.pubDate}`)
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
          let fullContent = article.excerpt;
          try {
            await page.goto(article.url, { waitUntil: 'networkidle2', timeout: 20000 });
            await sleep(300);
            
            fullContent = await page.evaluate(() => {
              const selectors = ['.entry-content', '.article-content', '.post-content', '.RichTextBody', 'article'];
              for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el?.textContent && el.textContent.length > 200) {
                  return el.textContent.trim().slice(0, 15000);
                }
              }
              return '';
            }) || article.excerpt;
          } catch (e) {
            // Keep excerpt
          }
          
          // Insert
          try {
            await pool.query(
              `INSERT INTO alt.news_1d (event_date, source, headline, content, url, specialist_tags, raw_payload, row_hash)
               VALUES ($1::date, 'profarmer', $2, $3, $4, $5, $6::jsonb, $7)`,
              [
                article.pubDate || new Date().toISOString().split('T')[0],
                article.title,
                fullContent,
                article.url,
                report.specialists,
                JSON.stringify({ report: report.name, scraped_at: new Date().toISOString() }),
                rowHash
              ]
            );
            totalInserted++;
            console.log(`    + ${article.title.slice(0, 60)}...`);
          } catch (e) {
            console.log(`    ! Insert failed: ${e.message}`);
          }
        }
        
        await sleep(1000); // Rate limit
      } catch (e) {
        console.log(`  Page ${pageNum}: Error - ${e.message}`);
        break;
      }
    }
  }

  console.log('\n=== SCRAPE COMPLETE ===');
  console.log(`Total attempted: ${totalAttempted}`);
  console.log(`Total inserted:  ${totalInserted}`);
  console.log(`Total skipped:   ${totalSkipped}`);

  await browser.close();
  await pool.end();
}

scrapeEverything().catch(console.error);
