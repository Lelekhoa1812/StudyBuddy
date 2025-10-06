import { NextResponse } from 'next/server'
import { getMongo, ensureIndexes } from '@/lib/mongo'

export const dynamic = 'force-dynamic'

export async function GET() {
  let mongodb_connected = false
  let mongo_error = null
  
  try {
    const mongo = await getMongo()
    await mongo.db.command({ ping: 1 })
    await ensureIndexes()
    mongodb_connected = true
  } catch (error: any) {
    mongodb_connected = false
    mongo_error = {
      name: error?.name || 'Unknown',
      message: error?.message || String(error),
      code: error?.code || 'UNKNOWN'
    }
  }
  
  return NextResponse.json({ 
    ok: true, 
    mongodb_connected, 
    service: 'ingestion_pipeline',
    mongo_error
  })
}
