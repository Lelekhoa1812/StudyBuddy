import { NextRequest, NextResponse } from 'next/server'
import { getFileChunks } from '@/lib/mongo'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const user_id = searchParams.get('user_id') || ''
  const project_id = searchParams.get('project_id') || ''
  const filename = searchParams.get('filename') || ''
  const limit = parseInt(searchParams.get('limit') || '20', 10)
  if (!user_id || !project_id || !filename) return NextResponse.json({ error: 'user_id, project_id and filename are required' }, { status: 400 })
  const chunks = await getFileChunks(user_id, project_id, filename, limit)
  return NextResponse.json({ chunks })
}
