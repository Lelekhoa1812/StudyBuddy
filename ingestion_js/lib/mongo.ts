import { MongoClient, Db } from 'mongodb'

let client: MongoClient | null = null
let db: Db | null = null

export async function getMongo() {
  if (client && db) return { client, db }
  
  const uri = process.env.MONGO_URI
  const dbName = process.env.MONGO_DB || 'studybuddy'
  
  console.log('[MONGO_DEBUG] Environment check:')
  console.log('[MONGO_DEBUG] MONGO_URI exists:', !!uri)
  console.log('[MONGO_DEBUG] MONGO_DB:', dbName)
  console.log('[MONGO_DEBUG] MONGO_URI starts with:', uri?.substring(0, 20) + '...')
  
  if (!uri) {
    console.error('[MONGO_DEBUG] MONGO_URI is required but not set')
    throw new Error('MONGO_URI is required')
  }
  
  try {
    console.log('[MONGO_DEBUG] Creating MongoClient...')
    client = new MongoClient(uri)
    console.log('[MONGO_DEBUG] Connecting to MongoDB...')
    await client.connect()
    console.log('[MONGO_DEBUG] MongoDB connected successfully')
    
    db = client.db(dbName)
    console.log('[MONGO_DEBUG] Database selected:', dbName)
    
    // Test the connection
    console.log('[MONGO_DEBUG] Testing connection with ping...')
    await db.command({ ping: 1 })
    console.log('[MONGO_DEBUG] Ping successful')
    
    return { client, db }
  } catch (error) {
    console.error('[MONGO_DEBUG] MongoDB connection failed:', error)
    console.error('[MONGO_DEBUG] Error details:', {
      name: error instanceof Error ? error.name : 'Unknown',
      message: error instanceof Error ? error.message : String(error),
      stack: error instanceof Error ? error.stack : undefined
    })
    throw error
  }
}

export const VECTOR_DIM = 384

export async function storeCards(cards: any[]) {
  const { db } = await getMongo()
  if (!cards || !cards.length) return
  for (const c of cards) {
    if (!c.embedding || c.embedding.length !== VECTOR_DIM) {
      throw new Error(`Invalid embedding length; expected ${VECTOR_DIM}`)
    }
  }
  await db.collection('chunks').insertMany(cards, { ordered: false })
}

export async function upsertFileSummary(user_id: string, project_id: string, filename: string, summary: string) {
  const { db } = await getMongo()
  await db.collection('files').updateOne(
    { user_id, project_id, filename },
    { $set: { summary } },
    { upsert: true }
  )
}

export async function listFiles(user_id: string, project_id: string) {
  const { db } = await getMongo()
  const cursor = db.collection('files').find({ user_id, project_id }, { projection: { _id: 0, filename: 1, summary: 1 } }).sort({ filename: 1 })
  return cursor.toArray()
}

export async function getFileChunks(user_id: string, project_id: string, filename: string, limit = 20) {
  const { db } = await getMongo()
  const cursor = db.collection('chunks').find({ user_id, project_id, filename }).limit(limit)
  const out: any[] = []
  for await (const doc of cursor) {
    const d: any = {}
    for (const [k, v] of Object.entries(doc as any)) {
      if (k === '_id') d[k] = String(v)
      // @ts-ignore
      else if (v && typeof v === 'object' && typeof (v as any).toISOString === 'function') d[k] = (v as any).toISOString()
      else d[k] = v as any
    }
    out.push(d)
  }
  return out
}

export async function deleteFileData(user_id: string, project_id: string, filename: string) {
  const { db } = await getMongo()
  await db.collection('chunks').deleteMany({ user_id, project_id, filename })
  await db.collection('files').deleteMany({ user_id, project_id, filename })
}

export async function ensureIndexes() {
  const { db } = await getMongo()
  await db.collection('chunks').createIndex({ user_id: 1, project_id: 1, filename: 1 })
  await db.collection('files').createIndex({ user_id: 1, project_id: 1, filename: 1 })
}
