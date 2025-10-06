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

## Deploy to Vercel

- Root directory: `ingestion_js`
- Set Project Settings → Build Command: `next build`
- Output: Next.js default
- Environment Variables: set the vars above in Vercel

## cURL Samples

Replace `BASE` with your deployment URL.

Health:

```bash
curl -X GET "$BASE/api/health" -H "Content-Type: application/json"
```

Upload:

```bash
curl -X POST "$BASE/api/upload" \
  -F "user_id=YOUR_USER_ID" \
  -F "project_id=YOUR_PROJECT_ID" \
  -F "files=@../exefiles/Lecture5_ML.pdf" \
  -F "files=@../exefiles/Lecture6_ANN_DL.pdf"
```

Status:

```bash
curl -X GET "$BASE/api/upload/status?job_id=YOUR_JOB_ID" -H "Content-Type: application/json"
```

List Files:

```bash
curl -X GET "$BASE/api/files?user_id=YOUR_USER_ID&project_id=YOUR_PROJECT_ID" -H "Content-Type: application/json"
```

Get Chunks:

```bash
curl -X GET "$BASE/api/files/chunks?user_id=YOUR_USER_ID&project_id=YOUR_PROJECT_ID&filename=Lecture5_ML.pdf&limit=5" -H "Content-Type: application/json"
```

## Notes

- Jobs are tracked in MongoDB collection `jobs` for serverless safety.
- Vector dim assumed 384 to match `all-MiniLM-L6-v2`.
- PDF/DOCX parsing uses Node libraries; image extraction is best-effort.


