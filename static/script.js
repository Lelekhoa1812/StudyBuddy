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
  const sendBtn = document.getElementById('send-btn');
  const chatHint = document.getElementById('chat-hint');
  const messages = document.getElementById('messages');
  const reportLink = document.getElementById('report-link');
  const loadingOverlay = document.getElementById('loading-overlay');
  const loadingMessage = document.getElementById('loading-message');

  // State
  let selectedFiles = [];
  let isUploading = false;
  let isProcessing = false;

  // Initialize
  init();

  function init() {
    console.log('[SCRIPT] Initializing script.js...');
    console.log('[SCRIPT] DOM elements found:', {
      fileDropZone: !!fileDropZone,
      fileInput: !!fileInput,
      fileList: !!fileList,
      fileItems: !!fileItems,
      uploadBtn: !!uploadBtn,
      uploadProgress: !!uploadProgress,
      progressStatus: !!progressStatus,
      progressFill: !!progressFill,
      progressLog: !!progressLog,
      questionInput: !!questionInput,
      sendBtn: !!sendBtn,
      chatHint: !!chatHint,
      messages: !!messages,
      reportLink: !!reportLink,
      loadingOverlay: !!loadingOverlay,
      loadingMessage: !!loadingMessage
    });
    
    setupFileDropZone();
    setupEventListeners();
    checkUserAuth();
    
    // Listen for project changes
    document.addEventListener('projectChanged', () => {
      updateUploadButton();
    });
    
    // Initial button state update
    updateUploadButton();
    
    console.log('[SCRIPT] Initialization complete');
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
    console.log('[SCRIPT] Setting up event listeners...');
    
    // Upload form
    const uploadForm = document.getElementById('upload-form');
    if (uploadForm) {
      uploadForm.addEventListener('submit', handleUpload);
      console.log('[SCRIPT] Upload form listener added');
    } else {
      console.error('[SCRIPT] Upload form not found!');
    }
    
    // Chat
    if (sendBtn) {
      sendBtn.addEventListener('click', handleAsk);
      console.log('[SCRIPT] Send button click listener added');
    } else {
      console.error('[SCRIPT] Send button not found!');
    }
    
    if (questionInput) {
      // Convert to textarea behavior: Enter submits, Shift+Enter for newline
      questionInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          handleAsk();
        }
      });
      questionInput.addEventListener('input', autoGrowTextarea);
      console.log('[SCRIPT] Question input listeners added');
    } else {
      console.error('[SCRIPT] Question input not found!');
    }

    // Clear chat history
    const clearBtn = document.getElementById('clear-chat-btn');
    if (clearBtn) {
      clearBtn.addEventListener('click', async () => {
        const user = window.__sb_get_user();
        const currentProject = window.__sb_get_current_project && window.__sb_get_current_project();
        if (!user || !currentProject) return;
        if (!confirm('Clear chat history for this project?')) return;
        try {
          const res = await fetch(`/chat/history?user_id=${encodeURIComponent(user.user_id)}&project_id=${encodeURIComponent(currentProject.project_id)}`, { method: 'DELETE' });
          if (res.ok) {
            document.getElementById('messages').innerHTML = '';
          } else {
            alert('Failed to clear history');
          }
        } catch (e) {
          console.error('Failed to clear chat history:', e);
        }
      });
    }

    // Report mode toggle
    if (reportLink) {
      reportLink.addEventListener('click', (e) => {
        e.preventDefault();
        toggleReportMode();
      });
    }

    // New project form
    const newProjectForm = document.getElementById('new-project-form');
    if (newProjectForm) {
      newProjectForm.addEventListener('submit', handleCreateProject);
    }

    // Cancel project button
    const cancelProjectBtn = document.getElementById('cancel-project');
    if (cancelProjectBtn) {
      cancelProjectBtn.addEventListener('click', hideNewProjectModal);
    }

    console.log('[SCRIPT] Event listeners setup complete');
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

  // Stored files view
  async function loadStoredFiles() {
    const user = window.__sb_get_user();
    const currentProject = window.__sb_get_current_project && window.__sb_get_current_project();
    if (!user || !currentProject) return;
    try {
      const res = await fetch(`/files?user_id=${encodeURIComponent(user.user_id)}&project_id=${encodeURIComponent(currentProject.project_id)}`);
      if (!res.ok) return;
      const data = await res.json();
      const files = data.files || [];
      renderStoredFiles(files);
      // Enable Report button when at least one file exists
      if (reportLink) {
        // Disable visually by muted color when no files
        reportLink.style.pointerEvents = (files.length === 0) ? 'none' : 'auto';
        reportLink.title = 'Generate report from selected document';
      }
      window.__sb_current_filenames = new Set((data.filenames || []).map(f => (f || '').toLowerCase()));
    } catch {}
  }

  function renderStoredFiles(files) {
    const container = document.getElementById('stored-file-items');
    if (container) {
      if (!files || files.length === 0) {
        container.innerHTML = '<div class="muted">No files stored yet.</div>';
      } else {
        container.innerHTML = files.map(f => `<div class=\"pill\">${f.filename}</div>`).join(' ');
      }
    }
    // Also render into Files page section
    const list = document.getElementById('files-list');
    if (!list) return;
    if (!files || files.length === 0) {
      list.innerHTML = '<div class="muted">No files in this project.</div>';
      return;
    }
    list.innerHTML = files.map((f, idx) => `
      <div class="file-card" data-idx="${idx}">
        <div class="file-card-head">
          <div class="file-name">${f.filename}</div>
        </div>
        <div class="file-summary" id="file-summary-${idx}">${(f.summary || '').replace(/</g,'&lt;')}</div>
        <div class="file-card-actions">
          <button class="see-more-btn" data-idx="${idx}">… See more</button>
          <div class="file-actions-right">
            <button class="btn-danger file-del" data-fn="${encodeURIComponent(f.filename)}" title="Delete">Delete</button>
          </div>
        </div>
      </div>
    `).join('');
    // bind deletes
    list.querySelectorAll('.file-del').forEach(btn => {
      btn.addEventListener('click', async () => {
        const filename = decodeURIComponent(btn.getAttribute('data-fn'));
        if (!confirm(`Delete ${filename}? This will remove all related chunks.`)) return;
        const user = window.__sb_get_user();
        const currentProject = window.__sb_get_current_project && window.__sb_get_current_project();
        if (!user || !currentProject) return;
        try {
          const res = await fetch(`/files?user_id=${encodeURIComponent(user.user_id)}&project_id=${encodeURIComponent(currentProject.project_id)}&filename=${encodeURIComponent(filename)}`, { method: 'DELETE' });
          if (res.ok) {
            await loadStoredFiles();
          } else {
            alert('Failed to delete file');
          }
        } catch {}
      });
    });
    // bind see more/less
    list.querySelectorAll('.see-more-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const idx = btn.getAttribute('data-idx');
        const summary = document.getElementById(`file-summary-${idx}`);
        if (!summary) return;
        const expanded = summary.classList.toggle('expanded');
        btn.textContent = expanded ? 'See less' : '… See more';
      });
    });
  }

  // Expose show files section
  window.__sb_show_files_section = async () => {
    await loadStoredFiles();
  };

  // Duplicate detection: returns {toUpload, replace, renameMap}
  async function resolveDuplicates(files) {
    const existing = window.__sb_current_filenames || new Set();
    const toUpload = [];
    const replace = [];
    const renameMap = {};
    for (const f of files) {
      const name = f.name;
      if (existing.has(name.toLowerCase())) {
        const choice = await promptDuplicateChoice(name);
        if (choice === 'cancel') {
          // skip this file
        } else if (choice === 'replace') {
          replace.push(name);
          toUpload.push(f);
        } else if (choice && choice.startsWith('rename:')) {
          const newName = choice.slice(7);
          // create a new File with newName
          const renamed = new File([f], newName, { type: f.type, lastModified: f.lastModified });
          renameMap[name] = newName;
          toUpload.push(renamed);
        }
      } else {
        toUpload.push(f);
      }
    }
    return { toUpload, replace, renameMap };
  }

  function promptDuplicateChoice(filename) {
    return new Promise((resolve) => {
      // Minimal UX: use confirm/prompt; can be replaced with real modal later
      const msg = `A similar file named ${filename} already exists.\nChoose: [Cancel] to skip, [OK] to choose Replace or Rename.`;
      if (!confirm(msg)) { resolve('cancel'); return; }
      const answer = prompt('Type "replace" to overwrite, or enter a new filename to rename:', 'replace');
      if (!answer) { resolve('cancel'); return; }
      if (answer.trim().toLowerCase() === 'replace') { resolve('replace'); return; }
      resolve('rename:' + answer.trim());
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
      // Check duplicates against server list first
      await loadStoredFiles();
      const { toUpload, replace, renameMap } = await resolveDuplicates(selectedFiles);
      if (toUpload.length === 0) {
        updateProgressStatus('No files to upload');
        setTimeout(() => hideUploadProgress(), 1000);
        return;
      }
      const formData = new FormData();
      formData.append('user_id', user.user_id);
      formData.append('project_id', currentProject.project_id);
      toUpload.forEach(file => formData.append('files', file));
      if (replace.length > 0) {
        formData.append('replace_filenames', JSON.stringify(replace));
      }
      if (Object.keys(renameMap).length > 0) {
        formData.append('rename_map', JSON.stringify(renameMap));
      }

      const response = await fetch('/upload', { method: 'POST', body: formData });
      const data = await response.json();

      if (response.ok) {
        updateProgressStatus('Upload successful! Processing documents...');
        updateProgressFill(0);
        // Friendly, non-technical messages only
        logProgress('Files uploaded successfully');
        
        // Poll backend for real progress
        startUploadStatusPolling(data.job_id, data.total_files || toUpload.length);
        // Refresh stored files list after a short delay
        setTimeout(loadStoredFiles, 2000);
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

  function startUploadStatusPolling(jobId, totalFiles) {
    let stopped = false;
    let failCount = 0;
    const maxFailsBeforeSilentStop = 30; // ~36s at 1200ms
    const interval = setInterval(async () => {
      if (stopped) return;
      try {
        const res = await fetch(`/upload/status?job_id=${encodeURIComponent(jobId)}`);
        if (!res.ok) { failCount++; return; }
        const status = await res.json();
        const percent = Math.max(0, Math.min(100, parseInt(status.percent || 0, 10)));
        const completed = status.completed || 0;
        const total = status.total || totalFiles || 1;
        updateProgressFill(percent);
        updateProgressStatus(percent >= 100 ? 'Finalizing...' : `Processing documents (${completed}/${total}) · ${percent}%`);
        if (status.status === 'completed' || percent >= 100) {
          clearInterval(interval);
          stopped = true;
          updateProgressFill(100);
          updateProgressStatus('Processing complete!');
          logProgress('You can now start chatting with your documents');
          setTimeout(() => hideUploadProgress(), 1500);
          enableChat();
          // Final refresh of stored files
          setTimeout(loadStoredFiles, 1000);
        }
      } catch (e) {
        // Swallow transient errors; update a friendly spinner-like status
        failCount++;
        if (failCount >= maxFailsBeforeSilentStop) {
          clearInterval(interval);
          stopped = true;
          updateProgressStatus('Still working...');
        }
      }
    }, 1200);
  }

  function enableChat() {
    console.log('[SCRIPT] enableChat called');
    console.log('[SCRIPT] Before enabling - questionInput.disabled:', questionInput.disabled);
    console.log('[SCRIPT] Before enabling - sendBtn.disabled:', sendBtn.disabled);
    
    questionInput.disabled = false;
    sendBtn.disabled = false;
    chatHint.style.display = 'none';
    autoGrowTextarea();
    
    console.log('[SCRIPT] After enabling - questionInput.disabled:', questionInput.disabled);
    console.log('[SCRIPT] After enabling - sendBtn.disabled:', sendBtn.disabled);
    console.log('[SCRIPT] Chat enabled successfully');
  }

  async function handleAsk() {
    console.log('[SCRIPT] handleAsk called');
    const question = questionInput.value.trim();
    if (!question) return;

    const user = window.__sb_get_user();
    console.log('[SCRIPT] User:', user);
    if (!user) {
      alert('Please sign in to chat');
      window.__sb_show_auth_modal();
      return;
    }

    const currentProject = window.__sb_get_current_project && window.__sb_get_current_project();
    console.log('[SCRIPT] Current project:', currentProject);
    if (!currentProject) {
      alert('Please select a project first');
      return;
    }

    console.log('[SCRIPT] Starting chat request...');
    // Add user message
    appendMessage('user', question);
    questionInput.value = '';
    autoGrowTextarea();

    // Save user message to chat history
    await saveChatMessage(user.user_id, currentProject.project_id, 'user', question);

    // Add thinking message
    const thinkingMsg = appendMessage('thinking', 'Thinking...');
    
    // Disable input during processing
    questionInput.disabled = true;
    sendBtn.disabled = true;
    showButtonLoading(sendBtn, true);

    try {
      // Branch: if report mode is active → call /report with textarea as instructions
      if (isReportModeActive()) {
        console.log('[SCRIPT] Report mode active, calling /report');
        const filename = pickActiveFilename();
        if (!filename) throw new Error('Please select a document to generate a report');
        const form = new FormData();
        form.append('user_id', user.user_id);
        form.append('project_id', currentProject.project_id);
        form.append('filename', filename);
        form.append('outline_words', '200');
        form.append('report_words', '1200');
        form.append('instructions', question);
        const response = await fetch('/report', { method: 'POST', body: form });
        const data = await response.json();
        if (response.ok) {
          thinkingMsg.remove();
          appendMessage('assistant', data.report_markdown || 'No report');
          if (data.sources && data.sources.length) appendSources(data.sources);
          // Save assistant report to chat history for persistence
          try { await saveChatMessage(user.user_id, currentProject.project_id, 'assistant', data.report_markdown || 'No report'); } catch {}
        } else {
          throw new Error(data.detail || 'Failed to generate report');
        }
      } else {
        console.log('[SCRIPT] Chat mode active, calling /chat');
        const formData = new FormData();
        formData.append('user_id', user.user_id);
        formData.append('project_id', currentProject.project_id);
        formData.append('question', question);
        formData.append('k', '6');
        console.log('[SCRIPT] Sending request to /chat with data:', {
          user_id: user.user_id,
          project_id: currentProject.project_id,
          question: question
        });
        const response = await fetch('/chat', { method: 'POST', body: formData });
        console.log('[SCRIPT] Response status:', response.status);
        const data = await response.json();
        console.log('[SCRIPT] Response data:', data);
        if (response.ok) {
          thinkingMsg.remove();
          appendMessage('assistant', data.answer || 'No answer received');
          await saveChatMessage(user.user_id, currentProject.project_id, 'assistant', data.answer || 'No answer received');
          if (data.sources && data.sources.length > 0) appendSources(data.sources);
        } else {
          throw new Error(data.detail || 'Failed to get answer');
        }
      }
    } catch (error) {
      console.error('[SCRIPT] Error in handleAsk:', error);
      thinkingMsg.remove();
      const errorMsg = `⚠️ Error: ${error.message}`;
      appendMessage('assistant', errorMsg);
      await saveChatMessage(user.user_id, currentProject.project_id, 'assistant', errorMsg);
    } finally {
      // Re-enable input
      questionInput.disabled = false;
      sendBtn.disabled = false;
      showButtonLoading(sendBtn, false);
      questionInput.focus();
    }
  }

  function toggleReportMode() {
    if (!reportLink) return;
    reportLink.classList.toggle('active');
  }

  function isReportModeActive() {
    return reportLink && reportLink.classList.contains('active');
  }

  function pickActiveFilename() {
    const candidates = Array.from(document.querySelectorAll('#stored-file-items .pill'));
    let active = candidates.find(el => el.classList.contains('active'));
    if (!active && candidates.length) active = candidates[0];
    return active ? active.textContent.trim() : '';
  }

  function autoGrowTextarea() {
    if (!questionInput) return;
    // Reset height to measure content size
    questionInput.style.height = 'auto';
    const style = window.getComputedStyle(questionInput);
    const borderTop = parseInt(style.borderTopWidth) || 0;
    const borderBottom = parseInt(style.borderBottomWidth) || 0;
    const paddingTop = parseInt(style.paddingTop) || 0;
    const paddingBottom = parseInt(style.paddingBottom) || 0;
    const boxExtras = borderTop + borderBottom + paddingTop + paddingBottom;
    const contentHeight = questionInput.scrollHeight - boxExtras;
    const lineHeight = 22; // approx for 16px font
    const minRows = 2;
    const maxRows = 7;
    // Compute rows required based on content height, clamped
    const neededRows = Math.ceil(contentHeight / lineHeight);
    const clamped = Math.min(maxRows, Math.max(minRows, neededRows));
    questionInput.rows = clamped;
    // Prevent jumpy growth for long single lines by restricting until wrap actually occurs
    // If no wrap (scrollWidth <= clientWidth), keep at least minRows
    const isWrapping = questionInput.scrollWidth > questionInput.clientWidth;
    if (!isWrapping) questionInput.rows = Math.min(questionInput.rows, minRows);
  }

  async function handleGenerateReport() {
    const user = window.__sb_get_user();
    const currentProject = window.__sb_get_current_project && window.__sb_get_current_project();
    if (!user || !currentProject) {
      alert('Please sign in and select a project');
      return;
    }
    // Determine selected/active file from files section; fallback to first
    const candidates = Array.from(document.querySelectorAll('#stored-file-items .pill'));
    let active = candidates.find(el => el.classList.contains('active'));
    if (!active && candidates.length) active = candidates[0];
    if (!active) { alert('Please upload and select a document first'); return; }
    const filename = active.textContent.trim();
    const instructions = (questionInput && questionInput.value || '').trim();
    showLoading('Generating report...');
    try {
      const form = new FormData();
      form.append('user_id', user.user_id);
      form.append('project_id', currentProject.project_id);
      form.append('filename', filename);
      form.append('outline_words', '200');
      form.append('report_words', '1200');
      form.append('instructions', instructions);
      const res = await fetch('/report', { method: 'POST', body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Report failed');
      // Append as assistant message
      appendMessage('assistant', data.report_markdown || 'No report');
      if (data.sources && data.sources.length) {
        appendSources(data.sources);
      }
    } catch (e) {
      alert(e.message || 'Failed to generate report');
    } finally {
      hideLoading();
    }
  }

  // Toggle active file pill selection
  document.addEventListener('click', (e) => {
    const tgt = e.target;
    if (tgt && tgt.classList && tgt.classList.contains('pill') && tgt.parentElement && tgt.parentElement.id === 'stored-file-items') {
      document.querySelectorAll('#stored-file-items .pill').forEach(el => el.classList.remove('active'));
      tgt.classList.add('active');
      // Enable link visually
      if (reportLink) reportLink.classList.add('active');
    }
  });

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
    
    // Render Markdown for assistant messages
    if (role === 'assistant') {
      try {
        // Check if marked library is available
        if (typeof marked !== 'undefined' && marked.parse) {
          const htmlContent = marked.parse(text);
          messageDiv.innerHTML = htmlContent;
        } else {
          console.warn('[SCRIPT] Marked library not available, using plain text');
          messageDiv.textContent = text;
        }
      } catch (e) {
        console.error('[SCRIPT] Markdown parsing failed:', e);
        // Fallback to plain text if Markdown parsing fails
        messageDiv.textContent = text;
      }
    } else {
      messageDiv.textContent = text;
    }
    
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
    const loadingSpan = button.querySelector('.btn-loading');
    const sendIcon = button.querySelector('.send-icon');
    
    if (isLoading) {
      if (loadingSpan) loadingSpan.style.display = 'inline-flex';
      if (sendIcon) sendIcon.style.display = 'none';
      button.disabled = true;
    } else {
      if (loadingSpan) loadingSpan.style.display = 'none';
      if (sendIcon) sendIcon.style.display = 'inline';
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
    console.log('[SCRIPT] checkUserAuth called');
    const user = window.__sb_get_user();
    console.log('[SCRIPT] User from localStorage:', user);
    if (user) {
      // Check if we have a current project
      const currentProject = window.__sb_get_current_project && window.__sb_get_current_project();
      console.log('[SCRIPT] Current project:', currentProject);
      if (currentProject) {
        console.log('[SCRIPT] Enabling chat for project:', currentProject.name);
        enableChat();
      } else {
        console.log('[SCRIPT] No current project, chat remains disabled');
      }
    } else {
      console.log('[SCRIPT] No user found, chat remains disabled');
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

  // Load stored files whenever project changes
  document.addEventListener('projectChanged', () => {
    loadStoredFiles();
  });

  // Expose to other scripts
  window.__sb_load_stored_files = loadStoredFiles;

  // Also attempt loading stored files after initial auth/project load
  window.addEventListener('load', () => {
    setTimeout(loadStoredFiles, 500);
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