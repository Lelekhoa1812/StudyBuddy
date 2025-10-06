import { NextRequest, NextResponse } from 'next/server'
import { listFiles } from '@/lib/mongo'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const user_id = searchParams.get('user_id') || ''
  const project_id = searchParams.get('project_id') || ''
  if (!user_id || !project_id) return NextResponse.json({ error: 'user_id and project_id are required' }, { status: 400 })
  const files = await listFiles(user_id, project_id)
  return NextResponse.json({ files, filenames: files.map((f: any) => f.filename) })
}
