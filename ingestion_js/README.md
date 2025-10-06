# Ingestion JS (Next.js API)

Mirror of `ingestion_python` implemented as Next.js Route Handlers for Vercel.

## Endpoints

- GET `/api/health`
- POST `/api/upload` (multipart/form-data)
  - `user_id`: string
  - `project_id`: string
  - `files`: File[]
  - `replace_filenames`: JSON string array (optional)
  - `rename_map`: JSON string map (optional)
- GET `/api/upload/status?job_id=...`
- GET `/api/files?user_id=...&project_id=...`
- GET `/api/files/chunks?user_id=...&project_id=...&filename=...&limit=...`

## Environment

- `MONGO_URI`: MongoDB Atlas connection string
- `MONGO_DB`: default `studybuddy`
- `MAX_FILES_PER_UPLOAD`: default `15`
- `MAX_FILE_MB`: default `50`
- `EMBED_BASE_URL`: remote embed service base, provides POST `/embed`
- `NVIDIA_API`, or `NVIDIA_API_1..N`: caption API keys (optional)

## Notes

- Jobs are tracked in MongoDB collection `jobs` for serverless safety.
- Vector dim assumed 384 to match `all-MiniLM-L6-v2`.
- PDF/DOCX parsing uses Node libraries; image extraction is best-effort.


