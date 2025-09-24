# Session Management Implementation

This document describes the implementation of multiple sessions per project functionality in the EdSummariser application.

## Overview

The system now supports multiple chat sessions per project, where each session maintains its own memory context separate from other sessions. This allows users to have different conversation threads within the same project while sharing the same documents.

## Key Features

### 1. Session Management UI
- **Dropdown Menu**: Lists all sessions for the current project with the last option to create a new session
- **Create Session**: "+" button to create new sessions (default name: "New Chat")
- **Rename Session**: Pencil icon (✏️) to rename sessions
- **Delete Session**: Trash icon (🗑️) to delete sessions with confirmation modal
- **Session Actions**: Rename and delete buttons appear only when a session is selected

### 2. Auto-Naming
- Sessions are automatically named based on the first user query
- Uses NVIDIA_SMALL API to generate 2-3 word descriptive names
- Names are generated when the user sends their first message in a new session
- Example: "What is machine learning?" → "Machine Learning Basics"

### 3. Session-Specific Memory
- Each session maintains its own conversation memory
- Memory is isolated between sessions
- Session memory is stored separately from project-wide memory
- Memory includes conversation context, Q&A pairs, and relevant metadata

## Technical Implementation

### Backend Components

#### 1. Session Routes (`routes/sessions.py`)
- `GET /sessions/list` - List all sessions for a project
- `POST /sessions/create` - Create a new session
- `PUT /sessions/rename` - Rename a session
- `DELETE /sessions/delete` - Delete a session and its memory
- `POST /sessions/auto-name` - Auto-name a session based on first query

#### 2. Session Memory Manager (`memo/session.py`)
- `SessionMemoryManager` class for session-specific memory operations
- Stores memories in MongoDB with session_id as key
- Supports semantic search within session memories
- Provides memory statistics and cleanup functions

#### 3. Updated Chat System
- Chat messages now include `session_id` parameter
- Memory retrieval is session-specific
- Auto-naming triggered on first message in new session
- Session context used for conversation continuity

### Frontend Components

#### 1. Session Management (`static/sessions.js`)
- Handles session dropdown, creation, renaming, and deletion
- Manages session state and UI updates
- Integrates with chat system for session-specific messaging

#### 2. Updated Chat Interface (`static/script.js`)
- Modified to use current session ID for all chat operations
- Session validation before allowing chat
- Session-specific message saving

#### 3. UI Styling (`static/styles.css`)
- Session control styling with responsive design
- Modal styles for rename/delete operations
- Consistent with existing design system

## Database Schema

### Chat Sessions Collection
```javascript
{
  "user_id": "string",
  "project_id": "string", 
  "session_id": "string",
  "session_name": "string",
  "is_auto_named": boolean,
  "role": "user|assistant",
  "content": "string",
  "timestamp": number,
  "created_at": datetime,
  "sources": array,
  "is_report": boolean
}
```

### Session Memories Collection
```javascript
{
  "memory_id": "string",
  "user_id": "string",
  "project_id": "string",
  "session_id": "string",
  "content": "string",
  "memory_type": "conversation",
  "importance": "medium",
  "tags": array,
  "metadata": object,
  "created_at": datetime,
  "timestamp": number
}
```

## API Endpoints

### Session Management
- `GET /sessions/list?user_id={id}&project_id={id}` - List sessions
- `POST /sessions/create` - Create session
- `PUT /sessions/rename` - Rename session  
- `DELETE /sessions/delete` - Delete session
- `POST /sessions/auto-name` - Auto-name session

### Updated Chat Endpoints
- `POST /chat` - Now includes session_id parameter
- `GET /chat/history` - Now supports session_id filter
- `POST /chat/save` - Now includes session_id parameter

## Usage Flow

1. **User selects a project** → Sessions are loaded for that project
2. **User creates a new session** → Default name "New Chat" is assigned
3. **User sends first message** → Session is auto-named based on query
4. **User continues chatting** → Memory is maintained within the session
5. **User switches sessions** → Different memory context is loaded
6. **User can rename/delete sessions** → UI provides management options

## Testing

A comprehensive test suite is provided in `test_sessions.py` that validates:
- Session creation, listing, renaming, and deletion
- Auto-naming functionality
- Chat integration with sessions
- Memory management
- API endpoint functionality

## Benefits

1. **Organized Conversations**: Users can maintain separate conversation threads
2. **Context Preservation**: Each session maintains its own memory context
3. **Easy Management**: Simple UI for creating, renaming, and deleting sessions
4. **Automatic Organization**: Sessions are auto-named for easy identification
5. **Scalable**: Supports unlimited sessions per project
6. **Backward Compatible**: Existing functionality remains unchanged

## Future Enhancements

- Session sharing between users
- Session templates
- Session export/import
- Advanced session analytics
- Session-based permissions
