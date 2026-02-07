const puppeteer = require('puppeteer');
const path = require('path');
const crypto = require('crypto');
require('dotenv').config({ path: path.join(__dirname, '../frontend/.env.local') });

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function scrape500Plus() {
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

  // STRATEGY: Multiple entry points with DEEP pagination
  const sections = [
    // Daily briefings - high volume
    { name: 'First Thing Today', url: 'https://www.profarmer.com/topics/first-thing-today', pages: 200 },
    { name: 'Ahead of the Open', url: 'https://www.profarmer.com/topics/ahead-open', pages: 200 },
    { name: 'After the Bell', url: 'https://www.profarmer.com/topics/after-bell', pages: 200 },
    
    // Commodity-specific
    { name: 'Soybeans', url: 'https://www.profarmer.com/topics/soybeans', pages: 150 },
    { name: 'Corn', url: 'https://www.profarmer.com/topics/corn', pages: 150 },
    { name: 'Wheat', url: 'https://www.profarmer.com/topics/wheat', pages: 150 },
    
    // Policy/Analysis  
    { name: 'Washington/Policy', url: 'https://www.profarmer.com/topics/policy-update', pages: 150 },
    { name: 'Trade', url: 'https://www.profarmer.com/topics/trade', pages: 150 },
    { name: 'Weather', url: 'https://www.profarmer.com/topics/weather', pages: 150 },
    
    // Editorial/Analysis
    { name: 'Pro Farmer Editors', url: 'https://www.profarmer.com/topics/pro-farmer-editors', pages: 200 },
  ];

  console.log(`🎯 TARGET: 500+ articles from ${sections.length} sections\n`);

  for (const section of sections) {
    console.log(`\n${'='.repeat(70)}`);
    console.log(`📁 ${section.name.toUpperCase()}`);
    console.log(`${'='.repeat(70)}`);

    let sectionInserted = 0;

    for (let p = 1; p <= section.pages; p++) {
      const pageUrl = p === 1 ? section.url : `${section.url}?page=${p}`;

      try {
        await page.goto(pageUrl, { waitUntil: 'networkidle2', timeout: 30000 });
        await sleep(400);

        const articles = await page.evaluate(() => {
          const results = [];
          document.querySelectorAll('a').forEach(a => {
            const href = a.href;
            if (!href || !href.includes('/news/')) return;
            if (href.includes('/r/') || href.includes('subscribe') || href.includes('/topics/')) return;
            
            const parts = href.replace('https://www.profarmer.com', '').split('/').filter(Boolean);
            if (parts.length < 3) return;
            
            const title = a.textContent?.trim();
            if (title && title.length >= 15 && title.length <= 500) {
              results.push({ url: href, title });
            }
          });
          return results;
        });

        const newArticles = articles.filter(a => !seenUrls.has(a.url));
        newArticles.forEach(a => seenUrls.add(a.url));

        if (newArticles.length === 0) {
          if (p === 1) console.log(`  Page ${p}: No articles found`);
          else if (p % 20 === 0) console.log(`  Page ${p}: No new articles`);
          continue;
        }

        if (p % 20 === 0 || p <= 5) {
          console.log(`  Page ${p}: ${newArticles.length} new articles`);
        }

        for (const article of newArticles) {
          const rowHash = crypto.createHash('sha256').update(`profarmer|${article.url}`).digest('hex');

          const exists = await pool.query('SELECT 1 FROM alt.profarmer_news WHERE row_hash = $1', [rowHash]);
          if (exists.rows.length > 0) {
            totalSkipped++;
            continue;
          }

          try {
            await page.goto(article.url, { waitUntil: 'networkidle2', timeout: 25000 });
            await sleep(250);

            const data = await page.evaluate(() => {
              // Extract date
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

              // Extract author
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

              // Extract content
              let content = '';
              const contentEl = document.querySelector('.Page-articleBody');
              if (contentEl) content = contentEl.textContent?.trim().slice(0, 50000);

              return { date, author, content };
            });

            if (!data.content || data.content.length < 50) continue;
            if (!data.date) continue;

            const pubDate = new Date(data.date).toISOString().split('T')[0];
            const specialists = getSpecialists(article.title, article.url);

            await pool.query(
              `INSERT INTO alt.profarmer_news 
               (event_date, section, headline, content, url, author, specialist_tags, row_hash, raw_payload)
               VALUES ($1::date, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
               ON CONFLICT (row_hash) DO NOTHING`,
              [
                pubDate,
                section.name,
                article.title.slice(0, 1000),
                data.content,
                article.url,
                data.author,
                specialists,
                rowHash,
                JSON.stringify({ scraped_at: new Date().toISOString() })
              ]
            );

            totalInserted++;
            sectionInserted++;
            
            if (totalInserted <= 50 || totalInserted % 25 === 0) {
              console.log(`    ✅ [${pubDate}] ${article.title.slice(0, 55)}...`);
            }
          } catch (e) {
            // Continue on error
          }
        }

        await sleep(250);

        if (totalInserted >= 500) {
          console.log(`\n🎯 TARGET REACHED: 500+ articles!\n`);
          break;
        }

      } catch (e) {
        if (p % 50 === 0) console.log(`  Page ${p}: ${e.message.slice(0, 40)}`);
        continue;
      }
    }

    console.log(`  📊 Section total: ${sectionInserted} articles`);

    if (totalInserted >= 500) break;
  }

  console.log('\n' + '='.repeat(70));
  console.log('📈 FINAL RESULTS');
  console.log('='.repeat(70));
  console.log(`✅ INSERTED:  ${totalInserted}`);
  console.log(`⏭️  SKIPPED:   ${totalSkipped}`);
  console.log(`🔗 TOTAL SEEN: ${seenUrls.size}`);
  console.log('='.repeat(70));

  await browser.close();
  await pool.end();
}

scrape500Plus().catch(e => {
  console.error('💥 ERROR:', e);
  process.exit(1);
});
