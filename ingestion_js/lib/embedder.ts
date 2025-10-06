export async function embedRemote(texts: string[]): Promise<number[][]> {
  if (!texts || texts.length === 0) return []
  const base = (process.env.EMBED_BASE_URL || '').replace(/\/$/, '')
  if (!base) throw new Error('EMBED_BASE_URL is required')
  const res = await fetch(`${base}/embed`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ texts }),
    // 60s like Python client
    next: { revalidate: 0 }
  })
  if (!res.ok) {
    // Fail closed with zeros to avoid crashes (parity with Python fallback)
    return Array.from({ length: texts.length }, () => Array(384).fill(0))
  }
  const data = await res.json() as any
  const vectors = Array.isArray(data?.vectors) ? data.vectors : []
  if (!Array.isArray(vectors)) {
    return Array.from({ length: texts.length }, () => Array(384).fill(0))
  }
  return vectors
}
