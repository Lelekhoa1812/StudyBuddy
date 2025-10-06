import * as pdfjs from 'pdfjs-dist/legacy/build/pdf'
import mammoth from 'mammoth'

export type Page = { page_num: number; text: string; images: Buffer[] }

export async function parsePdfBytes(buf: Buffer): Promise<Page[]> {
  const loadingTask = pdfjs.getDocument({ data: buf })
  const pdf = await loadingTask.promise
  const out: Page[] = []
  const num = pdf.numPages
  for (let i = 1; i <= num; i++) {
    const page = await pdf.getPage(i)
    const content = await page.getTextContent()
    const text = (content.items as any[]).map((it: any) => (it.str || '')).join(' ')
    out.push({ page_num: i, text, images: [] })
  }
  return out
}

export async function parseDocxBytes(buf: Buffer): Promise<Page[]> {
  const { value } = await mammoth.extractRawText({ buffer: buf })
  const text = value || ''
  return [{ page_num: 1, text, images: [] }]
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
  if (mime === 'application/pdf') return parsePdfBytes(file)
  if (mime === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document') return parseDocxBytes(file)
  throw new Error(`Unsupported file type: ${filename}`)
}
