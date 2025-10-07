import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'
export const maxDuration = 300

export async function POST(req: NextRequest) {
  try {
    const form = await req.formData()
    const file = form.get('file') as unknown as File
    if (!file) return NextResponse.json({ error: 'file is required' }, { status: 400 })

    const buf = Buffer.from(await file.arrayBuffer())
    const { extractPages } = await import('../../../lib/parser')
    const pages = await extractPages(file.name, buf)

    return NextResponse.json({
      filename: file.name,
      size_bytes: buf.length,
      pages_count: pages.length,
      pages: pages.map(p => ({
        page_num: p.page_num,
        text_length: p.text.length,
        preview: p.text.slice(0, 140)
      }))
    })
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 })
  }
}
