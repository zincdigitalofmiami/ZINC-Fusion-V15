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

  function getSpecialists(title, url, keywords = []) {
    const text = (title + ' ' + url + ' ' + keywords.join(' ')).toLowerCase();
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

  // Generate sitemap URLs for 2023-2026
  const sitemaps = [];
  for (let year = 2023; year <= 2026; year++) {
    for (let month = 1; month <= 12; month++) {
      if (year === 2026 && month > 1) break;
      const ym = `${year}${String(month).padStart(2, '0')}`;
      sitemaps.push(`https://www.profarmer.com/sitemap-${ym}.xml`);
    }
  }

  console.log(`🗺️  Processing ${sitemaps.length} monthly sitemaps (2023-2026)\n`);
  console.log(`🎯 TARGET: 500+ articles with FULL metadata\n`);
  console.log(`📋 Extracting: headline, summary, content, author, topics, tags, categories, keywords\n`);
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
            const metadata = {
              date: '',
              author: '',
              content: '',
              title: '',
              description: '',
              keywords: [],
              categories: [],
              tags: [],
              section: '',
              imageUrl: '',
              modifiedDate: ''
            };

            // Extract from JSON-LD (most reliable structured data)
            const scripts = document.querySelectorAll('script[type="application/ld+json"]');
            for (const s of scripts) {
              try {
                const json = JSON.parse(s.textContent);
                
                // Date
                if (!metadata.date && json.datePublished) {
                  metadata.date = json.datePublished;
                }
                if (!metadata.modifiedDate && json.dateModified) {
                  metadata.modifiedDate = json.dateModified;
                }
                
                // Author
                if (!metadata.author && json.author) {
                  if (Array.isArray(json.author) && json.author[0]?.name) {
                    metadata.author = json.author[0].name;
                  } else if (json.author.name) {
                    metadata.author = json.author.name;
                  }
                }
                
                // Title
                if (!metadata.title && (json.headline || json.name)) {
                  metadata.title = json.headline || json.name;
                }
                
                // Description/Summary
                if (!metadata.description && json.description) {
                  metadata.description = json.description;
                }
                
                // Image
                if (!metadata.imageUrl && json.image) {
                  if (Array.isArray(json.image) && json.image[0]?.url) {
                    metadata.imageUrl = json.image[0].url;
                  } else if (typeof json.image === 'string') {
                    metadata.imageUrl = json.image;
                  } else if (json.image.url) {
                    metadata.imageUrl = json.image.url;
                  }
                }
                
                // Keywords from articleSection or about
                if (json.articleSection) {
                  const sections = Array.isArray(json.articleSection) ? json.articleSection : [json.articleSection];
                  metadata.categories.push(...sections);
                }
                
                if (json.about) {
                  const about = Array.isArray(json.about) ? json.about : [json.about];
                  about.forEach(item => {
                    if (typeof item === 'string') metadata.tags.push(item);
                    else if (item.name) metadata.tags.push(item.name);
                  });
                }
                
                if (json.keywords) {
                  const kw = Array.isArray(json.keywords) ? json.keywords : json.keywords.split(',');
                  metadata.keywords.push(...kw.map(k => k.trim()));
                }
              } catch {}
            }

            // Fallback to meta tags
            if (!metadata.date) {
              const metaDate = document.querySelector('meta[property="article:published_time"]');
              if (metaDate) metadata.date = metaDate.getAttribute('content');
            }
            
            if (!metadata.description) {
              const metaDesc = document.querySelector('meta[name="description"], meta[property="og:description"]');
              if (metaDesc) metadata.description = metaDesc.getAttribute('content');
            }
            
            if (!metadata.title) {
              const metaTitle = document.querySelector('meta[property="og:title"], meta[name="twitter:title"]');
              if (metaTitle) metadata.title = metaTitle.getAttribute('content');
              else {
                const h1 = document.querySelector('h1');
                if (h1) metadata.title = h1.textContent.trim();
              }
            }
            
            // Extract keywords from meta tags
            const metaKeywords = document.querySelector('meta[name="keywords"]');
            if (metaKeywords) {
              const kw = metaKeywords.getAttribute('content').split(',').map(k => k.trim());
              metadata.keywords.push(...kw);
            }
            
            // Extract article:tag meta tags
            const articleTags = document.querySelectorAll('meta[property="article:tag"]');
            articleTags.forEach(tag => {
              metadata.tags.push(tag.getAttribute('content'));
            });
            
            // Extract article:section
            const articleSection = document.querySelector('meta[property="article:section"]');
            if (articleSection) {
              metadata.section = articleSection.getAttribute('content');
            }

            // Content extraction
            const contentEl = document.querySelector('.Page-articleBody');
            if (contentEl) metadata.content = contentEl.textContent.trim().slice(0, 50000);

            // Breadcrumbs for section/category
            const breadcrumbs = document.querySelectorAll('.Page-breadcrumbs a');
            breadcrumbs.forEach(bc => {
              const text = bc.textContent.trim();
              if (text && text !== 'Pro Farmer' && text !== 'News') {
                metadata.categories.push(text);
              }
            });

            // Deduplicate arrays
            metadata.keywords = [...new Set(metadata.keywords)];
            metadata.tags = [...new Set(metadata.tags)];
            metadata.categories = [...new Set(metadata.categories)];

            return metadata;
          });

          if (!data.content || data.content.length < 50) continue;
          if (!data.date) continue;

          const pubDate = new Date(data.date).toISOString().split('T')[0];
          const title = data.title || articleUrl.split('/').pop();
          const specialists = getSpecialists(title, articleUrl, [...data.keywords, ...data.tags, ...data.categories]);

          // Build comprehensive raw_payload
          const rawPayload = {
            scraped_at: new Date().toISOString(),
            source: 'sitemap',
            url: articleUrl,
            summary: data.description,
            keywords: data.keywords,
            tags: data.tags,
            categories: data.categories,
            section: data.section,
            image_url: data.imageUrl,
            modified_date: data.modifiedDate,
            topics: [...data.categories, ...data.tags].filter(Boolean)
          };

          await pool.query(
            `INSERT INTO alt.profarmer_news 
             (event_date, section, headline, content, url, author, specialist_tags, row_hash, raw_payload)
             VALUES ($1::date, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
             ON CONFLICT (row_hash) DO NOTHING`,
            [
              pubDate,
              data.section || yearMonth.slice(0, 4) + '-' + yearMonth.slice(4),
              title.slice(0, 1000),
              data.content,
              articleUrl,
              data.author,
              specialists,
              rowHash,
              JSON.stringify(rawPayload)
            ]
          );

          totalInserted++;
          monthInserted++;

          if (totalInserted <= 20 || totalInserted % 50 === 0) {
            console.log(`  ✅ [${pubDate}] ${title.slice(0, 50)}...`);
            if (data.description) console.log(`     📝 Summary: ${data.description.slice(0, 80)}...`);
            if (data.tags.length > 0) console.log(`     🏷️  Tags: ${data.tags.slice(0, 5).join(', ')}`);
            if (data.keywords.length > 0) console.log(`     🔑 Keywords: ${data.keywords.slice(0, 5).join(', ')}`);
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
