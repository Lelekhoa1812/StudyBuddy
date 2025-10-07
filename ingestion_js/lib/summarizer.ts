import { nvidiaChatOnce } from './llm'

export async function cheapSummarize(text: string, maxSentences = 3): Promise<string> {
  const trimmed = (text || '').trim()
  if (!trimmed) return ''
  const system = 'You summarize text. Output: concise summary only. No preface, no meta.'
  const user = `Summarize in at most ${maxSentences} sentences. Text:\n\n${trimmed}`
  const out = await nvidiaChatOnce(system, user, { modelEnv: 'NVIDIA_SMALL', maxTokens: 160 })
  return out || trimmed
}

export async function cleanChunkText(text: string): Promise<string> {
  let t = text
  t = t.replace(/\n\s*Page \d+\s*\n/gi, '\n')
  t = t.replace(/\s{3,}/g, ' ')
  return t.trim()
}
