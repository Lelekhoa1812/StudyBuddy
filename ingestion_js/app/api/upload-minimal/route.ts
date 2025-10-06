import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'
export const maxDuration = 300

export async function POST(req: NextRequest) {
  try {
    const form = await req.formData()
    const user_id = form.get('user_id')
    const project_id = form.get('project_id')
    const files = form.getAll('files')
    
    console.log('Minimal upload received:', { user_id, project_id, fileCount: files.length })
    
    // Return a job ID for testing
    const job_id = 'test-job-' + Date.now()
    
    return NextResponse.json({ 
      job_id,
      status: 'processing',
      total_files: files.length
    })
  } catch (error) {
    console.error('Minimal upload error:', error)
    return NextResponse.json({ error: String(error) }, { status: 500 })
  }
}
