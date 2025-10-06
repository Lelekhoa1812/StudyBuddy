export async function embedRemote(texts: string[]): Promise<number[][]> {
  console.log(`[EMBEDDER_DEBUG] Embedding ${texts.length} texts`)
  
  if (!texts || texts.length === 0) return []
  const base = (process.env.EMBED_BASE_URL || '').replace(/\/$/, '')
  if (!base) {
    console.error('[EMBEDDER_DEBUG] EMBED_BASE_URL is required')
    throw new Error('EMBED_BASE_URL is required')
  }
  
  console.log(`[EMBEDDER_DEBUG] Calling ${base}/embed`)
  
  const res = await fetch(`${base}/embed`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ texts }),
    // 60s like Python client
    next: { revalidate: 0 }
  })
  
  if (!res.ok) {
    console.warn(`[EMBEDDER_DEBUG] Embedding failed with status ${res.status}, using zero vectors`)
    // Fail closed with zeros to avoid crashes (parity with Python fallback)
    return Array.from({ length: texts.length }, () => Array(384).fill(0))
  }
  
  const data = await res.json() as any
  const vectors = Array.isArray(data?.vectors) ? data.vectors : []
  if (!Array.isArray(vectors)) {
    console.warn('[EMBEDDER_DEBUG] Invalid vectors format, using zero vectors')
    return Array.from({ length: texts.length }, () => Array(384).fill(0))
  }
  
  console.log(`[EMBEDDER_DEBUG] Successfully embedded ${vectors.length} vectors`)
  return vectors
}
