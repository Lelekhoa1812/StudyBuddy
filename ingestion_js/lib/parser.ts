import { PDFDocument } from 'pdf-lib'
import pdfParse from 'pdf-parse'
import mammoth from 'mammoth'

export type Page = { page_num: number; text: string; images: Buffer[] }

export async function parsePdfBytes(buf: Buffer): Promise<Page[]> {
  console.log(`[PARSER_DEBUG] Parsing PDF with ${buf.length} bytes`)
  
  try {
    // First try pdf-parse for text extraction
    const data = await pdfParse(buf)
    const text = data.text || ''
    console.log(`[PARSER_DEBUG] PDF extracted ${text.length} characters`)
    
    // Get page count from pdf-lib for proper page structure
    const pdfDoc = await PDFDocument.load(buf)
    const pageCount = pdfDoc.getPageCount()
    console.log(`[PARSER_DEBUG] PDF has ${pageCount} pages`)
    
    const pages: Page[] = []
    
    if (pageCount === 1) {
      // Single page - use all text
      pages.push({
        page_num: 1,
        text: text || `[PDF Content - ${buf.length} bytes - No text extracted]`,
        images: []
      })
    } else {
      // Multiple pages - split text roughly by page count
      const textPerPage = Math.ceil(text.length / pageCount)
      for (let i = 0; i < pageCount; i++) {
        const start = i * textPerPage
        const end = Math.min(start + textPerPage, text.length)
        const pageText = text.slice(start, end).trim()
        
        pages.push({
          page_num: i + 1,
          text: pageText || `[PDF Page ${i + 1} - No text extracted]`,
          images: []
        })
      }
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
