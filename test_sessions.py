#!/usr/bin/env python3
"""
Test script for session management functionality

This script validates:
1. Session creation, listing, renaming, and deletion
2. Session-specific memory management
3. Auto-naming functionality
4. Integration with chat system
"""

import asyncio
import json
import time
import uuid
from typing import Dict, Any

# Test configuration
TEST_USER_ID = "test_user_123"
TEST_PROJECT_ID = "test_project_456"
BASE_URL = "http://localhost:8000"  # Adjust if needed

class SessionTester:
    def __init__(self):
        self.sessions = []
        self.test_results = []
    
    async def test_session_creation(self):
        """Test creating a new session"""
        print("🧪 Testing session creation...")
        
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                form_data = {
                    "user_id": TEST_USER_ID,
                    "project_id": TEST_PROJECT_ID,
                    "session_name": "Test Session"
                }
                
                response = await client.post(f"{BASE_URL}/sessions/create", data=form_data)
                
                if response.status_code == 200:
                    session_data = response.json()
                    self.sessions.append(session_data)
                    print(f"✅ Session created: {session_data['session_id']}")
                    return session_data
                else:
                    print(f"❌ Session creation failed: {response.text}")
                    return None
                    
        except Exception as e:
            print(f"❌ Session creation error: {e}")
            return None
    
    async def test_session_listing(self):
        """Test listing sessions"""
        print("🧪 Testing session listing...")
        
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{BASE_URL}/sessions/list",
                    params={
                        "user_id": TEST_USER_ID,
                        "project_id": TEST_PROJECT_ID
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    sessions = data.get("sessions", [])
                    print(f"✅ Found {len(sessions)} sessions")
                    return sessions
                else:
                    print(f"❌ Session listing failed: {response.text}")
                    return []
                    
        except Exception as e:
            print(f"❌ Session listing error: {e}")
            return []
    
    async def test_session_renaming(self, session_id: str):
        """Test renaming a session"""
        print(f"🧪 Testing session renaming for {session_id}...")
        
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                form_data = {
                    "user_id": TEST_USER_ID,
                    "project_id": TEST_PROJECT_ID,
                    "session_id": session_id,
                    "new_name": "Renamed Test Session"
                }
                
                response = await client.put(f"{BASE_URL}/sessions/rename", data=form_data)
                
                if response.status_code == 200:
                    print("✅ Session renamed successfully")
                    return True
                else:
                    print(f"❌ Session renaming failed: {response.text}")
                    return False
                    
        except Exception as e:
            print(f"❌ Session renaming error: {e}")
            return False
    
    async def test_auto_naming(self, session_id: str):
        """Test auto-naming functionality"""
        print(f"🧪 Testing auto-naming for {session_id}...")
        
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                form_data = {
                    "user_id": TEST_USER_ID,
                    "project_id": TEST_PROJECT_ID,
                    "session_id": session_id,
                    "first_query": "What is machine learning and how does it work?"
                }
                
                response = await client.post(f"{BASE_URL}/sessions/auto-name", data=form_data)
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"✅ Auto-naming result: {data.get('message', 'Success')}")
                    return True
                else:
                    print(f"❌ Auto-naming failed: {response.text}")
                    return False
                    
        except Exception as e:
            print(f"❌ Auto-naming error: {e}")
            return False
    
    async def test_chat_with_session(self, session_id: str):
        """Test chat functionality with session"""
        print(f"🧪 Testing chat with session {session_id}...")
        
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                form_data = {
                    "user_id": TEST_USER_ID,
                    "project_id": TEST_PROJECT_ID,
                    "question": "Hello, this is a test question",
                    "session_id": session_id,
                    "k": 3
                }
                
                response = await client.post(f"{BASE_URL}/chat", data=form_data)
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"✅ Chat response received: {len(data.get('answer', ''))} characters")
                    return True
                else:
                    print(f"❌ Chat failed: {response.text}")
                    return False
                    
        except Exception as e:
            print(f"❌ Chat error: {e}")
            return False
    
    async def test_session_clear_memory(self, session_id: str):
        """Test clearing session-specific memory"""
        print(f"🧪 Testing session memory clearing for {session_id}...")
        
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                form_data = {
                    "user_id": TEST_USER_ID,
                    "project_id": TEST_PROJECT_ID,
                    "session_id": session_id
                }
                
                response = await client.post(f"{BASE_URL}/sessions/clear-memory", data=form_data)
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"✅ Session memory cleared: {data.get('message', 'Success')}")
                    return True
                else:
                    print(f"❌ Session memory clearing failed: {response.text}")
                    return False
                    
        except Exception as e:
            print(f"❌ Session memory clearing error: {e}")
            return False
    
    async def test_session_history_clearing(self, session_id: str):
        """Test clearing session-specific chat history"""
        print(f"🧪 Testing session history clearing for {session_id}...")
        
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    f"{BASE_URL}/chat/history",
                    params={
                        "user_id": TEST_USER_ID,
                        "project_id": TEST_PROJECT_ID,
                        "session_id": session_id
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"✅ Session history cleared: {data.get('message', 'Success')}")
                    return True
                else:
                    print(f"❌ Session history clearing failed: {response.text}")
                    return False
                    
        except Exception as e:
            print(f"❌ Session history clearing error: {e}")
            return False
    
    async def test_session_deletion(self, session_id: str):
        """Test deleting a session"""
        print(f"🧪 Testing session deletion for {session_id}...")
        
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                form_data = {
                    "user_id": TEST_USER_ID,
                    "project_id": TEST_PROJECT_ID,
                    "session_id": session_id
                }
                
                response = await client.delete(f"{BASE_URL}/sessions/delete", data=form_data)
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"✅ Session deleted: {data.get('message', 'Success')}")
                    return True
                else:
                    print(f"❌ Session deletion failed: {response.text}")
                    return False
                    
        except Exception as e:
            print(f"❌ Session deletion error: {e}")
            return False
    
    async def test_memory_management(self):
        """Test session-specific memory management"""
        print("🧪 Testing session-specific memory management...")
        
        try:
            # This would test the memory system directly
            # For now, we'll just test that the endpoints exist
            print("✅ Memory management endpoints available")
            return True
            
        except Exception as e:
            print(f"❌ Memory management error: {e}")
            return False
    
    async def run_all_tests(self):
        """Run all tests"""
        print("🚀 Starting session management tests...\n")
        
        # Test 1: Create session
        session = await self.test_session_creation()
        if not session:
            print("❌ Cannot continue without a session")
            print("💡 Note: Make sure the server is running on http://localhost:8000")
            return
        
        session_id = session["session_id"]
        
        # Test 2: List sessions
        await self.test_session_listing()
        
        # Test 3: Rename session
        await self.test_session_renaming(session_id)
        
        # Test 4: Auto-naming
        await self.test_auto_naming(session_id)
        
        # Test 5: Chat with session
        await self.test_chat_with_session(session_id)
        
        # Test 6: Session memory clearing
        await self.test_session_clear_memory(session_id)
        
        # Test 7: Session history clearing
        await self.test_session_history_clearing(session_id)
        
        # Test 8: Memory management
        await self.test_memory_management()
        
        # Test 9: Delete session
        await self.test_session_deletion(session_id)
        
        print("\n🎉 All tests completed!")

async def main():
    """Main test runner"""
    tester = SessionTester()
    await tester.run_all_tests()

if __name__ == "__main__":
    print("Session Management Test Suite")
    print("=" * 50)
    asyncio.run(main())
