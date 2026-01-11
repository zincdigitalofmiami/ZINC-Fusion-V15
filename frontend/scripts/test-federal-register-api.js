// Test Federal Register API
async function test() {
  const endDate = new Date();
  const startDate = new Date();
  startDate.setDate(startDate.getDate() - 7);
  
  const formatDate = (d) => d.toISOString().split('T')[0];
  
  const baseUrl = 'https://www.federalregister.gov/api/v1/documents.json';
  const params = new URLSearchParams({
    'per_page': '5',
    'order': 'newest',
    'conditions[publication_date][gte]': formatDate(startDate),
    'conditions[publication_date][lte]': formatDate(endDate),
  });
  ['RULE', 'PRORULE', 'NOTICE', 'PRESDOCU'].forEach(type => {
    params.append('conditions[type][]', type);
  });
  
  const url = `${baseUrl}?${params.toString()}`;
  console.log('Fetching:', url.substring(0, 100) + '...');
  
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error('API error: ' + response.status);
  }
  
  const json = await response.json();
  console.log('\n=== API Response ===');
  console.log('Total documents available:', json.count);
  console.log('Documents in this page:', json.results.length);
  
  console.log('\n=== Sample Documents ===');
  json.results.slice(0, 3).forEach((doc, i) => {
    console.log(`\n[${i+1}] ${doc.document_number}`);
    console.log(`    Type: ${doc.type}`);
    console.log(`    Title: ${(doc.title || '').substring(0, 80)}...`);
    console.log(`    Agencies: ${(doc.agencies || []).map(a => a.name).join(', ').substring(0, 60)}`);
    console.log(`    Published: ${doc.publication_date}`);
  });
}
test().catch(console.error);
