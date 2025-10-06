import { NextRequest, NextResponse } from 'next/server'
import { randomUUID } from 'crypto'
import { extractPages } from '@/lib/parser'
import { captionImage } from '@/lib/captioner'
import { buildCardsFromPages } from '@/lib/chunker'
import { embedRemote } from '@/lib/embedder'
import { deleteFileData, storeCards, upsertFileSummary } from '@/lib/mongo'
import { cheapSummarize } from '@/lib/summarizer'
import { createJob, updateJob } from '@/lib/jobs'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function POST(req: NextRequest) {
  const form = await req.formData()
  const user_id = String(form.get('user_id') || '')
  const project_id = String(form.get('project_id') || '')
  const fileEntries = form.getAll('files') as File[]
  const replaceRaw = form.get('replace_filenames') as string | null
  const renameRaw = form.get('rename_map') as string | null

  if (!user_id || !project_id || fileEntries.length === 0) {
    return NextResponse.json({ error: 'user_id, project_id and files are required' }, { status: 400 })
  }

  const maxFiles = parseInt(process.env.MAX_FILES_PER_UPLOAD || '15', 10)
  const maxMb = parseInt(process.env.MAX_FILE_MB || '50', 10)
  if (fileEntries.length > maxFiles) return NextResponse.json({ error: `Too many files. Max ${maxFiles} allowed per upload.` }, { status: 400 })

  let replaceSet = new Set<string>()
  try { if (replaceRaw) replaceSet = new Set<string>(JSON.parse(replaceRaw)) } catch {}
  let renameMap: Record<string, string> = {}
  try { if (renameRaw) renameMap = JSON.parse(renameRaw) } catch {}

  const preloaded: Array<{ name: string; buf: Buffer }> = []
  for (const f of fileEntries) {
    const arr = Buffer.from(await f.arrayBuffer())
    const sizeMb = arr.byteLength / (1024 * 1024)
    if (sizeMb > maxMb) return NextResponse.json({ error: `${f.name} exceeds ${maxMb} MB limit` }, { status: 400 })
    const eff = renameMap[f.name] || f.name
    preloaded.push({ name: eff, buf: arr })
  }

  const job_id = randomUUID()
  await createJob(job_id, preloaded.length)

  // Fire-and-forget background processing; response immediately
  processAll(job_id, user_id, project_id, preloaded, replaceSet).catch(async (e) => {
    await updateJob(job_id, { status: 'failed', last_error: String(e) })
  })

  return NextResponse.json({ job_id, status: 'processing', total_files: preloaded.length })
}

async function processAll(job_id: string, user_id: string, project_id: string, files: Array<{ name: string; buf: Buffer }>, replaceSet: Set<string>) {
  for (let i = 0; i < files.length; i++) {
    const { name: fname, buf } = files[i]
    try {
      if (replaceSet.has(fname)) {
        await deleteFileData(user_id, project_id, fname)
      }

      const pages = await extractPages(fname, buf)

      // Best-effort captioning: parser doesn’t expose images; keep behavior parity by skipping or integrating if images available.
      // If images were available, we would append [Image] caption lines to page text here.

      const cards = await buildCardsFromPages(pages, fname, user_id, project_id)
      const vectors = await embedRemote(cards.map(c => c.content))
      for (let k = 0; k < cards.length; k++) (cards[k] as any).embedding = vectors[k]

      await storeCards(cards)

      const fullText = pages.map(p => p.text || '').join('\n\n')
      const summary = await cheapSummarize(fullText, 6)
      await upsertFileSummary(user_id, project_id, fname, summary)

      await updateJob(job_id, { completed: i + 1, status: (i + 1) < files.length ? 'processing' as const : 'completed' as const })
    } catch (e: any) {
      await updateJob(job_id, { completed: i + 1, last_error: String(e) })
    }
  }
}
