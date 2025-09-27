// ────────────────────────────── static/sessions.js ──────────────────────────────
(function() {
  // Session management state
  let currentSessionId = null;
  let currentProjectId = null;
  let sessions = [];
  
  // DOM elements
  const sessionDropdown = document.getElementById('session-dropdown');
  const createSessionBtn = document.getElementById('create-session-btn');
  const renameSessionBtn = document.getElementById('rename-session-btn');
  const deleteSessionBtn = document.getElementById('delete-session-btn');
  const sessionActions = document.querySelector('.session-actions');
  
  // Modals
  const renameModal = document.getElementById('rename-session-modal');
  const deleteModal = document.getElementById('delete-session-modal');
  const renameForm = document.getElementById('rename-session-form');
  const sessionNameInput = document.getElementById('session-name-input');
  
  // Initialize session management
  function init() {
    setupEventListeners();
    // Load sessions when project changes
    document.addEventListener('projectChanged', (event) => {
      console.log('[SESSIONS] Project changed event received:', event.detail);
      loadSessions();
    });
  }
  
  function setupEventListeners() {
    // Session dropdown change
    sessionDropdown.addEventListener('change', handleSessionChange);
    
    // Create session button
    createSessionBtn.addEventListener('click', createNewSession);
    
    // Rename session
    renameSessionBtn.addEventListener('click', showRenameModal);
    renameForm.addEventListener('submit', handleRenameSession);
    document.getElementById('cancel-rename-session').addEventListener('click', hideRenameModal);
    
    // Delete session
    deleteSessionBtn.addEventListener('click', showDeleteModal);
    document.getElementById('confirm-delete-session').addEventListener('click', handleDeleteSession);
    document.getElementById('cancel-delete-session').addEventListener('click', hideDeleteModal);
    
    // Close modals on outside click
    renameModal.addEventListener('click', (e) => {
      if (e.target === renameModal) hideRenameModal();
    });
    deleteModal.addEventListener('click', (e) => {
      if (e.target === deleteModal) hideDeleteModal();
    });
  }
  
  async function loadSessions() {
    const user = window.__sb_get_user();
    const currentProject = window.__sb_get_current_project && window.__sb_get_current_project();
    
    console.log('[SESSIONS] Loading sessions for user:', user?.user_id, 'project:', currentProject?.project_id);
    
    if (!user || !currentProject) {
      console.log('[SESSIONS] No user or project, clearing sessions');
      sessions = [];
      updateSessionDropdown();
      return;
    }
    
    try {
      const response = await fetch(`/sessions/list?user_id=${encodeURIComponent(user.user_id)}&project_id=${encodeURIComponent(currentProject.project_id)}`);
      if (response.ok) {
        const data = await response.json();
        sessions = data.sessions || [];
        updateSessionDropdown();
        
        // Auto-select first session if none selected
        if (sessions.length > 0 && !currentSessionId) {
          selectSession(sessions[0].session_id);
        } else if (sessions.length === 0) {
          // If no sessions exist, create a default one
          await createDefaultSession();
        }
      } else {
        console.error('Failed to load sessions');
        sessions = [];
        updateSessionDropdown();
        // Try to create a default session even if loading failed
        await createDefaultSession();
      }
    } catch (error) {
      console.error('Error loading sessions:', error);
      sessions = [];
      updateSessionDropdown();
      // Try to create a default session even if loading failed
      await createDefaultSession();
    }
  }
  
  function updateSessionDropdown() {
    console.log(`[SESSIONS] 🔄 updateSessionDropdown called with ${sessions.length} sessions`);
    console.log(`[SESSIONS] Sessions:`, sessions.map(s => ({ id: s.session_id, name: s.name, auto: s.is_auto_named })));
    
    sessionDropdown.innerHTML = '<option value="">Select Session</option>';
    
    sessions.forEach(session => {
      const option = document.createElement('option');
      option.value = session.session_id;
      option.textContent = session.name;
      if (session.is_auto_named) {
        option.textContent += ' (Auto)';
      }
      sessionDropdown.appendChild(option);
      console.log(`[SESSIONS] Added option: ${option.value} = ${option.textContent}`);
    });
    
    // Add create new session option
    const createOption = document.createElement('option');
    createOption.value = 'create_new';
    createOption.textContent = '+ Create new session';
    sessionDropdown.appendChild(createOption);
    
    // Update session actions visibility
    updateSessionActions();
    
    console.log(`[SESSIONS] ✅ Dropdown updated with ${sessionDropdown.children.length} options`);
  }
  
  function updateSessionActions() {
    const hasSelectedSession = currentSessionId && currentSessionId !== 'create_new';
    sessionActions.style.display = hasSelectedSession ? 'flex' : 'none';
  }
  
  async function handleSessionChange() {
    const selectedValue = sessionDropdown.value;
    
    if (selectedValue === 'create_new') {
      await createNewSession();
    } else if (selectedValue && selectedValue !== currentSessionId) {
      selectSession(selectedValue);
    }
  }
  
  function selectSession(sessionId) {
    currentSessionId = sessionId;
    sessionDropdown.value = sessionId;
    updateSessionActions();
    
    // Clear chat messages when switching sessions
    const messages = document.getElementById('messages');
    if (messages) {
      messages.innerHTML = '';
    }
    
    // Load chat history for this session
    loadChatHistory();
  }
  
  async function createDefaultSession() {
    const user = window.__sb_get_user();
    const currentProject = window.__sb_get_current_project && window.__sb_get_current_project();
    
    if (!user || !currentProject) {
      return;
    }
    
    try {
      const formData = new FormData();
      formData.append('user_id', user.user_id);
      formData.append('project_id', currentProject.project_id);
      formData.append('session_name', 'New Chat');
      
      const response = await fetch('/sessions/create', {
        method: 'POST',
        body: formData
      });
      
      if (response.ok) {
        const session = await response.json();
        sessions.unshift(session); // Add to beginning
        updateSessionDropdown();
        selectSession(session.session_id);
        console.log('Created default session:', session.session_id);
      } else {
        console.error('Failed to create default session');
      }
    } catch (error) {
      console.error('Failed to create default session:', error);
    }
  }

  async function createNewSession() {
    const user = window.__sb_get_user();
    const currentProject = window.__sb_get_current_project && window.__sb_get_current_project();
    
    if (!user || !currentProject) {
      alert('Please select a project first');
      return;
    }
    
    try {
      const formData = new FormData();
      formData.append('user_id', user.user_id);
      formData.append('project_id', currentProject.project_id);
      formData.append('session_name', 'New Chat');
      
      const response = await fetch('/sessions/create', {
        method: 'POST',
        body: formData
      });
      
      if (response.ok) {
        const session = await response.json();
        sessions.unshift(session); // Add to beginning
        updateSessionDropdown();
        selectSession(session.session_id);
      } else {
        alert('Failed to create session');
      }
    } catch (error) {
      console.error('Error creating session:', error);
      alert('Failed to create session');
    }
  }
  
  function showRenameModal() {
    if (!currentSessionId) return;
    
    const session = sessions.find(s => s.session_id === currentSessionId);
    if (session) {
      sessionNameInput.value = session.name;
      renameModal.classList.remove('hidden');
      sessionNameInput.focus();
    }
  }
  
  function hideRenameModal() {
    renameModal.classList.add('hidden');
    sessionNameInput.value = '';
  }
  
  async function handleRenameSession(e) {
    e.preventDefault();
    
    if (!currentSessionId) return;
    
    const newName = sessionNameInput.value.trim();
    if (!newName) return;
    
    try {
      const formData = new FormData();
      formData.append('user_id', window.__sb_get_user().user_id);
      formData.append('project_id', window.__sb_get_current_project().project_id);
      formData.append('session_id', currentSessionId);
      formData.append('new_name', newName);
      
      // Use POST for broader proxy compatibility; backend has alias
      const response = await fetch('/sessions/rename', {
        method: 'POST',
        body: formData
      });
      
      if (response.ok) {
        // Update local session data
        const session = sessions.find(s => s.session_id === currentSessionId);
        if (session) {
          session.name = newName;
          session.is_auto_named = false;
        }
        updateSessionDropdown();
        hideRenameModal();
      } else {
        alert('Failed to rename session');
      }
    } catch (error) {
      console.error('Error renaming session:', error);
      alert('Failed to rename session');
    }
  }
  
  function showDeleteModal() {
    if (!currentSessionId) return;
    deleteModal.classList.remove('hidden');
  }
  
  function hideDeleteModal() {
    deleteModal.classList.add('hidden');
  }
  
  async function handleDeleteSession() {
    if (!currentSessionId) return;
    
    try {
      const formData = new FormData();
      formData.append('user_id', window.__sb_get_user().user_id);
      formData.append('project_id', window.__sb_get_current_project().project_id);
      formData.append('session_id', currentSessionId);
      
      const response = await fetch('/sessions/delete', {
        method: 'DELETE',
        body: formData
      });
      
      if (response.ok) {
        // Remove from local sessions
        sessions = sessions.filter(s => s.session_id !== currentSessionId);
        currentSessionId = null;
        updateSessionDropdown();
        hideDeleteModal();
        
        // Clear chat messages
        const messages = document.getElementById('messages');
        if (messages) {
          messages.innerHTML = '';
        }
        
        // Select first available session or create new one
        if (sessions.length > 0) {
          selectSession(sessions[0].session_id);
        } else {
          await createNewSession();
        }
      } else {
        alert('Failed to delete session');
      }
    } catch (error) {
      console.error('Error deleting session:', error);
      alert('Failed to delete session');
    }
  }
  
  async function loadChatHistory() {
    if (!currentSessionId) return;
    
    const user = window.__sb_get_user();
    const currentProject = window.__sb_get_current_project && window.__sb_get_current_project();
    
    if (!user || !currentProject) return;
    
    try {
      const response = await fetch(`/chat/history?user_id=${encodeURIComponent(user.user_id)}&project_id=${encodeURIComponent(currentProject.project_id)}&session_id=${encodeURIComponent(currentSessionId)}`);
      if (response.ok) {
        const data = await response.json();
        const msgContainer = document.getElementById('messages');
        if (msgContainer && data.messages) {
          msgContainer.innerHTML = '';
          // Use unified renderer from script.js to ensure consistent UX
          data.messages.forEach(message => {
            const isReport = !!message.is_report;
            // Render the message
            if (window.appendMessage) {
              window.appendMessage(message.role, message.content, isReport);
            }
            // Render sources separately to avoid mixing with content
            if (message.sources && message.sources.length && window.appendSources) {
              window.appendSources(message.sources);
            }
          });
        }
      }
    } catch (error) {
      console.error('Error loading chat history:', error);
    }
  }
  
  // Remove local appendMessage in favor of the unified version from script.js
  
  // Function to update session name in UI immediately
  function updateSessionName(sessionId, newName) {
    console.log(`[SESSIONS] 🔄 updateSessionName called: sessionId=${sessionId}, newName='${newName}'`);
    console.log(`[SESSIONS] Current sessions:`, sessions.map(s => ({ id: s.session_id, name: s.name })));
    
    // Update the session in our local sessions array
    const sessionIndex = sessions.findIndex(s => s.session_id === sessionId);
    console.log(`[SESSIONS] Session index found: ${sessionIndex}`);
    
    if (sessionIndex !== -1) {
      console.log(`[SESSIONS] 📝 Updating session at index ${sessionIndex}: '${sessions[sessionIndex].name}' -> '${newName}'`);
      sessions[sessionIndex].name = newName;
      sessions[sessionIndex].is_auto_named = false;
      
      // Update the dropdown to reflect the new name
      console.log(`[SESSIONS] 🔄 Updating dropdown...`);
      updateSessionDropdown();
      
      // If this is the currently selected session, update the dropdown value
      if (currentSessionId === sessionId) {
        console.log(`[SESSIONS] 🎯 This is the current session, updating dropdown selection`);
        sessionDropdown.value = sessionId;
      }
      
      console.log(`[SESSIONS] ✅ Updated session name to: ${newName}`);
    } else {
      console.warn(`[SESSIONS] ❌ Session not found in local array: ${sessionId}`);
      console.warn(`[SESSIONS] Available sessions:`, sessions.map(s => s.session_id));
    }
  }
  
  // Expose functions for external use
  window.__sb_get_current_session = () => currentSessionId;
  window.__sb_set_current_session = (sessionId) => selectSession(sessionId);
  // Forward to the unified renderer exported by script.js, with safety guard
  window.__sb_append_message = (role, content, isReport = false) => {
    if (window.appendMessage) {
      window.appendMessage(role, content, isReport);
    } else {
      // Fallback basic rendering if script.js didn't load for some reason
      const messages = document.getElementById('messages');
      if (!messages) return;
      const div = document.createElement('div');
      div.className = `msg ${role}`;
      div.textContent = content;
      messages.appendChild(div);
      messages.scrollTop = messages.scrollHeight;
    }
  };
  window.__sb_load_sessions = loadSessions;
  window.__sb_update_session_name = updateSessionName;
  
  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
