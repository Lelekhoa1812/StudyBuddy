# Memory System for EdSummariser

This directory contains a clean, modular memory and history management system for the EdSummariser application, designed to provide superior chat continuity and context awareness while maintaining simplicity and efficiency.

## 🚀 Features

### Core Memory Types
- **Conversation Memory**: Stores and retrieves chat history with intelligent summarization
- **Enhanced Memory**: MongoDB-based persistent storage with semantic search (when available)
- **Legacy Memory**: In-memory LRU system for backward compatibility

### Key Capabilities
- **Backward Compatibility**: All existing code works unchanged
- **Enhanced Features**: MongoDB persistence and semantic search when available
- **Graceful Fallback**: Falls back to legacy system if MongoDB unavailable
- **Zero Breaking Changes**: No modifications required to existing code
- **Modular Design**: Clean separation of concerns across files

## 📁 Architecture

```
memo/
├── README.md                    # This documentation
├── core.py                      # Main memory system Legacy memory
├── legacy.py                    # Legacy in-memory LRU system
├── persistent.py                # MongoDB-based persistent storage
├── nvidia.py                    # NVIDIA API integration
├── context.py                   # Context retrieval and management
└── history.py                   # History management functions
```

## 🚀 Core Features

- **Dual Memory System**: Legacy LRU + MongoDB persistent storage
- **Smart Context Selection**: NVIDIA AI + semantic similarity
- **Graceful Fallback**: Works with or without MongoDB
- **Zero Breaking Changes**: Backward compatible with existing code

## 🔧 Quick Start

```python
from memo.core import get_memory_system
from memo.history import get_history_manager

# Initialize
memory = get_memory_system()
history_manager = get_history_manager(memory)

# Basic operations
memory.add("user123", "q: What is AI?\na: AI is artificial intelligence")
recent = memory.recent("user123", 3)

# Enhanced features (when MongoDB available)
if memory.is_enhanced_available():
    await memory.add_conversation_memory(
        user_id="user123",
        question="How to implement auth?",
        answer="Use JWT tokens...",
        project_id="my_project"
    )
```

## 🧠 Memory Types

| Type | Description | Storage |
|------|-------------|---------|
| `conversation` | Chat history & Q&A pairs | Both |
| `user_preference` | User preferences | Enhanced only |
| `project_context` | Project-specific knowledge | Enhanced only |
| `knowledge_fact` | Domain facts | Enhanced only |

## 🔧 Configuration

```bash
MONGO_URI=mongodb://localhost:27017
MONGO_DB=studybuddy
NVIDIA_SMALL=meta/llama-3.1-8b-instruct
```

## 🛠️ Maintenance

### Key Functions
- `get_memory_system()` - Main entry point
- `memory.add()` - Add memory (legacy compatible)
- `memory.get_conversation_context()` - Get context
- `memory.search_memories()` - Semantic search
- `history_manager.files_relevance()` - File relevance detection

### Error Handling
- Multiple fallback mechanisms
- Graceful degradation when services unavailable
- Comprehensive logging for debugging

## 🔬 R&D Notes

### Context Selection Algorithm
1. **Recent Context**: NVIDIA AI selection from recent memories
2. **Semantic Context**: Cosine similarity search across all memories
3. **Fallback**: Direct memory retrieval if AI/semantic fails

### Performance Optimizations
- Shared cosine similarity function
- Efficient MongoDB indexing
- Lazy loading of embeddings
- Memory consolidation and pruning

### Extension Points
- Add new memory types in `persistent.py`
- Enhance context selection in `context.py`
- Add new AI integrations in `nvidia.py`
- Extend memory operations in `core.py`