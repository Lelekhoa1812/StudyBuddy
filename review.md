# EdSummariser: Advanced RAG System with Intelligent Memory Architecture

## 🚀 Project Overview

**EdSummariser** (StudyBuddy) is a sophisticated Retrieval-Augmented Generation (RAG) application that revolutionizes document analysis through advanced AI-powered memory systems, multi-model orchestration, and intelligent context management. Built with FastAPI and deployed on Hugging Face Spaces, this system demonstrates cutting-edge techniques in conversational AI and document understanding.

**Live Demo**: [https://binkhoale1812-edsummariser.hf.space](https://binkhoale1812-edsummariser.hf.space)

## 🏗️ Technical Architecture

### Core System Design
- **Backend**: FastAPI with async/await patterns for high-performance document processing
- **Database**: MongoDB with Atlas Vector Search for scalable semantic retrieval
- **Frontend**: Modern vanilla JavaScript with responsive design and real-time status updates
- **Deployment**: Docker containerization optimized for Hugging Face Spaces
- **AI Integration**: Multi-provider API orchestration with intelligent model selection

### Advanced Memory System (`memo/`)
The heart of EdSummariser lies in its sophisticated memory architecture that goes far beyond traditional RAG implementations:

#### **Dual Memory Architecture**
- **Enhanced Memory**: MongoDB-based persistent storage with semantic search capabilities
- **Legacy Memory**: In-memory LRU system ensuring backward compatibility
- **Graceful Fallback**: Automatic degradation when services are unavailable

#### **Intelligent Memory Planning**
- **Intent Detection**: AI-powered classification of user requests (enhancement, clarification, comparison, reference, new topic)
- **Strategy Planning**: Dynamic selection of optimal retrieval strategies based on user intent
- **Context Switching**: Automatic detection and handling of topic changes in conversations
- **Memory Consolidation**: Intelligent pruning to prevent information overload

#### **Memory Types & Specialized Handling**
- `conversation`: Chat history and Q&A pairs with semantic indexing
- `user_preference`: Personalized user behavior patterns
- `project_context`: Project-specific knowledge retention
- `knowledge_fact`: Domain-specific factual information

### Multi-Model AI Orchestration

#### **Four-Tier Model Selection System**
The system implements an intelligent model routing mechanism that optimizes both performance and cost:

1. **NVIDIA Small (Llama-3.1-8b-instruct)**: Simple tasks, basic operations
2. **NVIDIA Medium (Qwen-3-next-80b-a3b-thinking)**: Reasoning tasks, decision-making, context selection
3. **NVIDIA Large (GPT-OSS-120b)**: Content processing, long context analysis
4. **Gemini Pro**: Complex research, comprehensive analysis, advanced reasoning

#### **Dynamic Task Assignment**
- **Easy Tasks**: Immediate execution with NVIDIA Small
- **Reasoning Tasks**: Thinking and decision-making with Qwen's thinking mode
- **Processing Tasks**: Long context and content analysis with NVIDIA Large
- **Complex Tasks**: Research and comprehensive analysis with Gemini Pro

### Advanced RAG Implementation

#### **Multi-Strategy Vector Search**
- **Flat Search**: Exhaustive search for maximum accuracy
- **Hybrid Search**: Combines Atlas and local search strategies
- **Atlas Search**: Cloud-native vector search for scalability
- **Local Search**: Cosine similarity with intelligent sampling

#### **Enhanced Retrieval Features**
- **Query Variations**: AI-generated query expansions for better recall
- **File Relevance Classification**: NVIDIA-powered relevance scoring
- **Semantic Chunking**: Academic-aware document segmentation with overlap preservation
- **Fallback Strategies**: 4-tier fallback system ensuring robust retrieval

#### **Document Processing Pipeline**
1. **Multi-format Support**: PDF and DOCX parsing with PyMuPDF
2. **Image Captioning**: BLIP-based automatic image description
3. **Semantic Chunking**: 150-500 word chunks with 50-word overlap
4. **Vector Embeddings**: All-MiniLM-L6-v2 (384 dimensions)
5. **Metadata Extraction**: Page spans, topics, and automatic summaries

### Intelligent Chat System

#### **Context-Aware Conversations**
- **Smart Context Retrieval**: Automatic context selection based on user intent
- **Enhancement Detection**: Specialized handling for "Enhance..." requests
- **Q&A Prioritization**: Focus on past Q&A data for detailed responses
- **Session Management**: Real-time conversation continuity tracking

#### **Advanced Features**
- **Real-time Status Updates**: Live progress tracking for long-running operations
- **Web Search Integration**: Optional web augmentation with DuckDuckGo and Jina Reader
- **Source Attribution**: Comprehensive citation system with relevance scoring
- **Memory Integration**: Automatic Q&A summarization and storage

### Report Generation System

#### **Chain of Thought Planning**
- **AI-Powered Structure**: Dynamic report planning based on user requirements
- **Multi-level Analysis**: Comprehensive subtask execution with quality checks
- **Content Synthesis**: Advanced integration of multiple information sources
- **PDF Export**: Professional report generation with dark IDE-like code formatting

#### **Quality Assurance**
- **Content Validation**: Cross-source information verification
- **Authority Scoring**: Domain and content authority assessment
- **Quality Metrics**: Multi-factor content relevance evaluation

## 🛠️ Technical Implementation Highlights

### Performance Optimizations
- **Lazy Loading**: Models loaded only when needed to reduce startup time
- **Background Processing**: Async file uploads and report generation
- **Caching Strategies**: Session-based context caching and API key rotation
- **Smart Fallbacks**: Graceful degradation when services are unavailable

### Security & Reliability
- **Password Hashing**: PBKDF2 with 120,000 iterations
- **Input Validation**: Comprehensive request validation and sanitization
- **User Isolation**: Project and data access control
- **Error Handling**: Graceful error responses without information leakage

### Scalability Features
- **MongoDB Integration**: Scalable document storage with vector indexing
- **API Key Rotation**: Automatic failover and load balancing
- **Docker Optimization**: Efficient containerization for cloud deployment
- **Resource Management**: Intelligent memory consolidation and pruning

## 🎯 Key Technical Achievements

### 1. **Advanced Memory Architecture**
- Implemented a sophisticated dual-memory system with semantic search capabilities
- Created intelligent memory planning with intent detection and strategy selection
- Developed context switching detection and memory consolidation algorithms

### 2. **Multi-Model AI Orchestration**
- Built a four-tier model selection system optimizing for both performance and cost
- Implemented dynamic task assignment based on complexity and reasoning requirements
- Created flexible summarization with automatic model selection based on context length

### 3. **Enhanced RAG Implementation**
- Developed multi-strategy vector search with fallback mechanisms
- Implemented AI-powered query variations and file relevance classification
- Created semantic chunking with academic-aware patterns and overlap preservation

### 4. **Intelligent Chat System**
- Built context-aware conversations with smart context retrieval
- Implemented real-time status updates and session management
- Created enhancement detection and Q&A prioritization systems

### 5. **Professional Report Generation**
- Developed Chain of Thought planning with AI-powered structure generation
- Implemented multi-level analysis with comprehensive subtask execution
- Created professional PDF export with advanced formatting capabilities

## 🚀 Innovation & Impact

### Technical Innovation
- **Memory Planning System**: First-of-its-kind intent-based memory retrieval strategy
- **Multi-Model Orchestration**: Intelligent model selection based on task complexity
- **Context Switching Detection**: Automatic topic change detection and handling
- **Semantic Chunking**: Academic-aware document segmentation with overlap preservation

### User Experience
- **Real-time Feedback**: Live progress tracking for all operations
- **Intelligent Context**: Automatic context selection based on user intent
- **Professional Output**: High-quality reports with proper citations and formatting
- **Seamless Integration**: Web search augmentation and multi-format document support

### Scalability & Performance
- **Cloud-Native Design**: Optimized for Hugging Face Spaces deployment
- **Efficient Resource Usage**: Lazy loading and intelligent caching strategies
- **Robust Error Handling**: Comprehensive fallback mechanisms
- **Cost Optimization**: Smart model selection reducing API costs

## 🔧 Technology Stack

### Backend Technologies
- **FastAPI**: High-performance async web framework
- **MongoDB**: Document database with Atlas Vector Search
- **PyMuPDF**: Advanced PDF processing with image extraction
- **Sentence Transformers**: All-MiniLM-L6-v2 for embeddings
- **BLIP**: Image captioning for document images

### AI & ML Integration
- **NVIDIA API**: Multi-model access (Llama, Qwen, GPT-OSS)
- **Google Gemini**: Advanced reasoning and complex analysis
- **Hugging Face**: Model hosting and inference
- **Custom Memory System**: Advanced context management

### Frontend & UI
- **Vanilla JavaScript**: Modern ES6+ with async/await patterns
- **CSS3**: Advanced styling with CSS variables and animations
- **Marked.js**: Client-side Markdown rendering
- **Responsive Design**: Mobile-first approach with progressive enhancement

### DevOps & Deployment
- **Docker**: Containerization with multi-stage builds
- **Hugging Face Spaces**: Cloud deployment platform
- **Environment Configuration**: Comprehensive config management
- **Health Monitoring**: System status and database connectivity checks

## 📊 System Capabilities

### Document Processing
- **Multi-format Support**: PDF, DOCX with image extraction
- **Semantic Chunking**: Intelligent document segmentation
- **Vector Embeddings**: 384-dimensional semantic representations
- **Automatic Summarization**: AI-powered document summaries

### Conversational AI
- **Context-Aware Chat**: Intelligent conversation management
- **Memory Integration**: Persistent conversation history
- **Enhancement Detection**: Specialized request handling
- **Real-time Updates**: Live progress tracking

### Report Generation
- **Chain of Thought Planning**: AI-powered report structure
- **Multi-level Analysis**: Comprehensive content processing
- **Professional Formatting**: PDF export with citations
- **Quality Assurance**: Content validation and scoring

### Search & Retrieval
- **Multi-strategy Search**: Flat, hybrid, Atlas, and local search
- **Query Variations**: AI-generated search expansions
- **Relevance Classification**: Intelligent content scoring
- **Fallback Mechanisms**: Robust error handling

## 🎉 Conclusion

EdSummariser represents a significant advancement in RAG system architecture, combining sophisticated memory management, intelligent AI orchestration, and professional document analysis capabilities. The system demonstrates how advanced AI techniques can be integrated into practical applications that provide real value to users while maintaining high performance and reliability.

The project showcases expertise in:
- **Advanced AI Architecture**: Multi-model orchestration and intelligent task assignment
- **Memory Systems**: Sophisticated context management and conversation continuity
- **RAG Implementation**: Enhanced retrieval with multiple strategies and fallbacks
- **Full-Stack Development**: Modern web technologies with responsive design
- **Cloud Deployment**: Optimized containerization and scalable architecture

This system serves as a comprehensive example of how to build production-ready AI applications that balance complexity with usability, performance with cost-effectiveness, and innovation with reliability.

---

*Built with ❤️ using FastAPI, MongoDB, and advanced AI orchestration techniques.*
