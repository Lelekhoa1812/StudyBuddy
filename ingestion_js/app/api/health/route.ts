import { NextResponse } from 'next/server'
import { getMongo, ensureIndexes } from '@/lib/mongo'

export const dynamic = 'force-dynamic'

export async function GET() {
  const mongo = await getMongo()
  let mongodb_connected = false
  try {
    await mongo.db.command({ ping: 1 })
    await ensureIndexes()
    mongodb_connected = true
  } catch {
    mongodb_connected = false
  }
  return NextResponse.json({ ok: true, mongodb_connected, service: 'ingestion_pipeline' })
}
