const fs = require('fs');
const path = require('path');

// Simple test for PDF parser
async function testParser() {
  try {
    // Import the parser
    const { extractPages } = require('./lib/parser.ts');
    
    // Test with a sample PDF
    const pdfPath = path.join(__dirname, '../exefiles/Lecture5_ML.pdf');
    
    if (!fs.existsSync(pdfPath)) {
      console.log('❌ Test PDF not found:', pdfPath);
      return;
    }
    
    console.log('📄 Testing PDF parser with:', pdfPath);
    const buffer = fs.readFileSync(pdfPath);
    console.log('📊 File size:', buffer.length, 'bytes');
    
    const pages = await extractPages('Lecture5_ML.pdf', buffer);
    console.log('✅ Parsed pages:', pages.length);
    
    pages.forEach((page, i) => {
      console.log(`\n--- Page ${page.page_num} ---`);
      console.log('Text length:', page.text.length);
      console.log('Preview:', page.text.substring(0, 200) + '...');
    });
    
  } catch (error) {
    console.error('❌ Parser test failed:', error);
  }
}

testParser();
