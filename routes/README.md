# Routes Directory

API routes for the EdSummariser application, providing RESTful endpoints for authentication, file management, chat functionality, report generation, and project management.

## 🚀 Core Features

### **Authentication** (`auth.py`)
- **User Registration**: Secure signup with email validation
- **User Login**: Password verification with PBKDF2 hashing
- **Security**: Salt-based password hashing with 120,000 iterations

### **Chat System** (`chats.py`)
- **Intelligent Chat**: Memory-enhanced conversations with context awareness
- **Smart Context**: Integration with memory planning system for enhancement requests
- **Query Variations**: AI-powered query expansion for better retrieval
- **Web Search**: Optional web augmentation for comprehensive answers
- **Session Management**: Real-time status tracking and session continuity
- **Memory Integration**: Automatic Q&A summarization and storage

### **File Management** (`files.py`)
- **Multi-format Upload**: PDF, DOCX support with background processing
- **Image Captioning**: BLIP-based automatic image description
- **Semantic Chunking**: Intelligent document segmentation
- **Vector Embeddings**: All-MiniLM-L6-v2 embedding generation
- **File Summaries**: Automatic document summarization
- **Progress Tracking**: Real-time upload status monitoring

### **Report Generation** (`reports.py`)
- **Chain of Thought Planning**: AI-powered report structure planning
- **Comprehensive Analysis**: Multi-level detailed analysis execution
- **Memory Enhancement**: Integration with conversation memory
- **PDF Export**: Professional report generation with citations
- **Quality Assessment**: Content quality and authority scoring
- **Web Integration**: Optional web research augmentation

### **Project Management** (`projects.py`)
- **Project CRUD**: Create, read, update, delete operations
- **User Isolation**: Project ownership and access control
- **Data Cleanup**: Cascading deletion of associated data
- **Metadata Tracking**: Creation and update timestamps

### **Search & Web** (`search.py`)
- **Intelligent Search**: AI-powered keyword extraction and strategy generation
- **Multi-source Search**: DuckDuckGo integration with multiple strategies
- **Content Processing**: Jina Reader for clean content extraction
- **Relevance Scoring**: Multi-factor content relevance assessment
- **Quality Validation**: Cross-source information validation
- **Authority Scoring**: Domain and content authority assessment

### **Health & Monitoring** (`health.py`)
- **System Health**: Basic health check endpoint
- **Database Testing**: Connection and operation validation
- **RAG Status**: Vector store and database availability checks

## 📁 Route Structure

```
routes/
├── README.md           # This documentation
├── auth.py             # Authentication endpoints
├── chats.py            # Chat and conversation endpoints
├── files.py            # File upload and management
├── health.py           # Health check and monitoring
├── projects.py         # Project management
├── reports.py          # Report generation
└── search.py           # Web search and content processing
```

## 🔧 Key Endpoints

### **Authentication**
- `POST /auth/signup` - User registration
- `POST /auth/login` - User authentication

### **Chat System**
- `POST /chat` - Main chat endpoint with memory integration
- `POST /chat/search` - Web-augmented chat
- `POST /chat/save` - Save chat messages
- `GET /chat/history` - Retrieve chat history
- `DELETE /chat/history` - Clear chat history
- `GET /chat/status/{session_id}` - Get chat processing status

### **File Management**
- `POST /upload` - Upload and process files
- `GET /upload/status` - Check upload progress
- `GET /files` - List project files
- `DELETE /files` - Delete specific file
- `GET /cards` - List document chunks
- `GET /file-summary` - Get file summary

### **Report Generation**
- `POST /report` - Generate comprehensive report
- `POST /report/pdf` - Export report as PDF
- `GET /report/status/{session_id}` - Get report generation status

### **Project Management**
- `POST /projects/create` - Create new project
- `GET /projects` - List user projects
- `GET /projects/{project_id}` - Get specific project
- `DELETE /projects/{project_id}` - Delete project

### **Health & Monitoring**
- `GET /healthz` - Basic health check
- `GET /test-db` - Database connection test
- `GET /rag-status` - RAG system status

## 🧠 Memory Integration

All chat and report endpoints integrate with the memory planning system:

- **Smart Context**: Automatic context retrieval based on user intent
- **Enhancement Detection**: Specialized handling for "Enhance..." requests
- **Q&A Focus**: Prioritizes past Q&A data for detailed responses
- **Session Continuity**: Maintains conversation context across requests
- **Memory Consolidation**: Automatic memory optimization and pruning

## 🔄 Processing Flow

### **Chat Request Flow**
1. **Intent Detection** → Determine user intent (enhancement, clarification, etc.)
2. **Memory Planning** → Select optimal retrieval strategy
3. **Context Retrieval** → Get relevant past Q&A and semantic context
4. **Query Enhancement** → Generate query variations for better search
5. **Vector Search** → Multi-strategy document search
6. **Answer Generation** → AI-powered response with citations
7. **Memory Storage** → Save Q&A summary for future use

### **Report Generation Flow**
1. **Memory Enhancement** → Enhance instructions with conversation context
2. **CoT Planning** → Generate detailed report structure plan
3. **Subtask Execution** → Execute comprehensive analysis for each section
4. **Content Synthesis** → Combine analyses into coherent report
5. **Quality Validation** → Ensure report meets quality standards

## 🛠️ Configuration

### **Environment Variables**
```bash
# File Upload Limits
MAX_FILES_PER_UPLOAD=15
MAX_FILE_MB=50

# API Keys (configured in helpers/setup.py)
GEMINI_API_KEY=your_gemini_key
NVIDIA_API_KEY=your_nvidia_key
```

### **Dependencies**
- FastAPI for API framework
- MongoDB for data persistence
- NVIDIA API for AI processing
- Google Gemini for large model inference
- All-MiniLM-L6-v2 for embeddings
- BLIP for image captioning

## 📊 Status Tracking

Real-time status updates for long-running operations:

- **Chat Processing**: receiving → processing → planning → searching → thinking → generating → complete
- **Report Generation**: receiving → planning → processing → thinking → generating → complete
- **File Upload**: processing → completed (with progress percentage)

## 🔒 Security Features

- **Password Hashing**: PBKDF2 with 120,000 iterations
- **Input Validation**: Comprehensive request validation
- **User Isolation**: Project and data access control
- **Error Handling**: Graceful error responses without information leakage

## 🚀 Performance Optimizations

- **Background Processing**: File uploads and report generation
- **Query Variations**: Multiple search strategies for better results
- **Memory Caching**: Session-based context caching
- **Async Processing**: Non-blocking operations throughout
- **Smart Fallbacks**: Graceful degradation when services unavailable

This routes system provides a comprehensive API for document analysis, intelligent chat, and report generation with advanced memory integration and context awareness.
