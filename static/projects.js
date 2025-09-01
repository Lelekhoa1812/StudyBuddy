// ────────────────────────────── static/projects.js ──────────────────────────────
(function() {
  // DOM elements
  const newProjectBtn = document.getElementById('new-project-btn');
  const projectList = document.getElementById('project-list');
  const newProjectModal = document.getElementById('new-project-modal');
  const newProjectForm = document.getElementById('new-project-form');
  const cancelProjectBtn = document.getElementById('cancel-project');
  const welcomeNewProjectBtn = document.getElementById('welcome-new-project');
  const projectHeader = document.getElementById('project-header');
  const currentProjectName = document.getElementById('current-project-name');
  const currentProjectDescription = document.getElementById('current-project-description');
  const deleteProjectBtn = document.getElementById('delete-project-btn');
  const welcomeScreen = document.getElementById('welcome-screen');
  const projectContent = document.getElementById('project-content');

  // State
  let currentProject = null;
  let projects = [];

  // Initialize
  init();

  function init() {
    setupEventListeners();
    loadProjects();
  }

  function setupEventListeners() {
    newProjectBtn.addEventListener('click', showNewProjectModal);
    welcomeNewProjectBtn.addEventListener('click', showNewProjectModal);
    cancelProjectBtn.addEventListener('click', hideNewProjectModal);
    newProjectForm.addEventListener('submit', handleCreateProject);
    deleteProjectBtn.addEventListener('click', handleDeleteProject);
  }

  function handleDeleteProject() {
    if (!currentProject) return;
    
    if (confirm(`Are you sure you want to delete "${currentProject.name}"? This will remove all associated files and chat history.`)) {
      deleteProject(currentProject.project_id);
    }
  }

  async function loadProjects() {
    const user = window.__sb_get_user();
    if (!user) return;

    try {
      const response = await fetch(`/projects?user_id=${user.user_id}`);
      if (response.ok) {
        const data = await response.json();
        projects = data.projects || [];
        renderProjectList();
        
        // If no projects, show welcome screen
        if (projects.length === 0) {
          showWelcomeScreen();
        } else {
          // Select first project by default
          selectProject(projects[0]);
        }
        
        // Update upload button after projects are loaded
        if (window.__sb_update_upload_button) {
          window.__sb_update_upload_button();
        }
      }
    } catch (error) {
      console.error('Failed to load projects:', error);
    }
  }

  function renderProjectList() {
    projectList.innerHTML = '';
    
    projects.forEach(project => {
      const projectItem = document.createElement('div');
      projectItem.className = 'project-item';
      if (currentProject && currentProject.project_id === project.project_id) {
        projectItem.classList.add('active');
      }
      
      projectItem.innerHTML = `
        <div class="project-item-icon">📁</div>
        <div class="project-item-info">
          <div class="project-item-name">${project.name}</div>
          <div class="project-item-description">${project.description || 'No description'}</div>
        </div>
        <div class="project-item-actions">
          <button class="project-item-delete" title="Delete project">🗑️</button>
        </div>
      `;
      
      // Add click handlers
      projectItem.addEventListener('click', (e) => {
        if (!e.target.classList.contains('project-item-delete')) {
          selectProject(project);
        }
      });
      
      // Delete button handler
      const deleteBtn = projectItem.querySelector('.project-item-delete');
      deleteBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (confirm(`Are you sure you want to delete "${project.name}"? This will remove all associated files and chat history.`)) {
          deleteProject(project.project_id);
        }
      });
      
      projectList.appendChild(projectItem);
    });
  }

  function selectProject(project) {
    currentProject = project;
    
    // Update UI
    currentProjectName.textContent = project.name;
    currentProjectDescription.textContent = project.description || 'No description';
    
    // Show project content
    projectHeader.style.display = 'flex';
    welcomeScreen.style.display = 'none';
    projectContent.style.display = 'block';
    
    // Show both upload and chat sections by default
    const uploadSection = document.getElementById('upload-section');
    const chatSection = document.getElementById('chat-section');
    if (uploadSection) uploadSection.style.display = 'block';
    if (chatSection) chatSection.style.display = 'block';
    
    // Enable chat functionality when project is selected
    if (window.__sb_enable_chat) {
      window.__sb_enable_chat();
    }
    
    // Update project list
    renderProjectList();
    
    // Load chat history
    loadChatHistory();
    
    // Store current project in localStorage
    localStorage.setItem('sb_current_project', JSON.stringify(project));
    
    // Enable chat if user is authenticated
    const user = window.__sb_get_user();
    if (user) {
      enableChat();
    }
    
    // Update page title to show project name
    if (window.__sb_update_page_title) {
      window.__sb_update_page_title(`Project: ${project.name}`);
    }
    
    // Dispatch custom event to notify other scripts that project has changed
    const event = new CustomEvent('projectChanged', { detail: { project } });
    document.dispatchEvent(event);
    
    // Update upload button if the function exists
    if (window.__sb_update_upload_button) {
      window.__sb_update_upload_button();
    }
    // Ensure stored files are loaded immediately
    if (window.__sb_load_stored_files) {
      window.__sb_load_stored_files();
    }
  }

  function showWelcomeScreen() {
    currentProject = null;
    projectHeader.style.display = 'none';
    welcomeScreen.style.display = 'flex';
    projectContent.style.display = 'none';
    localStorage.removeItem('sb_current_project');
  }

  function showNewProjectModal() {
    newProjectModal.classList.remove('hidden');
    document.getElementById('project-name').focus();
  }

  function hideNewProjectModal() {
    newProjectModal.classList.add('hidden');
    newProjectForm.reset();
  }

  async function handleCreateProject(e) {
    e.preventDefault();
    
    const user = window.__sb_get_user();
    if (!user) {
      alert('Please sign in to create a project');
      return;
    }
    
    const name = document.getElementById('project-name').value.trim();
    const description = document.getElementById('project-description').value.trim();
    
    if (!name) {
      alert('Project name is required');
      return;
    }
    
    try {
      const formData = new FormData();
      formData.append('user_id', user.user_id);
      formData.append('name', name);
      formData.append('description', description);
      
      const response = await fetch('/projects/create', { method: 'POST', body: formData });
      
      if (response.ok) {
        const project = await response.json();
        projects.unshift(project);
        renderProjectList();
        selectProject(project);
        hideNewProjectModal();
      } else {
        const error = await response.json();
        alert(error.detail || 'Failed to create project');
      }
    } catch (error) {
      alert('Failed to create project. Please try again.');
    }
  }

  async function deleteProject(projectId) {
    const user = window.__sb_get_user();
    if (!user) return;
    
    try {
      const response = await fetch(`/projects/${projectId}?user_id=${user.user_id}`, {
        method: 'DELETE'
      });
      
      if (response.ok) {
        // Remove from local list
        projects = projects.filter(p => p.project_id !== projectId);
        
        // If this was the current project, clear it
        if (currentProject && currentProject.project_id === projectId) {
          currentProject = null;
          if (projects.length > 0) {
            selectProject(projects[0]);
          } else {
            showWelcomeScreen();
          }
        }
        
        renderProjectList();
      } else {
        alert('Failed to delete project');
      }
    } catch (error) {
      alert('Failed to delete project. Please try again.');
    }
  }

  async function loadChatHistory() {
    if (!currentProject) return;
    
    const user = window.__sb_get_user();
    if (!user) return;
    
    try {
      const response = await fetch(`/chat/history?user_id=${user.user_id}&project_id=${currentProject.project_id}`);
      if (response.ok) {
        const data = await response.json();
        const messages = data.messages || [];
        
        // Clear existing messages
        const messagesContainer = document.getElementById('messages');
        messagesContainer.innerHTML = '';
        
        // Load chat history
        messages.forEach(msg => {
          appendMessage(msg.role, msg.content);
        });
        
        // Scroll to bottom
        if (messages.length > 0) {
          messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
      }
    } catch (error) {
      console.error('Failed to load chat history:', error);
    }
  }

  function appendMessage(role, content) {
    const messagesContainer = document.getElementById('messages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `msg ${role}`;
    messageDiv.textContent = content;
    messagesContainer.appendChild(messageDiv);
  }

  function enableChat() {
    const questionInput = document.getElementById('question');
    const askBtn = document.getElementById('send-btn');
    const chatHint = document.getElementById('chat-hint');
    
    if (currentProject) {
      questionInput.disabled = false;
      askBtn.disabled = false;
      chatHint.style.display = 'none';
    }
  }

  // Public API
  window.__sb_get_current_project = () => currentProject;
  window.__sb_load_chat_history = loadChatHistory;
  window.__sb_enable_chat = enableChat;
  window.__sb_load_projects = loadProjects;
  
  // Load current project from localStorage on page load
  window.addEventListener('load', () => {
    const savedProject = localStorage.getItem('sb_current_project');
    if (savedProject) {
      try {
        const project = JSON.parse(savedProject);
        // Check if project still exists in our list
        const exists = projects.find(p => p.project_id === project.project_id);
        if (exists) {
          selectProject(exists);
        }
      } catch (e) {
        localStorage.removeItem('sb_current_project');
      }
    }
  });
})();
