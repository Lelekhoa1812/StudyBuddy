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

## 📁 File Structure

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

## 🔧 Installation & Setup

### Prerequisites
- MongoDB instance (local or cloud)
- Python 3.8+
- Required dependencies (see requirements.txt)

### Environment Variables
```bash
MONGO_URI=mongodb://localhost:27017
MONGO_DB=enhanced_memory
EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2
NVIDIA_SMALL=meta/llama-3.1-8b-instruct
```

### Quick Start
```python
from memo.core import get_memory_system

# Initialize the memory system
memory = get_memory_system()

# Check if enhanced features are available
if memory.is_enhanced_available():
    print("Enhanced memory system is ready!")
else:
    print("Using legacy memory system")
```

## 📖 Usage Examples

### Basic Memory Operations

```python
from memo.core import get_memory_system
from memo.history import get_history_manager

memory = get_memory_system()
history_manager = get_history_manager(memory)

# Add conversation memory (legacy compatibility)
memory.add("user123", "q: What is AI?\na: AI is artificial intelligence")

# Add enhanced conversation memory (when MongoDB available)
memory_id = await memory.add_conversation_memory(
    user_id="user123",
    question="How do I implement authentication?",
    answer="You can use JWT tokens with FastAPI...",
    project_id="my_project",
    context={"topic": "authentication", "difficulty": "intermediate"}
)

# Get recent memories
recent_memories = memory.recent("user123", n=5)

# Search memories semantically
search_results = await memory.search_memories(
    user_id="user123",
    query="authentication best practices",
    limit=10
)
```

### Advanced Features

```python
# Add user preferences
await memory_manager.add_user_preference(
    user_id="user123",
    preference="Prefers detailed explanations with code examples",
    context={"communication_style": "detailed"}
)

# Add project context
await memory_manager.add_project_context(
    user_id="user123",
    project_id="my_project",
    context="FastAPI application with JWT auth and PostgreSQL",
    importance=MemoryImportance.HIGH
)

# Get comprehensive conversation context
recent_context, semantic_context = await memory_manager.get_conversation_context(
    user_id="user123",
    question="How do I handle database migrations?",
    project_id="my_project"
)
```

### Conversation Management

```python
from memo.enhanced_history import ConversationManager

# Initialize conversation manager
conversation_manager = ConversationManager(
    memory_system=memory_manager.enhanced_memory,
    nvidia_rotator=nvidia_rotator,
    embedder=embedder
)

# Process conversation turn with enhanced context
memory_id = await conversation_manager.process_conversation_turn(
    user_id="user123",
    question="What's the best way to structure my code?",
    answer="Follow the single responsibility principle...",
    project_id="my_project",
    context={"files": ["main.py", "auth.py"]}
)

# Get conversation summary
summary = await conversation_manager.create_conversation_summary(
    user_id="user123",
    project_id="my_project"
)
```

## 🔄 Migration from Legacy System

The enhanced memory system is designed to be backward compatible. Here's how to migrate:

### Step 1: Update Imports
```python
# OLD
from memo.memory import MemoryLRU

# NEW
from memo.memory_integration import MemoryIntegrationManager
```

### Step 2: Initialize Memory Manager
```python
# OLD
memory = MemoryLRU()

# NEW
memory_manager = MemoryIntegrationManager(mongo_uri, db_name)
```

### Step 3: Update Memory Operations
```python
# OLD
memory.add(user_id, qa_summary)
recent = memory.recent(user_id, 3)
rest = memory.rest(user_id, 3)

# NEW
await memory_manager.add_conversation_memory(user_id, question, answer, project_id)
recent_context, semantic_context = await memory_manager.get_conversation_context(
    user_id, question, project_id
)
```

## 🏗️ Architecture

### Memory Layers
1. **Short-term Memory**: Recent conversation context (last 10-20 exchanges)
2. **Long-term Memory**: Persistent storage with semantic indexing
3. **User Memory**: Preferences, goals, and personality traits
4. **Project Memory**: Project-specific context and knowledge
5. **Session Memory**: Active conversation state and threading

### Data Flow
```
User Question → Context Composition → Memory Retrieval → LLM Processing → Memory Storage
     ↓                ↓                    ↓                ↓              ↓
Recent Context → Semantic Search → Enhanced Context → Response → Memory Update
```

## 🔍 Memory Types

| Type | Description | Use Case |
|------|-------------|----------|
| `CONVERSATION` | Chat history and Q&A pairs | Context continuity |
| `USER_PREFERENCE` | User communication style and preferences | Personalization |
| `PROJECT_CONTEXT` | Project-specific knowledge | Domain awareness |
| `SESSION_STATE` | Active conversation state | Session management |
| `KNOWLEDGE_FACT` | Domain-specific facts | Knowledge base |
| `GOAL_OBJECTIVE` | User goals and objectives | Goal tracking |

## 📊 Memory Importance Levels

| Level | Description | Retention |
|-------|-------------|-----------|
| `CRITICAL` | Essential user preferences, project goals | Permanent |
| `HIGH` | Important context, user patterns | Long-term |
| `MEDIUM` | Regular conversations, project details | Medium-term |
| `LOW` | Casual interactions, temporary context | Short-term |

## 🛠️ Configuration

### Memory Limits
```python
# Configure memory limits
memory_manager.enhanced_memory.consolidate_memories(
    user_id="user123",
    max_memories=1000  # Maximum memories per user
)

# Cleanup old memories
memory_manager.enhanced_memory.cleanup_old_memories(
    user_id="user123",
    days_old=90  # Remove memories older than 90 days
)
```

### Embedding Configuration
```python
# Use different embedding models
embedder = EmbeddingClient(model_name="sentence-transformers/all-mpnet-base-v2")

# Initialize with custom embedder
memory_manager = MemoryIntegrationManager(
    mongo_uri=mongo_uri,
    db_name=db_name
)
memory_manager.enhanced_memory.embedder = embedder
```

## 🔒 Privacy & Security

### Data Protection
- All memories are user-scoped and isolated
- No cross-user data leakage
- Configurable data retention policies
- Memory export/import capabilities

### Access Control
```python
# Clear user data
memory_manager.clear_user_memories("user123")

# Get memory statistics
stats = memory_manager.get_memory_stats("user123")
```

## 📈 Performance Optimization

### Memory Consolidation
- Automatic memory importance scoring
- Intelligent memory pruning
- Embedding-based deduplication
- Efficient MongoDB indexing

### Query Optimization
- Semantic search with similarity thresholds
- Context length management
- Lazy loading of memory components
- Caching for frequent queries

## 🧪 Testing

Run the example integration to test the system:

```bash
python memo/example_integration.py
```

This will demonstrate:
- Basic memory operations
- Advanced features
- Integration patterns
- Error handling

## 🤝 Contributing

When adding new features to the memory system:

1. Maintain backward compatibility
2. Add comprehensive logging
3. Include error handling
4. Update documentation
5. Add tests for new functionality

## 📚 References

This enhanced memory system is inspired by:
- **Cursor AI**: Multi-file context awareness and conversation threading
- **ChatGPT**: Memory functionality and conversation continuity
- **Claude**: Advanced context management and reasoning
- **Research Papers**: MemoryBank, Mem0, and other memory architectures

## 🐛 Troubleshooting

### Common Issues

1. **MongoDB Connection Failed**
   - Check MONGO_URI environment variable
   - Ensure MongoDB is running
   - Verify network connectivity

2. **Enhanced Memory Not Available**
   - Check MongoDB connection
   - Verify required dependencies
   - Check logs for initialization errors

3. **Memory Retrieval Issues**
   - Check embedding model availability
   - Verify memory consolidation settings
   - Check similarity thresholds

### Debug Mode
```python
import logging
logging.getLogger("ENHANCED_MEMORY").setLevel(logging.DEBUG)
logging.getLogger("MEMORY_INTEGRATION").setLevel(logging.DEBUG)
```

## 📄 License

This enhanced memory system is part of the EdSummariser project and follows the same license terms.
