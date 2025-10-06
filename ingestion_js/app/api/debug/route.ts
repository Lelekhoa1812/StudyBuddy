import { NextRequest, NextResponse } from 'next/server'
import { getMongo } from '@/lib/mongo'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const job_id = searchParams.get('job_id') || ''
  
  if (!job_id) {
    return NextResponse.json({ error: 'job_id is required' }, { status: 400 })
  }
  
  try {
    const { db } = await getMongo()
    // Use any type to bypass TypeScript strict typing for _id field
    const job = await db.collection('jobs').findOne({ _id: job_id } as any)
    
    if (!job) {
      return NextResponse.json({ error: 'Job not found', job_id }, { status: 404 })
    }
    
    return NextResponse.json({ 
      job_id, 
      job,
      mongo_connected: true 
    })
  } catch (error) {
    return NextResponse.json({ 
      error: 'Database error', 
      details: String(error),
      job_id 
    }, { status: 500 })
  }
}