import { NextRequest, NextResponse } from 'next/server'
import { getJob } from '@/lib/jobs'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const job_id = searchParams.get('job_id') || ''
  if (!job_id) return NextResponse.json({ error: 'job_id is required' }, { status: 400 })
  const job = await getJob(job_id)
  if (!job) return NextResponse.json({ error: 'job not found' }, { status: 404 })
  return NextResponse.json({ job_id, status: job.status, total: job.total, completed: job.completed, last_error: job.last_error })
}
