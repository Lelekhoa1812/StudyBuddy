import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET() {
  const env = {
    MONGO_URI: process.env.MONGO_URI ? 'SET' : 'NOT_SET',
    MONGO_DB: process.env.MONGO_DB || 'NOT_SET',
    EMBED_BASE_URL: process.env.EMBED_BASE_URL ? 'SET' : 'NOT_SET',
    NODE_ENV: process.env.NODE_ENV || 'NOT_SET'
  }
  
  return NextResponse.json({ 
    message: 'Debug info',
    env,
    timestamp: new Date().toISOString()
  })
}
