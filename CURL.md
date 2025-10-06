# CURL Test Commands for Ingestion Pipeline

## Backend Configuration
- **URL**: `https://binkhoale1812-studdybuddy-ingestion1.hf.space/`
- **User ID**: `44e65346-8eaa-4f95-b17a-f6219953e7a8`
- **Project ID**: `496e2fad-ec7e-4562-b06a-ea2491f2460`
- **Test Files**: `Lecture5_ML.pdf`, `Lecture6_ANN_DL.pdf`

## 1. Health Check

```bash
curl -X GET "https://binkhoale1812-studdybuddy-ingestion1.hf.space/health" \
  -H "Content-Type: application/json"
```

## 2. Upload Files

```bash
curl -X POST "https://binkhoale1812-studdybuddy-ingestion1.hf.space/upload" \
  -F "user_id=44e65346-8eaa-4f95-b17a-f6219953e7a8" \
  -F "project_id=496e2fad-ec7e-4562-b06a-ea2491f2460" \
  -F "files=@../exefiles/Lecture5_ML.pdf" \
  -F "files=@../exefiles/Lecture6_ANN_DL.pdf"
```

## 3. Check Upload Status

Replace `{JOB_ID}` with the job_id from the upload response:

```bash
curl -X GET "https://binkhoale1812-studdybuddy-ingestion1.hf.space/upload/status?job_id={JOB_ID}" \
  -H "Content-Type: application/json"
```

## 4. List Uploaded Files

```bash
curl -X GET "https://binkhoale1812-studdybuddy-ingestion1.hf.space/files?user_id=44e65346-8eaa-4f95-b17a-f6219953e7a8&project_id=496e2fad-ec7e-4562-b06a-ea2491f2460" \
  -H "Content-Type: application/json"
```

## 5. Get File Chunks (Lecture5_ML.pdf)

```bash
curl -X GET "https://binkhoale1812-studdybuddy-ingestion1.hf.space/files/chunks?user_id=44e65346-8eaa-4f95-b17a-f6219953e7a8&project_id=496e2fad-ec7e-4562-b06a-ea2491f2460&filename=Lecture5_ML.pdf&limit=5" \
  -H "Content-Type: application/json"
```

## 6. Get File Chunks (Lecture6_ANN_DL.pdf)

```bash
curl -X GET "https://binkhoale1812-studdybuddy-ingestion1.hf.space/files/chunks?user_id=44e65346-8eaa-4f95-b17a-f6219953e7a8&project_id=496e2fad-ec7e-4562-b06a-ea2491f2460&filename=Lecture6_ANN_DL.pdf&limit=5" \
  -H "Content-Type: application/json"
```

## Expected Responses

### Health Check Response
```json
{
  "ok": true,
  "mongodb_connected": true,
  "service": "ingestion_pipeline"
}
```

### Upload Response
```json
{
  "job_id": "uuid-string",
  "status": "processing",
  "total_files": 2
}
```

### Status Response
```json
{
  "job_id": "uuid-string",
  "status": "completed",
  "total": 2,
  "completed": 2,
  "progress": 100.0,
  "last_error": null,
  "created_at": 1234567890.123
}
```

### Files List Response
```json
{
  "files": [
    {
      "filename": "Lecture5_ML.pdf",
      "summary": "Document summary..."
    },
    {
      "filename": "Lecture6_ANN_DL.pdf", 
      "summary": "Document summary..."
    }
  ],
  "filenames": ["Lecture5_ML.pdf", "Lecture6_ANN_DL.pdf"]
}
```

### Chunks Response
```json
{
  "chunks": [
    {
      "user_id": "44e65346-8eaa-4f95-b17a-f6219953e7a8",
      "project_id": "496e2fad-ec7e-4562-b06a-ea2491f2460",
      "filename": "Lecture5_ML.pdf",
      "topic_name": "Machine Learning Introduction",
      "summary": "Chunk summary...",
      "content": "Chunk content...",
      "embedding": [0.1, 0.2, ...],
      "page_span": [1, 3],
      "card_id": "lecture5_ml-c0001"
    }
  ]
}
```

## Testing Steps

1. **Run Health Check**: Verify the service is running
2. **Upload Files**: Upload both PDF files
3. **Monitor Progress**: Check job status until completion
4. **Verify Files**: List uploaded files
5. **Inspect Chunks**: Get document chunks to verify processing

## Troubleshooting

- **Connection Issues**: Check if the backend URL is accessible
- **File Not Found**: Ensure PDF files exist in `../exefiles/` directory
- **Upload Fails**: Check file size limits and format support
- **Processing Stuck**: Monitor job status and check logs