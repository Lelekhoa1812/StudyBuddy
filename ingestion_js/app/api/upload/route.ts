import { NextRequest, NextResponse } from 'next/server'
import { randomUUID } from 'crypto'
import { extractPages } from '../../../lib/parser'
import { buildCardsFromPages } from '../../../lib/chunker'
import { embedRemote } from '../../../lib/embedder'
import { deleteFileData, storeCards, upsertFileSummary } from '../../../lib/mongo'
import { cheapSummarize } from '../../../lib/summarizer'
import { createJob, updateJob } from '../../../lib/jobs'

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

  const job_id = randomUUID()
  const formData = await req.formData()

  const user_id = formData.get('user_id')?.toString()
  const project_id = formData.get('project_id')?.toString()
  const files = formData.getAll('files') as File[]
  const replace_filenames_str = formData.get('replace_filenames')?.toString()
  const rename_map_str = formData.get('rename_map')?.toString()

  if (!user_id || !project_id) {
    return NextResponse.json({ error: 'user_id and project_id are required' }, { status: 400 })
  }
  if (!files || files.length === 0) {
    return NextResponse.json({ error: 'No files uploaded' }, { status: 400 })
  }

  const MAX_FILES_PER_UPLOAD = parseInt(process.env.MAX_FILES_PER_UPLOAD || '15')
  const MAX_FILE_MB = parseInt(process.env.MAX_FILE_MB || '50')

  if (files.length > MAX_FILES_PER_UPLOAD) {
    return NextResponse.json(
      { error: `Too many files. Max ${MAX_FILES_PER_UPLOAD} allowed per upload.` },
      { status: 400 }
    )
  }

  let replace_set = new Set<string>()
  try {
    if (replace_filenames_str) {
      replace_set = new Set(JSON.parse(replace_filenames_str))
    }
  } catch (e) {
    console.warn(`Failed to parse replace_filenames: ${e}`)
  }

  let rename_map: { [key: string]: string } = {}
  try {
    if (rename_map_str) {
      rename_map = JSON.parse(rename_map_str)
    }
  } catch (e) {
    console.warn(`Failed to parse rename_map: ${e}`)
  }

  const preloaded_files: { fname: string; buf: Buffer }[] = []
  for (const file of files) {
    const raw = Buffer.from(await file.arrayBuffer())
    if (raw.length > MAX_FILE_MB * 1024 * 1024) {
      return NextResponse.json(
        { error: `${file.name} exceeds ${MAX_FILE_MB} MB limit` },
        { status: 400 }
      )
    }
    const eff_name = rename_map[file.name] || file.name
    preloaded_files.push({ fname: eff_name, buf: raw })
  }

  await createJob(job_id, preloaded_files.length)

  // Process in background
  ;(async () => {
    await processFilesInBackground(job_id, user_id, project_id, preloaded_files, replace_set)
  })()

  return NextResponse.json(
    {
      job_id,
      status: 'processing',
      total_files: preloaded_files.length,
    },
    { status: 200 }
  )
}

async function processFilesInBackground(
  job_id: string,
  user_id: string,
  project_id: string,
  preloaded_files: { fname: string; buf: Buffer }[],
  replace_set: Set<string>
) {
  for (let i = 0; i < preloaded_files.length; i++) {
    const { fname, buf } = preloaded_files[i]
    try {
      console.log(`[UPLOAD_DEBUG] Processing file ${i + 1}/${preloaded_files.length}: ${fname}`)

      if (replace_set.has(fname)) {
        console.log(`[UPLOAD_DEBUG] Deleting existing data for ${fname}`)
        await deleteFileData(user_id, project_id, fname)
      }

      console.log(`[UPLOAD_DEBUG] Extracting pages from ${fname}`)
      const pages = await extractPages(fname, buf)
      console.log(`[UPLOAD_DEBUG] Extracted ${pages.length} pages`)

      console.log(`[UPLOAD_DEBUG] Building cards from pages`)
      const cards = await buildCardsFromPages(pages, fname, user_id, project_id)
      console.log(`[UPLOAD_DEBUG] Built ${cards.length} cards`)

      console.log(`[UPLOAD_DEBUG] Generating embeddings for ${cards.length} cards`)
      const vectors = await embedRemote(cards.map(c => c.content))
      if (vectors.length !== cards.length) {
        throw new Error(`Embedding mismatch: got ${vectors.length} for ${cards.length} cards`)
      }
      for (let j = 0; j < cards.length; j++) {
        cards[j].embedding = vectors[j]
      }
      console.log(`[UPLOAD_DEBUG] Generated embeddings`)

      console.log(`[UPLOAD_DEBUG] Storing ${cards.length} cards in MongoDB`)
      await storeCards(cards)
      console.log(`[UPLOAD_DEBUG] Stored cards`)

      const full_text = pages.map(p => p.text).join('\n\n')
      const file_summary = await cheapSummarize(full_text, 6)
      await upsertFileSummary(user_id, project_id, fname, file_summary)
      console.log(`[UPLOAD_DEBUG] Upserted file summary for ${fname}`)

      await updateJob(job_id, { completed: i + 1, status: i === preloaded_files.length - 1 ? 'completed' : 'processing' })
      
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
