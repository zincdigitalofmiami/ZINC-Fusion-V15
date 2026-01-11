/**
 * Test RSS feeds before building Inngest jobs
 */

const feeds = [
  { name: 'ICE', url: 'https://www.ice.gov/rss', tags: ['trump_effect', 'legislation'] },
  { name: 'DHS', url: 'https://www.dhs.gov/news-releases.xml', tags: ['trump_effect', 'legislation'] },
  { name: 'CBP Trade', url: 'https://www.cbp.gov/rss/trade', tags: ['tariff', 'legislation'] },
  { name: 'AgWeb Soybeans', url: 'https://www.agweb.com/news/crops/soybeans/rss', tags: ['crush'] },
  { name: 'Farmdoc RINs', url: 'https://farmdocdaily.illinois.edu/category/areas/biofuels/rins/feed/', tags: ['biofuel'] },
  { name: 'AEI Trade', url: 'https://www.aei.org/tag/trade-policy/feed/', tags: ['tariff', 'trump_effect'] },
  { name: 'NY Fed Rates', url: 'https://markets.newyorkfed.org/api/rates/all/latest.json', tags: ['fed'] },
  { name: 'CONAB Brazil', url: 'https://www.conab.gov.br/rss', tags: ['crush', 'china'] },
];

async function testFeed(feed) {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    
    const response = await fetch(feed.url, { 
      signal: controller.signal,
      headers: { 'User-Agent': 'ZINC-Fusion/1.0 (RSS Reader)' }
    });
    clearTimeout(timeout);
    
    if (!response.ok) {
      return { name: feed.name, status: 'ERROR', code: response.status, tags: feed.tags };
    }
    
    const text = await response.text();
    const isXML = text.trim().startsWith('<?xml') || text.trim().startsWith('<rss') || text.trim().startsWith('<feed');
    const isJSON = text.trim().startsWith('{') || text.trim().startsWith('[');
    
    // Count items
    let itemCount = 0;
    if (isXML) {
      itemCount = (text.match(/<item>/g) || []).length || (text.match(/<entry>/g) || []).length;
    } else if (isJSON) {
      const json = JSON.parse(text);
      itemCount = Array.isArray(json) ? json.length : (json.refRates?.length || json.results?.length || 1);
    }
    
    return { 
      name: feed.name, 
      status: 'OK', 
      type: isXML ? 'RSS/XML' : isJSON ? 'JSON' : 'OTHER',
      items: itemCount,
      tags: feed.tags
    };
  } catch (err) {
    return { name: feed.name, status: 'FAILED', error: err.message, tags: feed.tags };
  }
}

async function main() {
  console.log('Testing RSS/API feeds...\n');
  
  for (const feed of feeds) {
    const result = await testFeed(feed);
    const icon = result.status === 'OK' ? '✅' : result.status === 'ERROR' ? '⚠️' : '❌';
    console.log(`${icon} ${result.name}`);
    console.log(`   URL: ${feed.url.substring(0, 60)}...`);
    console.log(`   Status: ${result.status}${result.code ? ` (${result.code})` : ''}${result.type ? ` [${result.type}]` : ''}`);
    if (result.items) console.log(`   Items: ${result.items}`);
    if (result.error) console.log(`   Error: ${result.error}`);
    console.log(`   Tags: ${result.tags.join(', ')}`);
    console.log('');
  }
}

main();
