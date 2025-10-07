import slugify from 'slugify'
import type { Page } from './parser'
import { cheapSummarize, cleanChunkText } from './summarizer'
import { nvidiaChatOnce, nvidiaChatJSONRobust } from './llm'

// Slightly smaller chunk sizes for lower peak memory during local dev
const MAX_WORDS = Math.max(300, parseInt(process.env.CHUNK_MAX_WORDS || '450', 10))
const MIN_WORDS = Math.max(120, parseInt(process.env.CHUNK_MIN_WORDS || '150', 10))
const OVERLAP_WORDS = Math.max(40, parseInt(process.env.CHUNK_OVERLAP_WORDS || '50', 10))

function byHeadings(text: string): string[] {
  // Enhanced patterns matching Python logic
  const patterns = [
    /^(#{1,6}\s.*)\s*$/gm,  // Markdown headers
    /^([0-9]+\.\s+[^\n]+)\s*$/gm,  // Numbered sections
    /^([A-Z][A-Za-z0-9\s\-]{2,}\n[-=]{3,})\s*$/gm,  // Underlined headers
    /^(Chapter\s+\d+.*|Section\s+\d+.*)\s*$/gm,  // Chapter/Section headers
    /^(Abstract|Introduction|Conclusion|References|Bibliography)\s*$/gm,  // Common academic sections
  ]
  
  const parts: string[] = []
  let last = 0
  const allMatches: Array<{start: number, end: number, header: string}> = []
  
  // Find all matches from all patterns
  for (const pattern of patterns) {
    let match
    while ((match = pattern.exec(text)) !== null) {
      allMatches.push({
        start: match.index,
        end: match.index + match[0].length,
        header: match[1].trim()
      })
    }
  }
  
  // Sort matches by position
  allMatches.sort((a, b) => a.start - b.start)
  
  // Split text based on matches
  for (const { start, end, header } of allMatches) {
    if (start > last) {
      parts.push(text.slice(last, start))
    }
    parts.push(text.slice(start, end))
    last = end
  }
  
  if (last < text.length) {
    parts.push(text.slice(last))
  }
  
  if (parts.length === 0) {
    parts.push(text)
  }
  
  return parts.filter(p => p.trim().length > 0)
}

function createOverlappingChunks(blocks: string[]): string[] {
  const chunks: string[] = []
  
  for (let i = 0; i < blocks.length; i++) {
    const block = blocks[i]
    const words = block.split(/\s+/).filter(w => w.length > 0)
    
    if (words.length === 0) continue
    
    // If block is small enough, use as-is
    if (words.length <= MAX_WORDS) {
      chunks.push(block)
      continue
    }
    
    // Split large blocks with overlap
    let start = 0
    while (start < words.length) {
      const end = Math.min(start + MAX_WORDS, words.length)
      let chunkWords = words.slice(start, end)
      
      // Add overlap from previous chunk if available
      if (start > 0 && chunks.length > 0) {
        const prevWords = chunks[chunks.length - 1].split(/\s+/).filter(w => w.length > 0)
        const overlapStart = Math.max(0, prevWords.length - OVERLAP_WORDS)
        const overlapWords = prevWords.slice(overlapStart)
        chunkWords = [...overlapWords, ...chunkWords]
      }
      
      chunks.push(chunkWords.join(' '))
      start = end - OVERLAP_WORDS  // Overlap with next chunk
    }
  }
  
  return chunks
}

async function llmSuggestChunks(full: string): Promise<string[] | null> {
  const tokenSoftLimit = Math.max(1200, parseInt(process.env.LLM_CHUNK_SOFT_TOKENS || '2000', 10))
  const modelEnv = full.length > 200_000 ? 'NVIDIA_LARGE' : 'NVIDIA_SMALL'
  const system = 'You are a text segmenter. Output JSON array of coherent chunks that preserve meaning. Each chunk should be short (approx 150-400 words). No commentary.'
  const user = `Split the following text into coherent chunks under ${tokenSoftLimit} tokens total per chunk. Respond with a pure JSON array of strings (no extra text).\n\n${full}`
  const json = await nvidiaChatJSONRobust<string[]>(system, user, {
    modelEnvPrimary: modelEnv as any,
    modelEnvFallback: 'NVIDIA_LARGE',
    maxTokens: 1200
  })
  if (!json || !Array.isArray(json)) return null
  return json.filter(s => typeof s === 'string' && s.trim().length > 0)
}

export async function buildCardsFromPages(pages: Page[], filename: string, user_id: string, project_id: string) {
  console.log(`[CHUNKER_DEBUG] Building cards from ${pages.length} pages for ${filename}`)
  
  let full = ''
  for (const p of pages) full += `\n\n[[Page ${p.page_num}]]\n${(p.text || '').trim()}\n`
  console.log(`[CHUNKER_DEBUG] Full text length: ${full.length}`)
  
  let chunks: string[] | null = null
  try {
    chunks = await llmSuggestChunks(full)
  } catch {}
  if (!chunks || chunks.length === 0) {
    const coarse = byHeadings(full)
    console.log(`[CHUNKER_DEBUG] LLM chunking unavailable; fallback by headings: ${coarse.length} blocks`)
    chunks = createOverlappingChunks(coarse)
  }
  console.log(`[CHUNKER_DEBUG] Using ${chunks.length} chunks`)

  const out: any[] = []
  for (let i = 0; i < chunks.length; i++) {
    console.log(`[CHUNKER_DEBUG] Processing chunk ${i + 1}/${chunks.length}`)
    
    const cleaned = await cleanChunkText(chunks[i])
    const topic = await nvidiaChatOnce(
      'You extract concise topic names. Output: a brief topic only.',
      `Provide a short topic/title for this content. No preface. No extra words.\n\n${cleaned}`,
      { modelEnv: 'NVIDIA_SMALL', maxTokens: 24 }
    ) || (cleaned.slice(0, 80) + '...')
    const summary = await cheapSummarize(cleaned, 3)
    const firstPage = pages[0]?.page_num ?? 1
    const lastPage = pages[pages.length - 1]?.page_num ?? 1
    
    const card = {
      user_id,
      project_id,
      filename,
      topic_name: topic.slice(0, 120),
      summary,
      content: cleaned,
      page_span: [firstPage, lastPage],
      card_id: `${slugify(String(filename))}-c${String(i + 1).padStart(4, '0')}`
    }
    
    console.log(`[CHUNKER_DEBUG] Created card ${card.card_id} with content length ${cleaned.length}`)
    out.push(card)
  }
  
  console.log(`[CHUNKER_DEBUG] Built ${out.length} cards total`)
  return out
}
