import { NextRequest, NextResponse } from 'next/server'
import { getMongo } from '../../../lib/mongo'
import { getJob } from '../../../lib/jobs'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(req: NextRequest) {
  try {
    const url = new URL(req.url)
    const job_id = url.searchParams.get('job_id')
    const action = url.searchParams.get('action') || 'status'

    console.log(`[DEBUG] Debug request - action: ${action}, job_id: ${job_id}`)

    switch (action) {
      case 'status':
  if (!job_id) {
          return NextResponse.json({ error: 'job_id required for status check' }, { status: 400 })
        }
        return await debugJobStatus(job_id)

      case 'jobs':
        return await debugAllJobs()

      case 'files':
        return await debugFiles()

      case 'chunks':
        return await debugChunks()

      case 'env':
        return await debugEnvironment()

      case 'health':
        return await debugHealth()

      case 'memory':
        return await debugMemory()

      case 'test-embedding':
        return await debugTestEmbedding()

      case 'test-parser':
        return await debugTestParser()

      default:
        return NextResponse.json({ 
          error: 'Invalid action', 
          available_actions: ['status', 'jobs', 'files', 'chunks', 'env', 'health', 'memory', 'test-embedding', 'test-parser'] 
        }, { status: 400 })
    }
  } catch (error) {
    console.error('[DEBUG] Debug endpoint error:', error)
    return NextResponse.json({ 
      error: 'Debug endpoint failed', 
      details: String(error),
      stack: error instanceof Error ? error.stack : undefined
    }, { status: 500 })
  }
}

async function debugJobStatus(job_id: string) {
  try {
    const job = await getJob(job_id)
    if (!job) {
      return NextResponse.json({ 
        job_id, 
        status: 'not_found',
        message: 'Job not found in database'
      })
    }

    return NextResponse.json({
      job_id,
      job_details: job,
      timestamp: new Date().toISOString(),
      debug_info: {
        created_ago_seconds: Math.floor((Date.now() / 1000) - job.created_at),
        completion_percentage: job.total > 0 ? Math.round((job.completed / job.total) * 100) : 0,
        is_stuck: job.status === 'processing' && (Date.now() / 1000) - job.created_at > 300 // 5 minutes
      }
    })
  } catch (error) {
    return NextResponse.json({ 
      job_id, 
      error: 'Failed to get job status', 
      details: String(error) 
    }, { status: 500 })
  }
}

async function debugAllJobs() {
  try {
    const { db } = await getMongo()
    const jobs = await db.collection('jobs').find({}).sort({ created_at: -1 }).limit(10).toArray()
    
    return NextResponse.json({
      total_jobs: jobs.length,
      recent_jobs: jobs.map(job => ({
        job_id: job._id,
        status: job.status,
        created_at: new Date(job.created_at * 1000).toISOString(),
        completed: job.completed,
        total: job.total,
        last_error: job.last_error,
        is_stuck: job.status === 'processing' && (Date.now() / 1000) - job.created_at > 300
      }))
    })
  } catch (error) {
    return NextResponse.json({ 
      error: 'Failed to get jobs', 
      details: String(error) 
    }, { status: 500 })
  }
}

async function debugFiles() {
  try {
    const { db } = await getMongo()
    const files = await db.collection('files').find({}).sort({ created_at: -1 }).limit(10).toArray()
    
    return NextResponse.json({
      total_files: files.length,
      recent_files: files.map(file => ({
        filename: file.filename,
        user_id: file.user_id,
        project_id: file.project_id,
        created_at: new Date(file.created_at * 1000).toISOString(),
        summary: file.summary?.substring(0, 100) + '...'
      }))
    })
  } catch (error) {
    return NextResponse.json({ 
      error: 'Failed to get files', 
      details: String(error) 
    }, { status: 500 })
  }
}

async function debugChunks() {
  try {
    const { db } = await getMongo()
    const chunks = await db.collection('chunks').find({}).sort({ created_at: -1 }).limit(5).toArray()
    
    return NextResponse.json({
      total_chunks: chunks.length,
      recent_chunks: chunks.map(chunk => ({
        chunk_id: chunk._id,
        filename: chunk.filename,
        user_id: chunk.user_id,
        project_id: chunk.project_id,
        created_at: new Date(chunk.created_at * 1000).toISOString(),
        has_embedding: !!chunk.embedding,
        embedding_length: chunk.embedding?.length || 0,
        content_preview: chunk.content?.substring(0, 100) + '...'
      }))
    })
  } catch (error) {
    return NextResponse.json({ 
      error: 'Failed to get chunks', 
      details: String(error) 
    }, { status: 500 })
  }
}

async function debugEnvironment() {
  const env_vars = {
    MONGO_URI: process.env.MONGO_URI ? 'SET' : 'MISSING',
    EMBED_BASE_URL: process.env.EMBED_BASE_URL ? 'SET' : 'MISSING',
    NVIDIA_API: process.env.NVIDIA_API ? 'SET' : 'MISSING',
    MAX_FILES_PER_UPLOAD: process.env.MAX_FILES_PER_UPLOAD || '15',
    MAX_FILE_MB: process.env.MAX_FILE_MB || '50',
    NODE_ENV: process.env.NODE_ENV || 'development',
    VERCEL: process.env.VERCEL || 'false'
  }

  return NextResponse.json({
    environment: env_vars,
    timestamp: new Date().toISOString(),
    node_version: process.version
  })
}

async function debugHealth() {
  try {
    const { client, db } = await getMongo()
    
    // Test MongoDB connection
    await db.admin().ping()
    
    // Test collections exist
    const collections = await db.listCollections().toArray()
    const collection_names = collections.map(c => c.name)
    
    return NextResponse.json({
      status: 'healthy',
      mongodb: {
        connected: true,
        collections: collection_names,
        has_chunks: collection_names.includes('chunks'),
        has_files: collection_names.includes('files'),
        has_jobs: collection_names.includes('jobs')
      },
      timestamp: new Date().toISOString()
    })
  } catch (error) {
    return NextResponse.json({
      status: 'unhealthy',
      mongodb: {
        connected: false,
        error: String(error)
      },
      timestamp: new Date().toISOString()
    }, { status: 500 })
  }
}

async function debugMemory() {
  try {
    const mu = process.memoryUsage()
    const heapStats: any = {
      rss: mu.rss,
      heapTotal: mu.heapTotal,
      heapUsed: mu.heapUsed,
      external: mu.external,
      arrayBuffers: (mu as any).arrayBuffers
    }
    return NextResponse.json({
      pid: process.pid,
      memory: heapStats,
      uptime_seconds: Math.round(process.uptime()),
      timestamp: new Date().toISOString()
    })
  } catch (error) {
    return NextResponse.json({ error: String(error) }, { status: 500 })
  }
}

async function debugTestEmbedding() {
  try {
    const { embedRemote } = await import('../../../lib/embedder')
    
    const test_texts = ['This is a test document for embedding generation.']
    console.log('[DEBUG] Testing embedding service...')
    
    const start_time = Date.now()
    const vectors = await embedRemote(test_texts)
    const duration = Date.now() - start_time
    
    return NextResponse.json({
      status: 'success',
      test_texts,
      vectors_received: vectors.length,
      vector_dimensions: vectors[0]?.length || 0,
      duration_ms: duration,
      timestamp: new Date().toISOString()
    })
  } catch (error) {
    return NextResponse.json({
      status: 'failed',
      error: String(error),
      timestamp: new Date().toISOString()
    }, { status: 500 })
  }
}

async function debugTestParser() {
  try {
    const { extractPages } = await import('../../../lib/parser')
    
    // Create a simple test PDF-like content
    const test_content = Buffer.from('Test PDF content for parsing')
    console.log('[DEBUG] Testing parser...')
    
    const start_time = Date.now()
    const pages = await extractPages('test.pdf', test_content)
    const duration = Date.now() - start_time
    
    return NextResponse.json({
      status: 'success',
      pages_extracted: pages.length,
      pages: pages.map(p => ({
        page_num: p.page_num,
        text_length: p.text.length,
        images_count: p.images.length,
        text_preview: p.text.substring(0, 100) + '...'
      })),
      duration_ms: duration,
      timestamp: new Date().toISOString()
    })
  } catch (error) {
    return NextResponse.json({
      status: 'failed',
      error: String(error),
      timestamp: new Date().toISOString()
    }, { status: 500 })
  }
}