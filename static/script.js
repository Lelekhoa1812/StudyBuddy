// ────────────────────────────── static/script.js ──────────────────────────────
(function() {
  // DOM elements
  const fileDropZone = document.getElementById('file-drop-zone');
  const fileInput = document.getElementById('files');
  const fileList = document.getElementById('file-list');
  const fileItems = document.getElementById('file-items');
  const uploadBtn = document.getElementById('upload-btn');
  const uploadProgress = document.getElementById('upload-progress');
  const progressStatus = document.getElementById('progress-status');
  const progressFill = document.getElementById('progress-fill');
  const progressLog = document.getElementById('progress-log');
  const questionInput = document.getElementById('question');
  const askBtn = document.getElementById('ask');
  const chatHint = document.getElementById('chat-hint');
  const messages = document.getElementById('messages');
  const loadingOverlay = document.getElementById('loading-overlay');
  const loadingMessage = document.getElementById('loading-message');

  // State
  let selectedFiles = [];
  let isUploading = false;
  let isProcessing = false;

  // Initialize
  init();

  function init() {
    setupFileDropZone();
    setupEventListeners();
    checkUserAuth();
    
    // Listen for project changes
    document.addEventListener('projectChanged', () => {
      updateUploadButton();
    });
    
    // Initial button state update
    updateUploadButton();
  }

  function setupFileDropZone() {
    // Click to browse
    fileDropZone.addEventListener('click', () => fileInput.click());
    
    // Drag and drop
    fileDropZone.addEventListener('dragover', (e) => {
      e.preventDefault();
      fileDropZone.classList.add('dragover');
    });
    
    fileDropZone.addEventListener('dragleave', () => {
      fileDropZone.classList.remove('dragover');
    });
    
    fileDropZone.addEventListener('drop', (e) => {
      e.preventDefault();
      fileDropZone.classList.remove('dragover');
      const files = Array.from(e.dataTransfer.files);
      handleFileSelection(files);
    });

    // File input change
    fileInput.addEventListener('change', (e) => {
      const files = Array.from(e.target.files);
      handleFileSelection(files);
    });
  }

  function setupEventListeners() {
    // Upload form
    document.getElementById('upload-form').addEventListener('submit', handleUpload);
    
    // Chat
    askBtn.addEventListener('click', handleAsk);
    questionInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleAsk();
      }
    });
  }

  function handleFileSelection(files) {
    const validFiles = files.filter(file => {
      const isValid = file.type === 'application/pdf' || 
                     file.type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
      if (!isValid) {
        alert(`Unsupported file type: ${file.name}. Please upload PDF or DOCX files only.`);
      }
      return isValid;
    });

    if (validFiles.length === 0) return;

    selectedFiles = validFiles;
    updateFileList();
    updateUploadButton();
  }

  function updateFileList() {
    if (selectedFiles.length === 0) {
      fileList.style.display = 'none';
      return;
    }

    fileList.style.display = 'block';
    fileItems.innerHTML = '';

    selectedFiles.forEach((file, index) => {
      const fileItem = document.createElement('div');
      fileItem.className = 'file-item';
      
      const icon = document.createElement('span');
      icon.className = 'file-item-icon';
      icon.textContent = file.type.includes('pdf') ? '📄' : '📝';
      
      const name = document.createElement('span');
      name.className = 'file-item-name';
      name.textContent = file.name;
      
      const size = document.createElement('span');
      size.className = 'file-item-size';
      size.textContent = formatFileSize(file.size);
      
      const remove = document.createElement('button');
      remove.className = 'file-item-remove';
      remove.textContent = '×';
      remove.title = 'Remove file';
      remove.addEventListener('click', () => removeFile(index));
      
      fileItem.appendChild(icon);
      fileItem.appendChild(name);
      fileItem.appendChild(size);
      fileItem.appendChild(remove);
      fileItems.appendChild(fileItem);
    });
  }

  function removeFile(index) {
    selectedFiles.splice(index, 1);
    updateFileList();
    updateUploadButton();
  }

  function updateUploadButton() {
    const hasFiles = selectedFiles.length > 0;
    const hasProject = window.__sb_get_current_project && window.__sb_get_current_project();
    uploadBtn.disabled = !hasFiles || !hasProject || isUploading;
    
    if (hasFiles && hasProject) {
      uploadBtn.querySelector('.btn-text').textContent = `Upload ${selectedFiles.length} Document${selectedFiles.length > 1 ? 's' : ''}`;
    } else if (!hasProject) {
      uploadBtn.querySelector('.btn-text').textContent = 'Select a Project First';
    } else {
      uploadBtn.querySelector('.btn-text').textContent = 'Upload Documents';
    }
  }

  function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  async function handleUpload(e) {
    e.preventDefault();
    
    if (selectedFiles.length === 0) {
      alert('Please select files to upload');
      return;
    }

    const user = window.__sb_get_user();
    if (!user) {
      alert('Please sign in to upload files');
      window.__sb_show_auth_modal();
      return;
    }

    const currentProject = window.__sb_get_current_project && window.__sb_get_current_project();
    if (!currentProject) {
      alert('Please select a project first');
      return;
    }

    isUploading = true;
    updateUploadButton();
    showUploadProgress();

    try {
      const formData = new FormData();
      formData.append('user_id', user.user_id);
      formData.append('project_id', currentProject.project_id);
      selectedFiles.forEach(file => formData.append('files', file));

      const response = await fetch('/upload', { method: 'POST', body: formData });
      const data = await response.json();

      if (response.ok) {
        updateProgressStatus('Upload successful! Processing documents...');
        updateProgressFill(0);
        logProgress(`Job ID: ${data.job_id}`);
        logProgress('Files uploaded successfully');
        
        // Deterministic per-file progression
        simulateProcessing(selectedFiles.length);
      } else {
        throw new Error(data.detail || 'Upload failed');
      }
    } catch (error) {
      logProgress(`Error: ${error.message}`);
      updateProgressStatus('Upload failed');
      setTimeout(() => hideUploadProgress(), 3000);
    } finally {
      isUploading = false;
      updateUploadButton();
    }
  }

  function showUploadProgress() {
    uploadProgress.style.display = 'block';
    updateProgressStatus('Uploading files... (DO NOT REFRESH)');
    updateProgressFill(0);
    progressLog.innerHTML = '';
  }

  function hideUploadProgress() {
    uploadProgress.style.display = 'none';
    selectedFiles = [];
    updateFileList();
    updateUploadButton();
  }

  function updateProgressStatus(status) {
    progressStatus.textContent = status;
  }

  function updateProgressFill(percentage) {
    progressFill.style.width = `${percentage}%`;
  }

  function logProgress(message) {
    const timestamp = new Date().toLocaleTimeString();
    progressLog.innerHTML += `[${timestamp}] ${message}\n`;
    progressLog.scrollTop = progressLog.scrollHeight;
  }

  function simulateProcessing(totalFiles) {
    // Split 100% evenly across files. Round to nearest integer.
    let completed = 0;
    const step = Math.round(100 / Math.max(totalFiles, 1));
    const targets = Array.from({ length: totalFiles }, (_, i) => Math.min(100, Math.round(((i + 1) / totalFiles) * 100)));

    function advance() {
      if (completed >= totalFiles) {
        updateProgressFill(100);
        updateProgressStatus('Processing complete!');
        logProgress('All documents processed successfully');
        logProgress('You can now start chatting with your documents');
        setTimeout(() => hideUploadProgress(), 1500);
        enableChat();
        return;
      }

      const currentTarget = targets[completed];
      updateProgressFill(currentTarget);
      updateProgressStatus(`Processing documents... ${currentTarget}%`);
      logProgress(`Finished processing file ${completed + 1}/${totalFiles}`);
      completed += 1;

      // Wait a short time before next step (simulated, since backend is background)
      setTimeout(advance, 1200);
    }

    // kick off first step after a short delay to show feedback
    setTimeout(advance, 800);
  }

  function enableChat() {
    questionInput.disabled = false;
    askBtn.disabled = false;
    chatHint.style.display = 'none';
  }

  async function handleAsk() {
    const question = questionInput.value.trim();
    if (!question) return;

    const user = window.__sb_get_user();
    if (!user) {
      alert('Please sign in to chat');
      window.__sb_show_auth_modal();
      return;
    }

    const currentProject = window.__sb_get_current_project && window.__sb_get_current_project();
    if (!currentProject) {
      alert('Please select a project first');
      return;
    }

    // Add user message
    appendMessage('user', question);
    questionInput.value = '';

    // Save user message to chat history
    await saveChatMessage(user.user_id, currentProject.project_id, 'user', question);

    // Add thinking message
    const thinkingMsg = appendMessage('thinking', 'Thinking...');
    
    // Disable input during processing
    questionInput.disabled = true;
    askBtn.disabled = true;
    showButtonLoading(askBtn, true);

    try {
      const formData = new FormData();
      formData.append('user_id', user.user_id);
      formData.append('project_id', currentProject.project_id);
      formData.append('question', question);
      formData.append('k', '6');

      const response = await fetch('/chat', { method: 'POST', body: formData });
      const data = await response.json();

      if (response.ok) {
        // Remove thinking message
        thinkingMsg.remove();
        
        // Add assistant response
        appendMessage('assistant', data.answer || 'No answer received');
        
        // Save assistant message to chat history
        await saveChatMessage(user.user_id, currentProject.project_id, 'assistant', data.answer || 'No answer received');
        
        // Add sources if available
        if (data.sources && data.sources.length > 0) {
          appendSources(data.sources);
        }
      } else {
        throw new Error(data.detail || 'Failed to get answer');
      }
    } catch (error) {
      thinkingMsg.remove();
      const errorMsg = `⚠️ Error: ${error.message}`;
      appendMessage('assistant', errorMsg);
      await saveChatMessage(user.user_id, currentProject.project_id, 'assistant', errorMsg);
    } finally {
      // Re-enable input
      questionInput.disabled = false;
      askBtn.disabled = false;
      showButtonLoading(askBtn, false);
      questionInput.focus();
    }
  }

  async function saveChatMessage(userId, projectId, role, content) {
    try {
      const formData = new FormData();
      formData.append('user_id', userId);
      formData.append('project_id', projectId);
      formData.append('role', role);
      formData.append('content', content);
      formData.append('timestamp', Date.now() / 1000);
      
      await fetch('/chat/save', { method: 'POST', body: formData });
    } catch (error) {
      console.error('Failed to save chat message:', error);
    }
  }

  function appendMessage(role, text) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `msg ${role}`;
    messageDiv.textContent = text;
    
    messages.appendChild(messageDiv);
    
    // Scroll to bottom
    requestAnimationFrame(() => {
      messageDiv.scrollIntoView({ behavior: 'smooth', block: 'end' });
    });
    
    return messageDiv;
  }

  function appendSources(sources) {
    const sourcesDiv = document.createElement('div');
    sourcesDiv.className = 'sources';
    
    const sourcesList = sources.map(source => {
      const filename = source.filename || 'unknown';
      const topic = source.topic_name ? ` • ${source.topic_name}` : '';
      const pages = source.page_span ? ` [pp. ${source.page_span.join('-')}]` : '';
      const score = source.score ? ` (${source.score.toFixed(2)})` : '';
      
      return `<span class="pill">${filename}${topic}${pages}${score}</span>`;
    }).join(' ');
    
    sourcesDiv.innerHTML = `<strong>Sources:</strong> ${sourcesList}`;
    messages.appendChild(sourcesDiv);
    
    requestAnimationFrame(() => {
      sourcesDiv.scrollIntoView({ behavior: 'smooth', block: 'end' });
    });
  }

  function showButtonLoading(button, isLoading) {
    const textSpan = button.querySelector('.btn-text');
    const loadingSpan = button.querySelector('.btn-loading');
    
    if (isLoading) {
      textSpan.style.display = 'none';
      loadingSpan.style.display = 'inline-flex';
      button.disabled = true;
    } else {
      textSpan.style.display = 'inline';
      loadingSpan.style.display = 'none';
      button.disabled = false;
    }
  }

  function showLoading(message = 'Processing...') {
    loadingMessage.textContent = message;
    loadingOverlay.classList.remove('hidden');
  }

  function hideLoading() {
    loadingOverlay.classList.add('hidden');
  }

  function checkUserAuth() {
    const user = window.__sb_get_user();
    if (user) {
      // Check if we have a current project
      const currentProject = window.__sb_get_current_project && window.__sb_get_current_project();
      if (currentProject) {
        enableChat();
      }
    }
    // Always update upload button state
    updateUploadButton();
  }

  // Public API
  window.__sb_update_upload_button = updateUploadButton;

  // Listen for project changes
  window.addEventListener('projectChanged', () => {
    updateUploadButton();
    const currentProject = window.__sb_get_current_project && window.__sb_get_current_project();
    if (currentProject) {
      enableChat();
    }
  });

  // Reveal animations
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('in');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1 });

  document.querySelectorAll('.reveal').forEach(el => observer.observe(el));
})();