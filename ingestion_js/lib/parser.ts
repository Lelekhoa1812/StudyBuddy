import * as pdfjs from 'pdfjs-dist/legacy/build/pdf'
import mammoth from 'mammoth'

export type Page = { page_num: number; text: string; images: Buffer[] }

export async function parsePdfBytes(buf: Buffer): Promise<Page[]> {
  console.log(`[PARSER_DEBUG] Parsing PDF with ${buf.length} bytes`)
  
  try {
    // Convert Buffer to Uint8Array for pdfjs-dist
    const uint8Array = new Uint8Array(buf)
    const loadingTask = pdfjs.getDocument({ data: uint8Array })
    const pdf = await loadingTask.promise
    const pages: Page[] = []
    
    console.log(`[PARSER_DEBUG] PDF has ${pdf.numPages} pages`)
    
    for (let i = 1; i <= pdf.numPages; i++) {
      console.log(`[PARSER_DEBUG] Processing page ${i}`)
      
      const page = await pdf.getPage(i)
      const textContent = await page.getTextContent()
      
      // Extract text like Python PyMuPDF does
      const text = textContent.items
        .map((item: any) => item.str || '')
        .join(' ')
        .trim()
      
      console.log(`[PARSER_DEBUG] Page ${i} extracted ${text.length} characters`)
      
      // For now, we don't extract images from PDF in serverless (complex)
      // This matches the current limitation but we could add image extraction later
      pages.push({
        page_num: i,
        text: text || `[Page ${i} - No text content extracted]`,
        images: [] // Images not extracted in current implementation
      })
    }
    
    console.log(`[PARSER_DEBUG] Parsed PDF with ${pages.length} pages`)
    return pages
  } catch (error) {
    console.error('[PARSER_DEBUG] PDF parsing error:', error)
    // Fallback to simple text representation
    return [{ page_num: 1, text: `[PDF Content - ${buf.length} bytes - Parse error: ${error}]`, images: [] }]
  }
}

export async function parseDocxBytes(buf: Buffer): Promise<Page[]> {
  try {
    const { value } = await mammoth.extractRawText({ buffer: buf })
    const text = value || ''
    console.log(`[PARSER_DEBUG] DOCX extracted ${text.length} characters`)
    return [{ page_num: 1, text, images: [] }]
  } catch (error) {
    console.error('[PARSER_DEBUG] DOCX parsing error:', error)
    return [{ page_num: 1, text: `[DOCX Parse Error: ${error}]`, images: [] }]
  }
}

export function inferMime(filename: string): string {
  const lower = filename.toLowerCase()
  if (lower.endsWith('.pdf')) return 'application/pdf'
  if (lower.endsWith('.docx'))
    return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
  return 'application/octet-stream'
}

export async function extractPages(filename: string, file: Buffer): Promise<Page[]> {
  const mime = inferMime(filename)
  console.log(`[PARSER_DEBUG] Processing ${filename} as ${mime}`)
  
  if (mime === 'application/pdf') return parsePdfBytes(file)
  if (mime === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document') return parseDocxBytes(file)
  throw new Error(`Unsupported file type: ${filename}`)
}
