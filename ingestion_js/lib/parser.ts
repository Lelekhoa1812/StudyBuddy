import pdfParse from 'pdf-parse'
import mammoth from 'mammoth'

export type Page = { page_num: number; text: string; images: Buffer[] }

export async function parsePdfBytes(buf: Buffer): Promise<Page[]> {
  console.log(`[PARSER_DEBUG] Parsing PDF with ${buf.length} bytes`)
  
  try {
    const data = await pdfParse(buf)
    const text = data.text || ''
    console.log(`[PARSER_DEBUG] PDF extracted ${text.length} characters`)
    
    // Split text by pages if possible (pdf-parse doesn't provide page breaks)
    // For now, treat as single page like DOCX
    const pages: Page[] = [{
      page_num: 1,
      text: text || `[PDF Content - ${buf.length} bytes - No text extracted]`,
      images: [] // Images not extracted in current implementation
    }]
    
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
