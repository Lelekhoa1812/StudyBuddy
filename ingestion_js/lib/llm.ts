function getNvidiaKey(): string | null {
  const direct = process.env.NVIDIA_API || null
  if (direct) return direct
  for (let i = 1; i <= 5; i++) {
    const k = process.env[`NVIDIA_API_${i}`]
    if (k) return k
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

  const modelName = (opts?.modelEnv ? process.env[opts.modelEnv] : undefined)
    || process.env.NVIDIA_MAVERICK_MODEL
    || 'meta/llama-4-8b-instruct'

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
  if (!res.ok) return ''
  const data = await res.json() as any
  const text = data?.choices?.[0]?.message?.content || ''
  return normalizeConcise(text)
}

export async function nvidiaChatJSON<T = unknown>(
  systemPrompt: string,
  userPrompt: string,
  opts?: { modelEnv?: 'NVIDIA_SMALL' | 'NVIDIA_LARGE'; maxTokens?: number; temperature?: number }
): Promise<T | null> {
  const key = getNvidiaKey()
  if (!key) return null

  const modelName = (opts?.modelEnv ? process.env[opts.modelEnv] : undefined)
    || process.env.NVIDIA_MAVERICK_MODEL
    || 'meta/llama-4-8b-instruct'

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
  if (!res.ok) return null
  const data = await res.json() as any
  const text: string = (data?.choices?.[0]?.message?.content || '').trim()
  try {
    return JSON.parse(text) as T
  } catch {
    return null
  }
}


