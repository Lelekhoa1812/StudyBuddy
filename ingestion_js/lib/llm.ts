function getNvidiaKey(): string | null {
  const direct = process.env.NVIDIA_API || null
  if (direct) return direct
  for (let i = 1; i <= 5; i++) {
    const k = process.env[`NVIDIA_API_${i}`]
    if (k) return k
  }
  return null
}

function getModelFromEnv(which?: 'NVIDIA_SMALL' | 'NVIDIA_LARGE'): string | null {
  const tryKeys: string[] = []
  if (which === 'NVIDIA_SMALL') {
    tryKeys.push('NVIDIA_SMALL', 'NVIDIA_SMALL_MODEL', 'NVIDIA_MODEL_SMALL')
  } else if (which === 'NVIDIA_LARGE') {
    tryKeys.push('NVIDIA_LARGE', 'NVIDIA_LARGE_MODEL', 'NVIDIA_MODEL_LARGE')
  }
  // Common fallback
  tryKeys.push('NVIDIA_MAVERICK_MODEL')

  for (const key of tryKeys) {
    const val = process.env[key]
    if (val && typeof val === 'string' && val.trim().length > 0) return val.trim()
  }
  return null
}

export function normalizeConcise(text: string): string {
  if (!text) return ''
  let t = text.trim()
  const banned = [
    'sure,', 'sure.', 'sure',
    'here is', 'here are', "here's",
    'this image', 'the image', 'image shows', 'in the image',
    'the picture', 'the photo', 'photo shows', 'picture shows',
    'the text describes', 'the text describe', 'this text describes', 'this text describe',
    'this describes', 'this is', 'this is cleaned', 'this text', 'this document',
    'it shows', 'it depicts', 'it is',
    'caption:', 'description:', 'output:', 'result:', 'answer:', 'analysis:', 'observation:',
    'summary:', 'summarization:', 'topic:', 'title:'
  ]
  const lower = t.toLowerCase()
  for (const p of banned) {
    if (lower.startsWith(p)) {
      t = t.slice(p.length).trimStart()
      break
    }
  }
  t = t.replace(/^[-–—>*\s]+/, '')
  t = t.replace(/[\s]+/g, ' ')
  t = t.replace(/^[\'\"]|[\'\"]$/g, '')
  return t.trim()
}

export async function nvidiaChatOnce(
  systemPrompt: string,
  userPrompt: string,
  opts?: { modelEnv?: 'NVIDIA_SMALL' | 'NVIDIA_LARGE'; maxTokens?: number; temperature?: number }
): Promise<string> {
  const key = getNvidiaKey()
  if (!key) return ''

  const modelName = (getModelFromEnv(opts?.modelEnv) || 'meta/llama-4-8b-instruct').replace(/^['"]|['"]$/g, '')
  console.log('[LLM_DEBUG] chatOnce model:', modelName, 'env:', opts?.modelEnv || 'default')

  const payload = {
    model: modelName,
    messages: [
      { role: 'system', content: systemPrompt },
      { role: 'user', content: userPrompt }
    ],
    max_tokens: opts?.maxTokens ?? 256,
    temperature: opts?.temperature ?? 0.2,
    stream: false
  }

  const res = await fetch('https://integrate.api.nvidia.com/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${key}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  })
  if (!res.ok) {
    console.warn('[LLM_DEBUG] chatOnce HTTP', res.status)
    return ''
  }
  const data = await res.json() as any
  const text = data?.choices?.[0]?.message?.content || ''
  console.log('[LLM_DEBUG] chatOnce tokens:', data?.usage?.total_tokens, 'textLen:', text.length)
  return normalizeConcise(text)
}

export async function nvidiaChatJSON<T = unknown>(
  systemPrompt: string,
  userPrompt: string,
  opts?: { modelEnv?: 'NVIDIA_SMALL' | 'NVIDIA_LARGE'; maxTokens?: number; temperature?: number }
): Promise<T | null> {
  const key = getNvidiaKey()
  if (!key) return null

  const modelName = (getModelFromEnv(opts?.modelEnv) || 'meta/llama-4-8b-instruct').replace(/^['"]|['"]$/g, '')
  console.log('[LLM_DEBUG] chatJSON model:', modelName, 'env:', opts?.modelEnv || 'default')

  const payload = {
    model: modelName,
    messages: [
      { role: 'system', content: systemPrompt },
      { role: 'user', content: userPrompt }
    ],
    max_tokens: opts?.maxTokens ?? 512,
    temperature: opts?.temperature ?? 0.2,
    stream: false
  }

  const res = await fetch('https://integrate.api.nvidia.com/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${key}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  })
  if (!res.ok) {
    console.warn('[LLM_DEBUG] chatJSON HTTP', res.status)
    return null
  }
  const data = await res.json() as any
  let text: string = (data?.choices?.[0]?.message?.content || '').trim()
  // Strip common code fences if present
  if (text.startsWith('```')) {
    text = text.replace(/^```[a-zA-Z]*\n?/, '').replace(/```\s*$/, '').trim()
  }
  // Attempt direct JSON parse, then fallback to extracting first JSON array/object
  try {
    return JSON.parse(text) as T
  } catch {}
  console.warn('[LLM_DEBUG] chatJSON parse failed, attempting extraction')
  const match = text.match(/[\[{][\s\S]*[\]}]/)
  if (match) {
    try {
      return JSON.parse(match[0]) as T
    } catch {}
  }
  console.warn('[LLM_DEBUG] chatJSON extraction failed')
  return null
}

function tryExtractJSONArray(text: string): string | null {
  // Try code fence JSON
  const fence = text.match(/```json[\s\S]*?```/i) || text.match(/```[\s\S]*?```/)
  if (fence && fence[0]) {
    const inner = fence[0].replace(/```json|```/gi, '').trim()
    const jsonStart = inner.indexOf('[')
    const jsonEnd = inner.lastIndexOf(']')
    if (jsonStart >= 0 && jsonEnd > jsonStart) return inner.slice(jsonStart, jsonEnd + 1)
  }
  // Try raw array in text
  const start = text.indexOf('[')
  const end = text.lastIndexOf(']')
  if (start >= 0 && end > start) return text.slice(start, end + 1)
  return null
}

export async function nvidiaChatJSONRobust<T = unknown>(
  systemPrompt: string,
  userPrompt: string,
  opts?: { modelEnvPrimary?: 'NVIDIA_SMALL' | 'NVIDIA_LARGE'; modelEnvFallback?: 'NVIDIA_SMALL' | 'NVIDIA_LARGE'; maxTokens?: number }
): Promise<T | null> {
  // Primary attempt
  const primary = await nvidiaChatOnce(systemPrompt, userPrompt, {
    modelEnv: opts?.modelEnvPrimary || 'NVIDIA_SMALL',
    maxTokens: opts?.maxTokens ?? 800,
    temperature: 0
  })
  if (primary) {
    const extracted = tryExtractJSONArray(primary) || primary
    try { return JSON.parse(extracted) as T } catch {}
  }
  // Fallback attempt with larger model
  const fallback = await nvidiaChatOnce(systemPrompt, userPrompt, {
    modelEnv: opts?.modelEnvFallback || 'NVIDIA_LARGE',
    maxTokens: Math.max(800, opts?.maxTokens ?? 800),
    temperature: 0
  })
  if (fallback) {
    const extracted = tryExtractJSONArray(fallback) || fallback
    try { return JSON.parse(extracted) as T } catch {}
  }
  return null
}


