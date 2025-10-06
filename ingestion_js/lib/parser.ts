import pdfTextExtract from 'pdf-text-extract'
import mammoth from 'mammoth'

export type Page = { page_num: number; text: string; images: Buffer[] }

export async function parsePdfBytes(buf: Buffer): Promise<Page[]> {
  return new Promise((resolve, reject) => {
    pdfTextExtract(buf, (err, pages) => {
      if (err) {
        reject(err)
        return
      }
      const out: Page[] = []
      for (let i = 0; i < pages.length; i++) {
        out.push({ page_num: i + 1, text: pages[i] || '', images: [] })
      }
      if (out.length === 0) out.push({ page_num: 1, text: '', images: [] })
      resolve(out)
    })
  })
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
