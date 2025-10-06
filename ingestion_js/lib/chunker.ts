import slugify from 'slugify'
import type { Page } from './parser'
import { cheapSummarize, cleanChunkText } from './summarizer'

const MAX_WORDS = 220
const OVERLAP_WORDS = 40

function byHeadings(text: string): string[] {
  const lines = text.split('\n')
  const parts: string[] = []
  let current: string[] = []
  const flush = () => { if (current.length) { parts.push(current.join('\n')); current = [] } }
  const headingRe = /^(#+\s+|\d+\.|[A-Z][A-Za-z\s\-]{0,40}:?|^\s*\[[A-Za-z ]+\]\s*$)/
  for (const ln of lines) {
    if (headingRe.test(ln)) flush()
    current.push(ln)
  }
  flush()
  return parts.filter(p => p.trim().length > 0)
}

function createOverlappingChunks(blocks: string[]): string[] {
  const out: string[] = []
  let words: string[] = []
  for (const b of blocks) {
    words.push(...b.split(/\s+/))
    while (words.length > MAX_WORDS) {
      const chunk = words.slice(0, MAX_WORDS).join(' ')
      out.push(chunk)
      words = words.slice(MAX_WORDS - OVERLAP_WORDS)
    }
  }
  if (words.length) out.push(words.join(' '))
  return out
}

export async function buildCardsFromPages(pages: Page[], filename: string, user_id: string, project_id: string) {
  let full = ''
  for (const p of pages) full += `\n\n[[Page ${p.page_num}]]\n${(p.text || '').trim()}\n`
  const coarse = byHeadings(full)
  const chunks = createOverlappingChunks(coarse)

  const out: any[] = []
  for (let i = 0; i < chunks.length; i++) {
    const cleaned = await cleanChunkText(chunks[i])
    const topic = (await cheapSummarize(cleaned, 1)) || (cleaned.slice(0, 80) + '...')
    const summary = await cheapSummarize(cleaned, 3)
    const firstPage = pages[0]?.page_num ?? 1
    const lastPage = pages[pages.length - 1]?.page_num ?? 1
    out.push({
      user_id,
      project_id,
      filename,
      topic_name: topic.slice(0, 120),
      summary,
      content: cleaned,
      page_span: [firstPage, lastPage],
      card_id: `${slugify(filename)}-c${String(i + 1).padStart(4, '0')}`
    })
  }
  return out
}
