import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function POST(req: NextRequest) {
  try {
    const form = await req.formData()
    const user_id = form.get('user_id')
    const project_id = form.get('project_id')
    const files = form.getAll('files')
    
    console.log('Upload request received:', { user_id, project_id, fileCount: files.length })
    
    return NextResponse.json({ 
      message: 'Upload received successfully',
      user_id,
      project_id,
      fileCount: files.length,
      job_id: 'test-job-123'
    })
  } catch (error) {
    console.error('Upload error:', error)
    return NextResponse.json({ error: String(error) }, { status: 500 })
  }
}
