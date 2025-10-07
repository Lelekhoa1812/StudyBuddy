import { PDFDocument } from 'pdf-lib'
import mammoth from 'mammoth'

export type Page = { page_num: number; text: string; images: Buffer[] }

// Simple text extraction from PDF using basic parsing
function extractTextFromPdfBuffer(buffer: Buffer): string {
  try {
    // Convert buffer to string and look for text content
    const pdfString = buffer.toString('latin1')
    
    // Look for text streams in PDF
    const textMatches = pdfString.match(/BT[\s\S]*?ET/g) || []
    const textContent = textMatches
      .map(match => {
        // Extract text from PDF text objects
        const textMatches = match.match(/\([^)]*\)/g) || []
        return textMatches
          .map(t => t.slice(1, -1)) // Remove parentheses
          .join(' ')
      })
      .join(' ')
      .trim()
    
    return textContent || `[PDF Content - ${buffer.length} bytes - Text extraction limited]`
  } catch (error) {
    return `[PDF Content - ${buffer.length} bytes - Text extraction failed: ${error}]`
  }
}

export async function parsePdfBytes(buf: Buffer): Promise<Page[]> {
  console.log(`[PARSER_DEBUG] Parsing PDF with ${buf.length} bytes`)
  
  // Optional heavy parser (guarded by env to avoid OOM locally)
  if (process.env.PARSER_USE_PDFJS === '1') {
    try {
      const pdfjs: any = await import('pdfjs-dist/legacy/build/pdf')
      if (pdfjs.GlobalWorkerOptions) {
        pdfjs.GlobalWorkerOptions.workerSrc = undefined
      }
      const loadingTask = pdfjs.getDocument({
        data: new Uint8Array(buf),
        disableFontFace: true,
        useSystemFonts: true,
        isEvalSupported: false
      })
      const pdf = await loadingTask.promise
      const pageCount: number = pdf.numPages
      console.log(`[PARSER_DEBUG] pdfjs-dist loaded. Pages: ${pageCount}`)

      const pages: Page[] = []
      for (let i = 1; i <= pageCount; i++) {
        const page = await pdf.getPage(i)
        const textContent = await page.getTextContent()
        const text = (textContent.items || [])
          .map((it: any) => (typeof it.str === 'string' ? it.str : ''))
          .join(' ')
          .replace(/\s+/g, ' ')
          .trim()

        pages.push({ page_num: i, text, images: [] })
      }
      console.log(`[PARSER_DEBUG] Parsed PDF with ${pages.length} pages via pdfjs-dist`)
      return pages
    } catch (err) {
      console.warn('[PARSER_DEBUG] pdfjs-dist extraction failed, falling back to basic extractor:', err)
    }
  }

  // Fallback: use lightweight extractor and page-count from pdf-lib
  try {
    const pdfDoc = await PDFDocument.load(buf)
    const pageCount = pdfDoc.getPageCount()
    const extractedText = extractTextFromPdfBuffer(buf)
    const pages: Page[] = []
    if (pageCount > 1) {
      const textPerPage = Math.ceil(extractedText.length / pageCount)
      for (let i = 0; i < pageCount; i++) {
        const start = i * textPerPage
        const end = Math.min((i + 1) * textPerPage, extractedText.length)
        const pageText = extractedText.slice(start, end).trim() || `[Page ${i + 1} - Content]`
        pages.push({ page_num: i + 1, text: pageText, images: [] })
      }
    } else {
      pages.push({ page_num: 1, text: extractedText || `[PDF Content - ${buf.length} bytes]`, images: [] })
    }
    console.log(`[PARSER_DEBUG] Parsed PDF with ${pages.length} pages via fallback`)
    return pages
  } catch (error) {
    console.error('[PARSER_DEBUG] PDF parsing error (fallback):', error)
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
