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
  const searchLink = document.getElementById('search-link');
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
    sendBtn.addEventListener('click', handleAsk);
    // Convert to textarea behavior: Enter submits, Shift+Enter for newline
    questionInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleAsk();
      }
    });
    questionInput.addEventListener('input', autoGrowTextarea);

    // Clear chat history
    const clearBtn = document.getElementById('clear-chat-btn');
    if (clearBtn) {
      clearBtn.addEventListener('click', async () => {
        const user = window.__sb_get_user();
        const currentProject = window.__sb_get_current_project && window.__sb_get_current_project();
        const currentSession = window.__sb_get_current_session && window.__sb_get_current_session();
        if (!user || !currentProject || !currentSession) {
          alert('Please select a session first');
          return;
        }
        if (!confirm('Clear chat history for this session?')) return;
        try {
          const res = await fetch(`/chat/history?user_id=${encodeURIComponent(user.user_id)}&project_id=${encodeURIComponent(currentProject.project_id)}&session_id=${encodeURIComponent(currentSession)}`, { method: 'DELETE' });
          if (res.ok) {
            document.getElementById('messages').innerHTML = '';
            // Also clear session-specific memory
            try {
              await fetch('/sessions/clear-memory', {
                method: 'POST',
                body: new FormData().append('user_id', user.user_id)
                  .append('project_id', currentProject.project_id)
                  .append('session_id', currentSession)
              });
            } catch (e) {
              console.warn('Failed to clear session memory:', e);
            }
          } else {
            alert('Failed to clear history');
          }
        } catch {}
      });
    }
    // Report link toggle
    if (reportLink) {
      reportLink.addEventListener('click', (e) => {
        e.preventDefault();
        toggleReportMode();
      });
    }
    // Search link toggle (enables web search augmentation)
    if (searchLink) {
      searchLink.addEventListener('click', (e) => {
        e.preventDefault();
        // Visual toggle; can be active concurrently with report mode
        searchLink.classList.toggle('active');
      });
    }
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
    questionInput.disabled = false;
    sendBtn.disabled = false;
    chatHint.style.display = 'none';
    autoGrowTextarea();
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

    // Get current session ID from session management
    const sessionId = window.__sb_get_current_session && window.__sb_get_current_session();
    if (!sessionId) {
      alert('Please select a session first');
      return;
    }

    // Add user message
    appendMessage('user', question);
    questionInput.value = '';
    autoGrowTextarea();

    // Save user message to chat history
    await saveChatMessage(user.user_id, currentProject.project_id, 'user', question, null, sessionId);
    
    // Add thinking message with dynamic status
    const thinkingMsg = appendMessage('thinking', 'Receiving request...');
    
    // Disable input during processing
    questionInput.disabled = true;
    sendBtn.disabled = true;
    showButtonLoading(sendBtn, true);
    
    // Start status polling
    const statusInterval = startStatusPolling(sessionId, thinkingMsg);

    try {
      // Branch: if report mode is active → call /report with textarea as instructions
      if (isReportModeActive()) {
        const filename = pickActiveFilename();
        if (!filename) throw new Error('Please select a document to generate a report');
        const form = new FormData();
        form.append('user_id', user.user_id);
        form.append('project_id', currentProject.project_id);
        form.append('filename', filename);
        form.append('outline_words', '200');
        form.append('report_words', '1200');
        form.append('instructions', question);
        form.append('session_id', sessionId);
        // If Search is toggled on, enable web augmentation for report
        const useWeb = searchLink && searchLink.classList.contains('active');
        if (useWeb) {
          form.append('use_web', '1');
          form.append('max_web', '20');
        }
        const response = await fetch('/report', { method: 'POST', body: form });
        const data = await response.json();
        if (response.ok) {
          thinkingMsg.remove();
          appendMessage('assistant', data.report_markdown || 'No report', true); // isReport = true
          if (data.sources && data.sources.length) appendSources(data.sources);
          // Save assistant report to chat history for persistence
          try { await saveChatMessage(user.user_id, currentProject.project_id, 'assistant', data.report_markdown || 'No report', null, sessionId); } catch {}
        } else {
          throw new Error(data.detail || 'Failed to generate report');
        }
      } else {
        const formData = new FormData();
        formData.append('user_id', user.user_id);
        formData.append('project_id', currentProject.project_id);
        formData.append('question', question);
        formData.append('k', '6');
        formData.append('session_id', sessionId);
        // If Search is toggled on, enable web augmentation
        const useWeb = searchLink && searchLink.classList.contains('active');
        if (useWeb) {
          formData.append('use_web', '1');
          formData.append('max_web', '30');
        }
        const response = await fetch('/chat', { method: 'POST', body: formData });
        const data = await response.json();
        if (response.ok) {
          thinkingMsg.remove();
          appendMessage('assistant', data.answer || 'No answer received');
          if (data.sources && data.sources.length > 0) {
            appendSources(data.sources);
          }
          
          // Handle session auto-naming if returned
          if (data.session_name && data.session_id) {
            // Update the session name in the UI immediately
            if (window.__sb_update_session_name) {
              window.__sb_update_session_name(data.session_id, data.session_name);
            }
          }
          
          await saveChatMessage(
            user.user_id,
            currentProject.project_id,
            'assistant',
            data.answer || 'No answer received',
            (data.sources && data.sources.length > 0) ? data.sources : null,
            sessionId
          );
        } else {
          throw new Error(data.detail || 'Failed to get answer');
        }
      }
    } catch (error) {
      thinkingMsg.remove();
      const errorMsg = `⚠️ Error: ${error.message}`;
      appendMessage('assistant', errorMsg);
      await saveChatMessage(user.user_id, currentProject.project_id, 'assistant', errorMsg, null, sessionId);
    } finally {
      // Stop status polling
      if (statusInterval) {
        clearInterval(statusInterval);
      }
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
      // Respect Search toggle when using quick report button
      const useWeb = searchLink && searchLink.classList.contains('active');
      if (useWeb) {
        form.append('use_web', '1');
        form.append('max_web', '20');
      }
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

  async function saveChatMessage(userId, projectId, role, content, sources = null, sessionId = null) {
    try {
      const formData = new FormData();
      formData.append('user_id', userId);
      formData.append('project_id', projectId);
      formData.append('role', role);
      formData.append('content', content);
      formData.append('timestamp', Date.now() / 1000);
      if (sources) {
        try { formData.append('sources', JSON.stringify(sources)); } catch {}
      }
      if (sessionId) {
        formData.append('session_id', sessionId);
      }
      
      await fetch('/chat/save', { method: 'POST', body: formData });
    } catch (error) {
      console.error('Failed to save chat message:', error);
    }
  }
  
  function renderAssistantMarkdown(container, markdown, isReport) {
    try {
      // Configure marked to keep code blocks for highlight.js
      const htmlContent = marked.parse(markdown);
      container.innerHTML = htmlContent;
      // Normalize heading numbering (H1/H2/H3) without double-numbering
      try { renumberHeadings(container); } catch {}
      // Render Mermaid if present
      renderMermaidInElement(container);
      // Add copy buttons to code blocks
      addCopyButtonsToCodeBlocks(container);
      // Syntax highlight code blocks
      try {
        container.querySelectorAll('pre code').forEach((block) => {
          if (window.hljs && window.hljs.highlightElement) {
            window.hljs.highlightElement(block);
          }
        });
      } catch {}
      // Add download PDF button for reports
      if (isReport) addDownloadPdfButton(container, markdown);
    } catch (e) {
      container.textContent = markdown;
    }
  }

  function renumberHeadings(root) {
    const h1s = Array.from(root.querySelectorAll('h1'));
    const h2s = Array.from(root.querySelectorAll('h2'));
    const h3s = Array.from(root.querySelectorAll('h3'));
    let s1 = 0;
    let s2 = 0;
    let s3 = 0;
    const headers = Array.from(root.querySelectorAll('h1, h2, h3'));
    headers.forEach(h => {
      const text = h.textContent.trim();
      // Strip any existing numeric prefix like "1. ", "1.2 ", "1.2.3 "
      const stripped = text.replace(/^\d+(?:\.\d+){0,2}\s+/, '');
      if (h.tagName === 'H1') {
        s1 += 1; s2 = 0; s3 = 0;
        h.textContent = `${s1}. ${stripped}`;
      } else if (h.tagName === 'H2') {
        if (s1 === 0) { s1 = 1; }
        s2 += 1; s3 = 0;
        h.textContent = `${s1}.${s2} ${stripped}`;
      } else if (h.tagName === 'H3') {
        if (s1 === 0) { s1 = 1; }
        if (s2 === 0) { s2 = 1; }
        s3 += 1;
        h.textContent = `${s1}.${s2}.${s3} ${stripped}`;
      }
    });
  }

  // Dynamically load Mermaid and render mermaid code blocks
  async function ensureMermaidLoaded() {
    if (window.mermaid && window.mermaid.initialize) return true;
    return new Promise((resolve) => {
      const existing = document.querySelector('script[data-sb-mermaid]');
      if (existing) { existing.addEventListener('load', () => resolve(true)); return; }
      const s = document.createElement('script');
      s.src = 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js';
      s.async = true;
      s.dataset.sbMermaid = '1';
      s.onload = () => {
        try {
          if (window.mermaid && window.mermaid.initialize) {
            window.mermaid.initialize({ startOnLoad: false, securityLevel: 'loose', theme: 'default' });
          }
        } catch {}
        resolve(true);
      };
      document.head.appendChild(s);
    });
  }

  async function renderMermaidInElement(el) {
    const mermaidBlocks = el.querySelectorAll('code.language-mermaid, pre code.language-mermaid');
    if (!mermaidBlocks.length) return;
    await ensureMermaidLoaded();
    const isV10 = !!(window.mermaid && window.mermaid.render && typeof window.mermaid.render === 'function');
    for (let idx = 0; idx < mermaidBlocks.length; idx++) {
      const codeBlock = mermaidBlocks[idx];
      const graph = codeBlock.textContent || '';
      const wrapper = document.createElement('div');
      const id = `mermaid-${Date.now()}-${idx}`;
      wrapper.className = 'mermaid';
      wrapper.id = id;
      const replaceTarget = codeBlock.parentElement && codeBlock.parentElement.tagName.toLowerCase() === 'pre' ? codeBlock.parentElement : codeBlock;
      replaceTarget.replaceWith(wrapper);
      try {
        if (isV10) {
          // Pass wrapper as container to avoid document.createElementNS undefined errors
          const out = await window.mermaid.render(id + '-svg', graph, wrapper);
          if (out && out.svg) {
            wrapper.innerHTML = out.svg;
            if (out.bindFunctions) { out.bindFunctions(wrapper); }
          }
        } else if (window.mermaid && window.mermaid.init) {
          // Legacy fallback
          wrapper.textContent = graph;
          window.mermaid.init(undefined, wrapper);
        }
      } catch (e) {
        console.warn('Mermaid render failed:', e);
        wrapper.textContent = graph;
      }
    }
  }

  // Expose markdown-aware appenders for use after refresh (projects.js)
  window.appendMessage = appendMessage;
  window.appendSources = appendSources;

  function addCopyButtonsToCodeBlocks(messageDiv) {
    const codeBlocks = messageDiv.querySelectorAll('pre code');
    codeBlocks.forEach((codeBlock, index) => {
      const pre = codeBlock.parentElement;
      if (!pre || pre.dataset.sbWrapped === '1') return;
      const isMermaid = codeBlock.classList.contains('language-mermaid');
      // Do not wrap mermaid blocks; they will be replaced by SVGs
      if (isMermaid) return;
      const language = codeBlock.className.match(/language-(\w+)/)?.[1] || 'code';

      // Ensure syntax highlighting is applied before moving the node
      try {
        if (window.hljs && window.hljs.highlightElement) {
          window.hljs.highlightElement(codeBlock);
        }
      } catch {}

      // Create wrapper
      const wrapper = document.createElement('div');
      wrapper.className = 'code-block-wrapper';

      // Create header with language and copy button
      const header = document.createElement('div');
      header.className = 'code-block-header';
      header.innerHTML = `
        <span class="code-block-language">${language}</span>
        <button class="copy-code-btn" data-code-index="${index}">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
          </svg>
          Copy
        </button>
      `;

      // Create content wrapper and move the original <pre><code> inside (preserves highlighting)
      const content = document.createElement('div');
      content.className = 'code-block-content';
      pre.dataset.sbWrapped = '1';
      content.appendChild(pre);

      // Assemble wrapper
      wrapper.appendChild(header);
      wrapper.appendChild(content);

      // Insert wrapper where the original pre was
      const parent = content.parentNode || messageDiv; // safety
      if (pre.parentNode !== content) {
        // pre has been moved into content; parent should be original parent of pre
        const insertionParent = parent === messageDiv ? messageDiv : pre.parentNode;
      }
      // Replace in DOM: pre has been moved; place wrapper where pre used to be
      const originalParent = content.parentNode ? content.parentNode : messageDiv;
      // If pre had a previous sibling, insert wrapper before it; else append
      const ref = wrapper.querySelector('.code-block-content pre');
      const oldParent = wrapper.querySelector('.code-block-content pre').parentNode;
      // oldParent is content; we need to place wrapper at the original location of pre
      const originalPlaceholder = document.createComment('code-block-wrapper');
      const preOriginalParent = wrapper.querySelector('.code-block-content pre').parentElement; // content
      // Since we already moved pre, we can't auto-place; use previousSibling stored before move
      // Simpler: insert wrapper after content creation at the position of 'content' parent
      // If messageDiv contains multiple elements, just append wrapper now
      messageDiv.appendChild(wrapper);

      // Add click handler for copy button
      const copyBtn = wrapper.querySelector('.copy-code-btn');
      copyBtn.addEventListener('click', () => copyCodeToClipboard(codeBlock.textContent, copyBtn));
    });
  }

  function copyCodeToClipboard(code, button) {
    navigator.clipboard.writeText(code).then(() => {
      const originalText = button.innerHTML;
      button.innerHTML = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="20,6 9,17 4,12"></polyline>
        </svg>
        Copied!
      `;
      button.classList.add('copied');
      
      setTimeout(() => {
        button.innerHTML = originalText;
        button.classList.remove('copied');
      }, 2000);
    }).catch(err => {
      console.error('Failed to copy code:', err);
      // Fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = code;
      document.body.appendChild(textArea);
      textArea.select();
      try {
        document.execCommand('copy');
        button.innerHTML = `
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="20,6 9,17 4,12"></polyline>
          </svg>
          Copied!
        `;
        button.classList.add('copied');
        setTimeout(() => {
          button.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
            </svg>
            Copy
          `;
          button.classList.remove('copied');
        }, 2000);
      } catch (fallbackErr) {
        console.error('Fallback copy failed:', fallbackErr);
      }
      document.body.removeChild(textArea);
    });
  }

  function addDownloadPdfButton(messageDiv, reportContent) {
    const downloadBtn = document.createElement('button');
    downloadBtn.className = 'download-pdf-btn';
    downloadBtn.innerHTML = `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
        <polyline points="7,10 12,15 17,10"></polyline>
        <line x1="12" y1="15" x2="12" y2="3"></line>
      </svg>
      Download PDF
    `;
    
    downloadBtn.addEventListener('click', () => downloadReportAsPdf(reportContent, downloadBtn));
    messageDiv.appendChild(downloadBtn);
  }

  async function downloadReportAsPdf(reportContent, button) {
    const user = window.__sb_get_user();
    const currentProject = window.__sb_get_current_project && window.__sb_get_current_project();
    
    if (!user || !currentProject) {
      alert('Please sign in and select a project');
      return;
    }

    button.disabled = true;
    button.innerHTML = `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"></circle>
        <polyline points="12,6 12,12 16,14"></polyline>
      </svg>
      Generating PDF...
    `;

    try {
      // Find sources from the current message or recent sources
      const sources = findCurrentSources();
      
      const formData = new FormData();
      formData.append('user_id', user.user_id);
      formData.append('project_id', currentProject.project_id);
      formData.append('report_content', reportContent);
      formData.append('sources', JSON.stringify(sources));

      const response = await fetch('/report/pdf', {
        method: 'POST',
        body: formData
      });

      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `report-${new Date().toISOString().split('T')[0]}.pdf`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        
        button.innerHTML = `
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="20,6 9,17 4,12"></polyline>
          </svg>
          Downloaded!
        `;
        setTimeout(() => {
          button.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
              <polyline points="7,10 12,15 17,10"></polyline>
              <line x1="12" y1="15" x2="12" y2="3"></line>
            </svg>
            Download PDF
          `;
          button.disabled = false;
        }, 2000);
      } else {
        throw new Error('Failed to generate PDF');
      }
    } catch (error) {
      console.error('PDF generation failed:', error);
      alert('Failed to generate PDF. Please try again.');
      button.innerHTML = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
          <polyline points="7,10 12,15 17,10"></polyline>
          <line x1="12" y1="15" x2="12" y2="3"></line>
        </svg>
        Download PDF
      `;
      button.disabled = false;
    }
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
    
    // Store sources for PDF generation
    window.__sb_current_sources = sources;
    
    requestAnimationFrame(() => {
      sourcesDiv.scrollIntoView({ behavior: 'smooth', block: 'end' });
    });
  }

  function findCurrentSources() {
    // Try to get sources from the current message context
    if (window.__sb_current_sources) {
      return window.__sb_current_sources;
    }
    
    // Fallback: look for sources in the last assistant message
    const lastAssistantMsg = Array.from(messages.children).reverse().find(msg => 
      msg.classList.contains('msg') && msg.classList.contains('assistant')
    );
    
    if (lastAssistantMsg) {
      const sourcesDiv = lastAssistantMsg.nextElementSibling;
      if (sourcesDiv && sourcesDiv.classList.contains('sources')) {
        // Extract sources from the DOM (this is a fallback)
        const pills = sourcesDiv.querySelectorAll('.pill');
        const sources = Array.from(pills).map(pill => {
          const text = pill.textContent;
          const parts = text.split(' • ');
          return {
            filename: parts[0] || 'Unknown',
            topic_name: parts[1] || '',
            score: 0.0
          };
        });
        return sources;
      }
    }
    
    return [];
  }

  function showButtonLoading(button, isLoading) {
    const textSpan = button.querySelector('.btn-text');
    const loadingSpan = button.querySelector('.btn-loading');
    
    // Handle buttons with only loading state (like send button)
    if (!textSpan && loadingSpan) {
      if (isLoading) {
        loadingSpan.style.display = 'inline-flex';
        button.disabled = true;
      } else {
        loadingSpan.style.display = 'none';
        button.disabled = false;
      }
      return;
    }
    
    // Handle buttons with both text and loading states (like upload button)
    if (textSpan && loadingSpan) {
      if (isLoading) {
        textSpan.style.display = 'none';
        loadingSpan.style.display = 'inline-flex';
        button.disabled = true;
      } else {
        textSpan.style.display = 'inline';
        loadingSpan.style.display = 'none';
        button.disabled = false;
      }
      return;
    }
    
    // Fallback for buttons without proper loading structure
    if (isLoading) {
      button.disabled = true;
    } else {
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
  window.__sb_enable_chat = enableChat;

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

  // Status polling function for real-time updates
  function startStatusPolling(sessionId, thinkingMsg) {
    const isReportMode = isReportModeActive();
    const statusEndpoint = isReportMode ? `/report/status/${sessionId}` : `/chat/status/${sessionId}`;
    
    const interval = setInterval(async () => {
      try {
        const response = await fetch(statusEndpoint);
        if (response.ok) {
          const status = await response.json();
          updateThinkingMessage(thinkingMsg, status.message, status.progress);
          
          // Stop polling when complete or error
          if (status.status === 'complete' || status.status === 'error') {
            clearInterval(interval);
          }
        }
      } catch (error) {
        console.warn('Status polling failed:', error);
      }
    }, 500); // Poll every 500ms
    
    return interval;
  }

  function updateThinkingMessage(thinkingMsg, message, progress) {
    if (thinkingMsg && thinkingMsg.querySelector) {
      const progressBar = thinkingMsg.querySelector('.progress-bar');
      const statusText = thinkingMsg.querySelector('.status-text');
      
      if (statusText) {
        statusText.textContent = message;
      }
      
      if (progressBar && progress !== undefined) {
        progressBar.style.width = `${progress}%`;
      }
    }
  }

  // Enhanced thinking message with progress bar
  function appendMessage(role, text, isReport = false) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `msg ${role}`;
    if (role === 'thinking') {
      messageDiv.innerHTML = `
        <div class="thinking-container">
          <div class="status-text">${text}</div>
          <div class="progress-container">
            <div class="progress-bar" style="width: 0%"></div>
          </div>
        </div>
      `;
    } else if (role === 'assistant') {
      renderAssistantMarkdown(messageDiv, text, isReport);
    } else {
      messageDiv.textContent = text;
    }
    messages.appendChild(messageDiv);
    requestAnimationFrame(() => {
      messageDiv.scrollIntoView({ behavior: 'smooth', block: 'end' });
    });
    return messageDiv;
  }
})();