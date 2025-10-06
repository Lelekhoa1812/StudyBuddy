export async function cheapSummarize(text: string, maxSentences = 3): Promise<string> {
  if (!text || text.trim().length < 50) return text.trim()
  try {
    const sentences = text.split(/(?<=[.!?])\s+/).filter(Boolean)
    if (sentences.length <= maxSentences) return text.trim()
    let out = sentences.slice(0, maxSentences).join(' ')
    if (!/[.!?]$/.test(out)) out += '.'
    return out
  } catch {
    return text.length > 200 ? text.slice(0, 200) + '...' : text
  }
}

export async function cleanChunkText(text: string): Promise<string> {
  let t = text
  t = t.replace(/\n\s*Page \d+\s*\n/gi, '\n')
  t = t.replace(/\s{3,}/g, ' ')
  return t.trim()
}
