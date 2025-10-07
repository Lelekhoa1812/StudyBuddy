export async function embedRemote(texts: string[]): Promise<number[][]> {
  const total = texts?.length || 0
  console.log(`[EMBEDDER_DEBUG] Embedding ${total} texts`)

  if (!texts || texts.length === 0) return []
  const base = (process.env.EMBED_BASE_URL || '').replace(/\/$/, '')
  if (!base) {
    console.error('[EMBEDDER_DEBUG] EMBED_BASE_URL is required')
    throw new Error('EMBED_BASE_URL is required')
  }

  // Memory-safe batching to avoid large payloads in Node/Vercel
  // Keep batches modest for local dev to avoid large JSON payloads in memory
  const batchSize = Math.max(1, parseInt(process.env.EMBED_BATCH_SIZE || '8', 10))
  const results: number[][] = []

  for (let start = 0; start < texts.length; start += batchSize) {
    const end = Math.min(start + batchSize, texts.length)
    const batch = texts.slice(start, end)
    console.log(`[EMBEDDER_DEBUG] Calling ${base}/embed for batch ${start}..${end - 1} (size=${batch.length})`)

    const res = await fetch(`${base}/embed`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ texts: batch }),
      next: { revalidate: 0 }
    })

    if (!res.ok) {
      console.warn(`[EMBEDDER_DEBUG] Batch embedding failed with status ${res.status}, using zero vectors`)
      const zeros = Array.from({ length: batch.length }, () => Array(384).fill(0))
      results.push(...zeros)
      continue
    }

    const data = (await res.json()) as any
    const vectors = Array.isArray(data?.vectors) ? data.vectors : []
    if (!Array.isArray(vectors) || vectors.length !== batch.length) {
      console.warn('[EMBEDDER_DEBUG] Invalid vectors format/length, using zero vectors for this batch')
      const zeros = Array.from({ length: batch.length }, () => Array(384).fill(0))
      results.push(...zeros)
      continue
    }

    results.push(...vectors)
  }

  console.log(`[EMBEDDER_DEBUG] Successfully embedded ${results.length}/${total} vectors`)
  return results
}
