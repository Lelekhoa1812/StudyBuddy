import { NextRequest, NextResponse } from 'next/server'
import { randomUUID } from 'crypto'
import { extractPages } from '@/lib/parser'
import { buildCardsFromPages } from '@/lib/chunker'
import { embedRemote } from '@/lib/embedder'
import { deleteFileData, storeCards, upsertFileSummary } from '@/lib/mongo'
import { cheapSummarize } from '@/lib/summarizer'
import { createJob, updateJob } from '@/lib/jobs'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'
export const maxDuration = 300 // 5 minutes for Vercel Pro plan

export async function POST(req: NextRequest) {
  // Ensure envs
  if (!process.env.MONGO_URI) {
    return NextResponse.json({ error: 'Server not configured: MONGO_URI missing' }, { status: 500 })
  }
  if (!process.env.EMBED_BASE_URL) {
    return NextResponse.json({ error: 'Server not configured: EMBED_BASE_URL missing' }, { status: 500 })
  }

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

  // For Vercel serverless, we need to process synchronously due to timeout limits
  // Start processing immediately
  try {
    await processAll(job_id, user_id, project_id, preloaded, replaceSet)
    await updateJob(job_id, { status: 'completed' })
    return NextResponse.json({ job_id, status: 'completed', total_files: preloaded.length })
  } catch (e) {
    console.error(`[UPLOAD_DEBUG] Processing failed for job ${job_id}:`, e)
    await updateJob(job_id, { status: 'failed', last_error: String(e) })
    return NextResponse.json({ job_id, status: 'failed', total_files: preloaded.length, error: String(e) })
  }
}

async function processAll(job_id: string, user_id: string, project_id: string, files: Array<{ name: string; buf: Buffer }>, replaceSet: Set<string>) {
  console.log(`[UPLOAD_DEBUG] Starting processing for job ${job_id} with ${files.length} files`)
  
  for (let i = 0; i < files.length; i++) {
    const { name: fname, buf } = files[i]
    console.log(`[UPLOAD_DEBUG] Processing file ${i + 1}/${files.length}: ${fname} (${buf.length} bytes)`)
    
    try {
      if (replaceSet.has(fname)) {
        console.log(`[UPLOAD_DEBUG] Replacing existing data for ${fname}`)
        await deleteFileData(user_id, project_id, fname)
      }

      console.log(`[UPLOAD_DEBUG] Extracting pages from ${fname}`)
      const pages = await extractPages(fname, buf)
      console.log(`[UPLOAD_DEBUG] Extracted ${pages.length} pages`)

      // Process images with captions (best effort - images not extracted in current parser)
      // This matches Python behavior where captions are appended to page text
      // Note: Current parser doesn't extract images, so captioning is skipped
      // This maintains API compatibility while avoiding complex image processing

      console.log(`[UPLOAD_DEBUG] Building cards from pages`)
      const cards = await buildCardsFromPages(pages, fname, user_id, project_id)
      console.log(`[UPLOAD_DEBUG] Built ${cards.length} cards`)

      console.log(`[UPLOAD_DEBUG] Generating embeddings for ${cards.length} cards`)
      const vectors = await embedRemote(cards.map(c => c.content))
      console.log(`[UPLOAD_DEBUG] Generated ${vectors.length} embeddings`)
      
      for (let k = 0; k < cards.length; k++) (cards[k] as any).embedding = vectors[k]

      console.log(`[UPLOAD_DEBUG] Storing cards in MongoDB`)
      await storeCards(cards)

      console.log(`[UPLOAD_DEBUG] Creating file summary`)
      const fullText = pages.map(p => p.text || '').join('\n\n')
      const summary = await cheapSummarize(fullText, 6)
      await upsertFileSummary(user_id, project_id, fname, summary)

      console.log(`[UPLOAD_DEBUG] Updating job progress: ${i + 1}/${files.length}`)
      await updateJob(job_id, { completed: i + 1, status: (i + 1) < files.length ? 'processing' as const : 'completed' as const })
      
      console.log(`[UPLOAD_DEBUG] Successfully processed ${fname}`)
    } catch (e: any) {
      console.error(`[UPLOAD_DEBUG] Error processing ${fname}:`, e)
      console.error(`[UPLOAD_DEBUG] Error stack:`, e.stack)
      await updateJob(job_id, { completed: i + 1, status: 'failed' as const, last_error: String(e) })
      break // Stop processing on first error
    }
  }
  
  console.log(`[UPLOAD_DEBUG] Finished processing job ${job_id}`)
}
