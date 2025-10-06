import { getMongo } from './mongo'

export type JobDoc = {
  _id: string
  created_at: number
  total: number
  completed: number
  status: 'processing' | 'completed' | 'failed'
  last_error: string | null
}

export async function createJob(job_id: string, total: number) {
  const { db } = await getMongo()
  const col = db.collection<JobDoc>('jobs')
  const doc: JobDoc = { _id: job_id, created_at: Date.now() / 1000, total, completed: 0, status: 'processing', last_error: null }
  console.log(`[JOB_DEBUG] Creating job ${job_id} with total ${total}`)
  await col.insertOne(doc)
  console.log(`[JOB_DEBUG] Job ${job_id} created successfully`)
}

export async function updateJob(job_id: string, fields: Partial<JobDoc>) {
  const { db } = await getMongo()
  const col = db.collection<JobDoc>('jobs')
  console.log(`[JOB_DEBUG] Updating job ${job_id} with fields:`, fields)
  await col.updateOne({ _id: job_id }, { $set: fields })
  console.log(`[JOB_DEBUG] Job ${job_id} updated successfully`)
}

export async function getJob(job_id: string): Promise<JobDoc | null> {
  const { db } = await getMongo()
  const col = db.collection<JobDoc>('jobs')
  console.log(`[JOB_DEBUG] Getting job ${job_id}`)
  const job = await col.findOne({ _id: job_id })
  console.log(`[JOB_DEBUG] Job ${job_id} found:`, !!job)
  return job
}
