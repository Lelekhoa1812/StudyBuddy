import { NextResponse } from 'next/server'
import { getMongo } from '@/lib/mongo'

export const dynamic = 'force-dynamic'

export async function GET() {
  const envCheck = {
    MONGO_URI: !!process.env.MONGO_URI,
    MONGO_DB: process.env.MONGO_DB || 'studybuddy',
    EMBED_BASE_URL: !!process.env.EMBED_BASE_URL,
    MAX_FILES_PER_UPLOAD: process.env.MAX_FILES_PER_UPLOAD || '15',
    MAX_FILE_MB: process.env.MAX_FILE_MB || '50',
    NODE_ENV: process.env.NODE_ENV,
    VERCEL: process.env.VERCEL,
    VERCEL_ENV: process.env.VERCEL_ENV
  }

  let mongoStatus = 'not_connected'
  let mongoError = null

  try {
    const mongo = await getMongo()
    await mongo.db.command({ ping: 1 })
    mongoStatus = 'connected'
  } catch (error: any) {
    mongoStatus = 'error'
    mongoError = {
      name: error?.name || 'Unknown',
      message: error?.message || String(error),
      code: error?.code || 'UNKNOWN'
    }
  }

  return NextResponse.json({
    environment: envCheck,
    mongo: {
      status: mongoStatus,
      error: mongoError
    }
  })
}