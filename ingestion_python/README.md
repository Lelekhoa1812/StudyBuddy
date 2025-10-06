---
title: StuddyBuddy Ingestion
emoji: ⚙️
colorFrom: blue
colorTo: pink
sdk: docker
pinned: false
license: mit
short_description: 'backend for data ingestion'
---

# Ingestion Pipeline

A dedicated service for processing file uploads and storing them in MongoDB Atlas. This service mirrors the main system's file processing functionality while running as a separate service to share the processing load.

[API docs](CURL.md)

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                USER INTERFACE                                   │
│  ┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐              │
│  │   Frontend UI   │    │  Load Balancer   │    │  Main System    │              │
│  │                 │◄──►│                  │◄──►│   (Port 7860)   │              │
│  │ - File Upload   │    │ - Route Requests │    │ - Chat & Reports│              │
│  │ - Chat Interface│    │ - Health Checks │    │ - User Management│             │
│  │ - Project Mgmt │    │ - Load Balancing │    │ - Analytics     │              │
│  └─────────────────┘    └──────────────────┘    └─────────────────┘              │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              INGESTION PIPELINE                                │
│  ┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐              │
│  │ File Processing │    │   Data Storage   │    │   Monitoring    │              │
│  │ - PDF/DOCX Parse│    │ - MongoDB Atlas │    │ - Job Status    │              │
│  │ - Image Caption │    │ - Vector Search │    │ - Health Checks │              │
│  │ - Text Chunking │    │ - Embeddings    │    │ - Error Handling│              │
│  │ - Embedding Gen │    │ - User/Project  │    │ - Logging       │              │
│  └─────────────────┘    └──────────────────┘    └─────────────────┘              │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              SHARED DATABASE                                   │
│  ┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐              │
│  │   MongoDB Atlas  │    │   Collections    │    │   Indexes       │              │
│  │                 │    │ - chunks         │    │ - Vector Search │              │
│  │ - Same Cluster  │    │ - files          │    │ - Text Search   │              │
│  │ - Same Database │    │ - chat_sessions  │    │ - User/Project  │              │
│  │ - Same Schema   │    │ - chat_messages  │    │ - Performance   │              │
│  └─────────────────┘    └──────────────────┘    └─────────────────┘              │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## 📁 Project Structure

```
ingestion_pipeline/
├── __init__.py
├── app.py                    # Main FastAPI application
├── requirements.txt          # Python dependencies
├── Dockerfile               # HuggingFace deployment
├── deploy.sh               # Deployment script
├── test_pipeline.py        # Test script
├── README.md               # This file
├── config/               # Configuration
│   ├── __init__.py
│   └── settings.py
├── api/                   # API layer
│   ├── __init__.py
│   ├── models.py         # Pydantic models
│   └── routes.py         # API routes
└── services/             # Business logic
    ├── __init__.py
    └── ingestion_service.py
```

## 🚀 Quick Start

### Prerequisites
- Docker
- MongoDB Atlas cluster
- Python 3.11+


## 🔧 API Endpoints

### Health Check
```http
GET /health
```

### Upload Files
```http
POST /upload
Content-Type: multipart/form-data

user_id: string
project_id: string
files: File[]
replace_filenames: string (optional)
rename_map: string (optional)
```

### Job Status
```http
GET /upload/status?job_id={job_id}
```

### List Files
```http
GET /files?user_id={user_id}&project_id={project_id}
```

### Get File Chunks
```http
GET /files/chunks?user_id={user_id}&project_id={project_id}&filename={filename}&limit={limit}
```

## 🔄 Data Flow

### File Processing Pipeline
1. **File Upload**: User uploads files via frontend
2. **Load Balancing**: Request routed to ingestion pipeline
3. **File Processing**: 
   - PDF/DOCX parsing with image extraction
   - BLIP image captioning
   - Semantic chunking with overlap
   - Embedding generation (all-MiniLM-L6-v2)
4. **Data Storage**: 
   - Chunks stored in `chunks` collection
   - File summaries in `files` collection
   - Both scoped by `user_id` and `project_id`
5. **Response**: Job ID returned for progress tracking

### Data Consistency
- **Same Database**: Uses identical MongoDB Atlas cluster
- **Same Collections**: Stores in `chunks` and `files` collections
- **Same Schema**: Identical data structure and metadata
- **Same Scoping**: All data scoped by `user_id` and `project_id`
- **Same Indexes**: Uses identical database indexes

## 🐳 Docker Deployment

### HuggingFace Spaces
The service is designed for HuggingFace Spaces deployment with:
- Port 7860 (HuggingFace default)
- Non-root user for security
- HuggingFace cache directories
- Model preloading and warmup

### Logging
- Comprehensive logging for all operations
- Error tracking and debugging
- Performance monitoring

### Job Tracking
- Upload progress monitoring
- Error handling and reporting
- Status updates

## 🔧 Configuration

### Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `MONGO_URI` | Required | MongoDB connection string |
| `MONGO_DB` | `studybuddy` | Database name |
| `EMBED_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Embedding model |
| `ATLAS_VECTOR` | `0` | Enable Atlas Vector Search |
| `MAX_FILES_PER_UPLOAD` | `15` | Maximum files per upload |
| `MAX_FILE_MB` | `50` | Maximum file size in MB |
| `INGESTION_PORT` | `7860` | Service port |

### Processing Configuration
- **Vector Dimension**: 384 (all-MiniLM-L6-v2)
- **Chunk Max Words**: 500
- **Chunk Min Words**: 150
- **Chunk Overlap**: 50 words

## 🔒 Security

### Security Features
- Non-root user in Docker container
- Input validation and sanitization
- Error handling and logging
- Rate limiting (configurable)

### Best Practices
- Use environment variables for secrets
- Regular security updates
- Monitor logs for anomalies
- Implement proper access controls

## 🚀 Performance

### Optimization Features
- Lazy loading of ML models
- Efficient file processing
- Background task processing
- Memory management

### Scaling
- Horizontal scaling support
- Load balancing ready
- Resource optimization
- Performance monitoring

## 📚 Integration

### Main System Integration
The ingestion pipeline is designed to work seamlessly with the main system:
- Same API endpoints
- Same data structures
- Same processing pipeline
- Same storage format

### Load Balancer Integration
- Automatic request routing
- Health check integration
- Failover support
- Performance monitoring

## 🐛 Troubleshooting

### Common Issues
1. **MongoDB Connection**: Verify `MONGO_URI` is correct
2. **Port Conflicts**: Ensure port 7860 is available
3. **Model Loading**: Check HuggingFace cache permissions
4. **File Processing**: Verify file format support

## 📈 Future Enhancements

### Planned Features
- Multiple file format support
- Advanced chunking strategies
- Performance optimizations
- Enhanced monitoring

### Scalability
- Kubernetes deployment
- Auto-scaling support
- Load balancing improvements
- Resource optimization
