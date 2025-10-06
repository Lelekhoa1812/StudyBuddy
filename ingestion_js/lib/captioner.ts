type ImageLike = { data: Buffer } | Blob | ArrayBuffer | string

async function imageToJpegBase64(input: any): Promise<string> {
  // input will be a Buffer or ArrayBuffer from parser; expect Buffer for server-side
  if (typeof input === 'string') return input
  const b64 = Buffer.isBuffer(input) ? input.toString('base64') : Buffer.from(input).toString('base64')
  return b64
}

function getNvidiaKey(): string | null {
  const direct = process.env.NVIDIA_API || null
  if (direct) return direct
  for (let i = 1; i <= 5; i++) {
    const k = process.env[`NVIDIA_API_${i}`]
    if (k) return k
  }
  return null
}

export async function captionImage(imageBuffer: Buffer): Promise<string> {
  const key = getNvidiaKey()
  if (!key) return ''
  const imgB64 = await imageToJpegBase64(imageBuffer)
  const system_prompt =
    'You are an expert vision captioner. Produce a precise, information-dense caption of the image. Do not include conversational phrases or meta commentary.'
  const user_prompt = 'Caption this image at the finest level of detail. Return only the caption text.'
  const payload = {
    model: process.env.NVIDIA_MAVERICK_MODEL || 'meta/llama-4-maverick-17b-128e-instruct',
    messages: [
      { role: 'system', content: system_prompt },
      {
        role: 'user',
        content: [
          { type: 'text', text: user_prompt },
          { type: 'image_url', image_url: { url: `data:image/jpeg;base64,${imgB64}` } }
        ]
      }
    ],
    max_tokens: 512,
    temperature: 0.2,
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
  return normalizeCaption(text)
}

export function normalizeCaption(text: string): string {
  if (!text) return ''
  let t = text.trim()
  const banned = [
    'sure,', 'sure.', 'sure', 'here is', 'here are', 'this image', 'the image', 'image shows',
    'the picture', 'the photo', 'the text describes', 'the text describe', 'it shows', 'it depicts',
    'caption:', 'description:', 'output:', 'result:', 'answer:', 'analysis:', 'observation:'
  ]
  const lower = t.toLowerCase()
  for (const p of banned) {
    if (lower.startsWith(p)) {
      t = t.slice(p.length).trimStart()
      break
    }
  }
  return t.replace(/^['\"]|['\"]$/g, '').trim()
}
