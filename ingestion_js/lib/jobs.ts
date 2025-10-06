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
  await col.insertOne(doc)
}

export async function updateJob(job_id: string, fields: Partial<JobDoc>) {
  const { db } = await getMongo()
  const col = db.collection<JobDoc>('jobs')
  await col.updateOne({ _id: job_id }, { $set: fields })
}

export async function getJob(job_id: string): Promise<JobDoc | null> {
  const { db } = await getMongo()
  const col = db.collection<JobDoc>('jobs')
  return col.findOne({ _id: job_id })
}
