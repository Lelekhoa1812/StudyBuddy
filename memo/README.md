# Memory System for EdSummariser

A sophisticated memory management system that provides intelligent context retrieval, conversation continuity, and enhancement-focused memory planning for the EdSummariser application.

## 🧠 Key Features

### **Memory Planning System**
- **Intent Detection**: Automatically detects user intent (enhancement, clarification, comparison, etc.)
- **Strategy Planning**: Selects optimal memory retrieval strategy based on user intent
- **Enhancement Focus**: Specialized handling for "Enhance...", "Be more detailed" requests
- **Q&A Prioritization**: Focuses on past Q&A data for enhancement requests

### **Dual Memory Architecture**
- **Enhanced Memory**: MongoDB-based persistent storage with semantic search
- **Legacy Memory**: In-memory LRU system for backward compatibility
- **Graceful Fallback**: Automatically falls back when MongoDB unavailable

### **Smart Context Retrieval**
- **Semantic Search**: Cosine similarity-based memory selection
- **AI-Powered Selection**: NVIDIA model integration for intelligent memory filtering
- **Session Management**: Tracks conversation continuity and context switches
- **Memory Consolidation**: Prevents information overload through intelligent pruning

## 📁 Architecture

```
memo/
├── README.md                    # This documentation
├── core.py                      # Main memory system with planning integration
├── planning.py                  # Memory planning and strategy system
├── persistent.py                # MongoDB-based persistent storage
├── legacy.py                    # In-memory LRU system
├── retrieval.py                 # Context retrieval manager
├── conversation.py              # Conversation management orchestrator
├── sessions.py                  # Session tracking and context switching
├── consolidation.py             # Memory consolidation and pruning
├── context.py                   # Context management utilities
├── history.py                   # History management functions
├── nvidia.py                    # NVIDIA API integration
└── plan/                        # Modular planning components
    ├── intent.py                # Intent detection
    ├── strategy.py              # Strategy planning
    └── execution.py             # Execution engine
```

## 🚀 Core Capabilities

### **Enhancement Request Handling**
```python
# Automatically detects and handles enhancement requests
question = "Enhance the previous answer about machine learning"
# System uses FOCUSED_QA strategy with Q&A prioritization
```

### **Intent-Based Memory Planning**
- **ENHANCEMENT**: Uses FOCUSED_QA strategy for detailed responses
- **CLARIFICATION**: Uses RECENT_FOCUS strategy for context
- **COMPARISON**: Uses BROAD_CONTEXT strategy for comprehensive data
- **REFERENCE**: Uses FOCUSED_QA strategy for specific past content
- **NEW_TOPIC**: Uses SEMANTIC_DEEP strategy for discovery

### **Memory Types**
| Type | Description | Storage | Usage |
|------|-------------|---------|-------|
| `conversation` | Chat history & Q&A pairs | Both | Primary context source |
| `user_preference` | User preferences | Enhanced only | Personalization |
| `project_context` | Project-specific knowledge | Enhanced only | Project continuity |
| `knowledge_fact` | Domain facts | Enhanced only | Knowledge base |

## 🔧 Quick Start

```python
from memo.core import get_memory_system
from memo.planning import get_memory_planner

# Initialize memory system
memory = get_memory_system()
planner = get_memory_planner(memory, embedder)

# Basic operations (backward compatible)
memory.add("user123", "q: What is AI?\na: AI is artificial intelligence")
recent = memory.recent("user123", 3)

# Smart context with planning
recent_context, semantic_context, metadata = await memory.get_smart_context(
    user_id="user123",
    question="Enhance the previous answer about deep learning",
    nvidia_rotator=rotator
)

# Enhancement-specific context
enhancement_context = await memory.get_enhancement_context(
    user_id="user123",
    question="Be more detailed about neural networks",
    nvidia_rotator=rotator
)
```

## 🎯 Memory Planning Strategies

### **FOCUSED_QA** (Enhancement Requests)
- Prioritizes past Q&A pairs
- Uses very low similarity threshold (0.05) for maximum recall
- AI-powered selection of most relevant Q&A memories
- Optimized for detailed, comprehensive responses

### **RECENT_FOCUS** (Clarification Requests)
- Focuses on recent conversation context
- Balances recent and semantic context
- Ideal for follow-up questions

### **BROAD_CONTEXT** (Comparison Requests)
- Retrieves wide range of memories
- Higher similarity threshold for relevance
- Suitable for comparative analysis

### **SEMANTIC_DEEP** (New Topics)
- Deep semantic search across all memories
- AI-powered selection for discovery
- Comprehensive knowledge retrieval

### **MIXED_APPROACH** (Continuation)
- Combines recent and semantic context
- Balanced approach for ongoing conversations
- Adaptive based on conversation state

## 🔧 Configuration

```bash
# MongoDB Configuration
MONGO_URI=mongodb://localhost:27017
MONGO_DB=studybuddy

# NVIDIA API Configuration
NVIDIA_SMALL=meta/llama-3.1-8b-instruct
```

## 🛠️ Key Functions

### **Core Memory System**
- `get_memory_system()` - Main entry point
- `memory.get_smart_context()` - Intelligent context with planning
- `memory.get_enhancement_context()` - Enhancement-specific context
- `memory.add_conversation_memory()` - Add structured memories
- `memory.search_memories()` - Semantic search

### **Memory Planning**
- `planner.plan_memory_strategy()` - Plan retrieval strategy
- `planner.execute_memory_plan()` - Execute planned strategy
- `planner._detect_user_intent()` - Detect user intent

### **Session Management**
- `session_manager.get_or_create_session()` - Session tracking
- `session_manager.detect_context_switch()` - Context switching
- `session_manager.get_conversation_insights()` - Conversation analytics

## 🧪 Enhancement Request Examples

The system automatically handles various enhancement patterns:

```python
# These all trigger FOCUSED_QA strategy:
"Enhance the previous answer about machine learning"
"Be more detailed about neural networks"
"Elaborate on the explanation of deep learning"
"Tell me more about what we discussed"
"Go deeper into the topic"
"Provide more context about..."
```

## 🔬 Technical Details

### **Intent Detection**
- Pattern-based detection using regex
- AI-powered detection using NVIDIA models
- Fallback to continuation for ambiguous cases

### **Memory Selection**
- Cosine similarity for semantic matching
- AI-powered selection for optimal relevance
- Configurable similarity thresholds per strategy

### **Performance Optimizations**
- Efficient MongoDB indexing
- Lazy loading of embeddings
- Memory consolidation and pruning
- Cached context for session continuity

### **Error Handling**
- Multiple fallback mechanisms
- Graceful degradation when services unavailable
- Comprehensive logging for debugging
- Backward compatibility maintained

## 🚀 Advanced Usage

### **Custom Memory Planning**
```python
# Create custom execution plan
execution_plan = {
    "intent": QueryIntent.ENHANCEMENT,
    "strategy": MemoryStrategy.FOCUSED_QA,
    "retrieval_params": {
        "recent_limit": 5,
        "semantic_limit": 10,
        "qa_focus": True,
        "enhancement_mode": True,
        "similarity_threshold": 0.05
    }
}

# Execute custom plan
recent, semantic, metadata = await planner.execute_memory_plan(
    user_id, question, execution_plan, nvidia_rotator
)
```

### **Memory Consolidation**
```python
# Consolidate and prune memories
consolidation_result = await memory.consolidate_memories(
    user_id="user123", 
    nvidia_rotator=rotator
)
```

## 🔄 Integration Points

The memory system integrates seamlessly with:
- **Chat Routes**: Automatic context retrieval
- **Report Generation**: Enhanced instruction processing
- **File Processing**: Relevance detection
- **User Sessions**: Continuity tracking
- **API Rotators**: AI-powered enhancements

## 📊 Monitoring

The system provides comprehensive metadata:
- Intent detection results
- Strategy selection rationale
- Memory retrieval statistics
- Enhancement focus indicators
- Session continuity tracking
- Performance metrics

This memory system ensures that enhancement requests like "Enhance..." or "Be more detailed" are handled with maximum effectiveness by focusing on past Q&A data and using intelligent memory planning strategies.