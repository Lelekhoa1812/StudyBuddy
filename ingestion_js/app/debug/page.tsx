"use client"
import { useEffect, useState } from 'react'

type DebugData = Record<string, any>

export default function DebugPage() {
  const [env, setEnv] = useState<DebugData | null>(null)
  const [health, setHealth] = useState<DebugData | null>(null)
  const [jobs, setJobs] = useState<DebugData | null>(null)
  const [files, setFiles] = useState<DebugData | null>(null)
  const [chunks, setChunks] = useState<DebugData | null>(null)
  const [embedding, setEmbedding] = useState<DebugData | null>(null)
  const [parser, setParser] = useState<DebugData | null>(null)
  const [loading, setLoading] = useState(false)

  async function fetchDebug(action: string): Promise<DebugData> {
    const res = await fetch(`/api/debug?action=${encodeURIComponent(action)}`, { cache: 'no-store' })
    return res.json()
  }

  async function refreshAll() {
    setLoading(true)
    try {
      const [envData, healthData, jobsData] = await Promise.all([
        fetchDebug('env'),
        fetchDebug('health'),
        fetchDebug('jobs')
      ])
      setEnv(envData)
      setHealth(healthData)
      setJobs(jobsData)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refreshAll()
  }, [])

  return (
    <main style={{ padding: 20, fontFamily: 'system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif' }}>
      <h1>Ingestion Debug</h1>
      <p>Quick tools to inspect server status and ingestion pipeline.</p>

      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', margin: '12px 0' }}>
        <button onClick={refreshAll} disabled={loading}>{loading ? 'Refreshing…' : 'Refresh Env/Health/Jobs'}</button>
        <button onClick={async () => setFiles(await fetchDebug('files'))}>Load Files</button>
        <button onClick={async () => setChunks(await fetchDebug('chunks'))}>Load Chunks</button>
        <button onClick={async () => setEmbedding(await fetchDebug('test-embedding'))}>Test Embedding</button>
        <button onClick={async () => setParser(await fetchDebug('test-parser'))}>Test Parser</button>
      </div>

      <section>
        <h2>Environment</h2>
        <pre style={{ background: '#f5f5f5', padding: 12, overflow: 'auto' }}>{JSON.stringify(env, null, 2)}</pre>
      </section>

      <section>
        <h2>Health</h2>
        <pre style={{ background: '#f5f5f5', padding: 12, overflow: 'auto' }}>{JSON.stringify(health, null, 2)}</pre>
      </section>

      <section>
        <h2>Jobs</h2>
        <pre style={{ background: '#f5f5f5', padding: 12, overflow: 'auto' }}>{JSON.stringify(jobs, null, 2)}</pre>
      </section>

      <section>
        <h2>Files</h2>
        <pre style={{ background: '#f5f5f5', padding: 12, overflow: 'auto' }}>{JSON.stringify(files, null, 2)}</pre>
      </section>

      <section>
        <h2>Chunks</h2>
        <pre style={{ background: '#f5f5f5', padding: 12, overflow: 'auto' }}>{JSON.stringify(chunks, null, 2)}</pre>
      </section>

      <section>
        <h2>Embedding Test</h2>
        <pre style={{ background: '#f5f5f5', padding: 12, overflow: 'auto' }}>{JSON.stringify(embedding, null, 2)}</pre>
      </section>

      <section>
        <h2>Parser Test</h2>
        <pre style={{ background: '#f5f5f5', padding: 12, overflow: 'auto' }}>{JSON.stringify(parser, null, 2)}</pre>
      </section>
    </main>
  )
}


