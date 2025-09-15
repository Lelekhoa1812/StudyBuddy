# EdSummariser Utils

Core utilities for the EdSummariser RAG system providing document processing, retrieval, and AI integration.

## Core Modules

### `rag.py` - Enhanced Retrieval System
- **Multi-strategy search**: Flat, hybrid, Atlas, and local vector search
- **Flat index**: Exhaustive search for maximum accuracy
- **MongoDB integration**: Chunk storage and retrieval with vector embeddings
- **Search types**: `flat`, `hybrid`, `atlas`, `local`

### `chunker.py` - Document Segmentation
- **Semantic chunking**: Heading-based text segmentation
- **Overlap strategy**: 50-word overlap between chunks for context preservation
- **Academic patterns**: Enhanced regex for academic document structures
- **Size control**: 150-500 word chunks with intelligent splitting

### `embeddings.py` - Vector Generation
- **Sentence Transformers**: all-MiniLM-L6-v2 model (384 dimensions)
- **Lazy loading**: Model loaded on first use
- **Fallback support**: Random embeddings when model unavailable

### `router.py` - AI Model Routing
- **Multi-provider**: Gemini and NVIDIA API integration
- **Model selection**: Automatic routing based on query complexity
- **Retry logic**: Robust error handling with key rotation

### `parser.py` - Document Processing
- **PDF parsing**: PyMuPDF with image extraction
- **DOCX support**: Microsoft Word document processing
- **Image handling**: PIL integration for document images

## AI Integration

### `summarizer.py` - Content Summarization
- **Cheap summarization**: Lightweight text summarization
- **Content cleaning**: LLM-based chunk text cleaning
- **Topic extraction**: Single-sentence topic generation

### `caption.py` - Image Analysis
- **BLIP integration**: Image captioning for document images
- **Visual context**: Image-to-text conversion for RAG

## Memory & Context

### `memo/` - Memory Management
- **Conversation history**: LRU-based memory system
- **Context retrieval**: Semantic and recent context selection
- **NVIDIA integration**: File relevance classification

## Key Features

### Enhanced RAG Capabilities
- **Chain of Thought**: Query variation generation for better retrieval
- **Multi-query search**: 3-5 query variations per search
- **Smart deduplication**: Result ranking and deduplication
- **Fallback strategies**: 4-tier fallback system for zero results

### Document Processing
- **Academic-aware chunking**: Specialized patterns for academic documents
- **Context preservation**: Overlapping chunks maintain document flow
- **Metadata extraction**: Page spans, topics, and summaries

### Performance Optimizations
- **Lazy loading**: Models loaded only when needed
- **Caching**: API key rotation and retry mechanisms
- **Sampling**: Intelligent document sampling for large datasets

## R&D Areas

### Short-term Improvements
- **Query expansion**: More sophisticated query reformulation
- **Reranking**: Cross-encoder models for result reranking
- **Metadata filtering**: Enhanced metadata-based search

### Long-term Enhancements
- **TreeRAG**: Hierarchical document organization
- **Hybrid retrieval**: Sparse + dense retrieval combination
- **Fine-tuning**: Domain-specific embedding models
- **Evaluation framework**: Retrieval accuracy metrics

## Maintenance

### Dependencies
- **Core**: `sentence-transformers`, `pymongo`, `numpy`
- **PDF**: `PyMuPDF`, `PIL`
- **AI**: `httpx` for API calls
- **Optional**: `weasyprint` for PDF generation

### Configuration
- **Environment variables**: API keys, model names, search preferences
- **MongoDB**: Vector index configuration for Atlas
- **Model settings**: Embedding dimensions, chunk sizes

### Monitoring
- **Logging**: Comprehensive logging across all modules
- **Error handling**: Graceful degradation and fallbacks
- **Performance**: Search strategy selection based on results

## Usage

```python
# Basic RAG usage
from utils.rag import RAGStore
from utils.embeddings import EmbeddingClient

rag = RAGStore(mongo_uri, db_name)
embedder = EmbeddingClient()

# Enhanced search
hits = rag.vector_search(
    user_id, project_id, query_vector, 
    k=6, search_type="flat"
)
```

## File Structure
```
utils/
├── rag.py          # Core retrieval system
├── chunker.py      # Document segmentation
├── embeddings.py   # Vector generation
├── router.py       # AI model routing
├── parser.py       # Document parsing
├── summarizer.py   # Content summarization
├── caption.py      # Image analysis
├── common.py       # Shared utilities
├── logger.py       # Logging configuration
└── memo/           # Memory management
    ├── core.py     # Memory system core
    ├── history.py  # Conversation history
    └── nvidia.py   # NVIDIA integration
```
