// ────────────────────────────── static/quiz.js ──────────────────────────────
(function() {
  // Quiz state
  let currentQuiz = null;
  let currentQuestionIndex = 0;
  let quizAnswers = {};
  let quizTimer = null;
  let timeRemaining = 0;
  let quizSetupStep = 1;

  // DOM elements
  const quizLink = document.getElementById('quiz-link');
  const quizSetupModal = document.getElementById('quiz-setup-modal');
  const quizModal = document.getElementById('quiz-modal');
  const quizResultsModal = document.getElementById('quiz-results-modal');
  const quizSetupForm = document.getElementById('quiz-setup-form');
  const quizQuestionsInput = document.getElementById('quiz-questions-input');
  const quizTimeLimit = document.getElementById('quiz-time-limit');
  const quizDocumentList = document.getElementById('quiz-document-list');
  const quizPrevStep = document.getElementById('quiz-prev-step');
  const quizNextStep = document.getElementById('quiz-next-step');
  const quizCancel = document.getElementById('quiz-cancel');
  const quizSubmit = document.getElementById('quiz-submit');
  const quizTimerElement = document.getElementById('quiz-timer');
  const quizProgressFill = document.getElementById('quiz-progress-fill');
  const quizProgressText = document.getElementById('quiz-progress-text');
  const quizQuestion = document.getElementById('quiz-question');
  const quizAnswers = document.getElementById('quiz-answers');
  const quizPrev = document.getElementById('quiz-prev');
  const quizNext = document.getElementById('quiz-next');
  const quizSubmitBtn = document.getElementById('quiz-submit');
  const quizResultsContent = document.getElementById('quiz-results-content');
  const quizResultsClose = document.getElementById('quiz-results-close');

  // Initialize
  init();

  function init() {
    setupEventListeners();
  }

  function setupEventListeners() {
    // Quiz link
    if (quizLink) {
      quizLink.addEventListener('click', (e) => {
        e.preventDefault();
        openQuizSetup();
      });
    }

    // Quiz setup form
    if (quizSetupForm) {
      quizSetupForm.addEventListener('submit', handleQuizSetupSubmit);
    }

    // Quiz setup navigation
    if (quizNextStep) {
      quizNextStep.addEventListener('click', nextQuizStep);
    }
    if (quizPrevStep) {
      quizPrevStep.addEventListener('click', prevQuizStep);
    }
    if (quizCancel) {
      quizCancel.addEventListener('click', closeQuizSetup);
    }

    // Quiz navigation
    if (quizPrev) {
      quizPrev.addEventListener('click', prevQuestion);
    }
    if (quizNext) {
      quizNext.addEventListener('click', nextQuestion);
    }
    if (quizSubmitBtn) {
      quizSubmitBtn.addEventListener('click', submitQuiz);
    }

    // Quiz results
    if (quizResultsClose) {
      quizResultsClose.addEventListener('click', closeQuizResults);
    }

    // Close modals on outside click
    document.addEventListener('click', (e) => {
      if (e.target.classList.contains('modal')) {
        closeAllQuizModals();
      }
    });
  }

  async function openQuizSetup() {
    const user = window.__sb_get_user();
    if (!user) {
      alert('Please sign in to create a quiz');
      window.__sb_show_auth_modal();
      return;
    }

    const currentProject = window.__sb_get_current_project && window.__sb_get_current_project();
    if (!currentProject) {
      alert('Please select a project first');
      return;
    }

    // Load available documents
    await loadQuizDocuments();
    
    // Reset form
    quizSetupStep = 1;
    updateQuizSetupStep();
    
    // Show modal
    quizSetupModal.classList.remove('hidden');
  }

  async function loadQuizDocuments() {
    const user = window.__sb_get_user();
    const currentProject = window.__sb_get_current_project && window.__sb_get_current_project();
    
    if (!user || !currentProject) return;

    try {
      const res = await fetch(`/files?user_id=${encodeURIComponent(user.user_id)}&project_id=${encodeURIComponent(currentProject.project_id)}`);
      if (!res.ok) return;
      
      const data = await res.json();
      const files = data.files || [];
      
      // Clear existing documents
      quizDocumentList.innerHTML = '';
      
      if (files.length === 0) {
        quizDocumentList.innerHTML = '<div class="muted">No documents available. Please upload documents first.</div>';
        return;
      }

      // Create document checkboxes
      files.forEach((file, index) => {
        const item = document.createElement('div');
        item.className = 'document-checkbox-item';
        item.innerHTML = `
          <input type="checkbox" id="quiz-doc-${index}" value="${file.filename}" checked>
          <label for="quiz-doc-${index}">${file.filename}</label>
        `;
        quizDocumentList.appendChild(item);
      });
    } catch (error) {
      console.error('Failed to load documents:', error);
      quizDocumentList.innerHTML = '<div class="muted">Failed to load documents.</div>';
    }
  }

  function updateQuizSetupStep() {
    // Hide all steps
    document.querySelectorAll('.quiz-step').forEach(step => {
      step.style.display = 'none';
    });

    // Show current step
    const currentStep = document.getElementById(`quiz-step-${quizSetupStep}`);
    if (currentStep) {
      currentStep.style.display = 'block';
    }

    // Update navigation buttons
    quizPrevStep.style.display = quizSetupStep > 1 ? 'inline-flex' : 'none';
    quizNextStep.style.display = quizSetupStep < 3 ? 'inline-flex' : 'none';
    quizSubmit.style.display = quizSetupStep === 3 ? 'inline-flex' : 'none';
  }

  function nextQuizStep() {
    if (quizSetupStep < 3) {
      quizSetupStep++;
      updateQuizSetupStep();
    }
  }

  function prevQuizStep() {
    if (quizSetupStep > 1) {
      quizSetupStep--;
      updateQuizSetupStep();
    }
  }

  function closeQuizSetup() {
    quizSetupModal.classList.add('hidden');
    quizSetupStep = 1;
    updateQuizSetupStep();
  }

  async function handleQuizSetupSubmit(e) {
    e.preventDefault();
    
    const user = window.__sb_get_user();
    const currentProject = window.__sb_get_current_project && window.__sb_get_current_project();
    
    if (!user || !currentProject) {
      alert('Please sign in and select a project');
      return;
    }

    // Get form data
    const questionsInput = quizQuestionsInput.value.trim();
    const timeLimit = parseInt(quizTimeLimit.value) || 0;
    
    // Get selected documents
    const selectedDocs = Array.from(quizDocumentList.querySelectorAll('input[type="checkbox"]:checked'))
      .map(input => input.value);

    if (selectedDocs.length === 0) {
      alert('Please select at least one document');
      return;
    }

    if (!questionsInput) {
      alert('Please specify how many questions you want');
      return;
    }

    // Show loading
    showLoading('Creating quiz...');

    try {
      // Create quiz
      const formData = new FormData();
      formData.append('user_id', user.user_id);
      formData.append('project_id', currentProject.project_id);
      formData.append('questions_input', questionsInput);
      formData.append('time_limit', timeLimit.toString());
      formData.append('documents', JSON.stringify(selectedDocs));

      const response = await fetch('/quiz/create', {
        method: 'POST',
        body: formData
      });

      const data = await response.json();

      if (response.ok) {
        hideLoading();
        closeQuizSetup();
        
        // Start quiz
        currentQuiz = data.quiz;
        currentQuestionIndex = 0;
        quizAnswers = {};
        timeRemaining = timeLimit * 60; // Convert to seconds
        
        startQuiz();
      } else {
        hideLoading();
        alert(data.detail || 'Failed to create quiz');
      }
    } catch (error) {
      hideLoading();
      console.error('Quiz creation failed:', error);
      alert('Failed to create quiz. Please try again.');
    }
  }

  function startQuiz() {
    // Show quiz modal
    quizModal.classList.remove('hidden');
    
    // Start timer if time limit is set
    if (timeRemaining > 0) {
      startQuizTimer();
    } else {
      quizTimerElement.textContent = 'No time limit';
    }
    
    // Show first question
    showQuestion(0);
  }

  function startQuizTimer() {
    updateTimerDisplay();
    
    quizTimer = setInterval(() => {
      timeRemaining--;
      updateTimerDisplay();
      
      if (timeRemaining <= 0) {
        clearInterval(quizTimer);
        timeUp();
      }
    }, 1000);
  }

  function updateTimerDisplay() {
    const minutes = Math.floor(timeRemaining / 60);
    const seconds = timeRemaining % 60;
    const timeString = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    
    quizTimerElement.textContent = `Time: ${timeString}`;
    
    // Add warning classes
    quizTimerElement.classList.remove('warning', 'danger');
    if (timeRemaining <= 60) {
      quizTimerElement.classList.add('danger');
    } else if (timeRemaining <= 300) { // 5 minutes
      quizTimerElement.classList.add('warning');
    }
  }

  function timeUp() {
    alert('Time Up!');
    submitQuiz();
  }

  function showQuestion(index) {
    if (!currentQuiz || !currentQuiz.questions || index >= currentQuiz.questions.length) {
      return;
    }

    const question = currentQuiz.questions[index];
    currentQuestionIndex = index;

    // Update progress
    const progress = ((index + 1) / currentQuiz.questions.length) * 100;
    quizProgressFill.style.width = `${progress}%`;
    quizProgressText.textContent = `Question ${index + 1} of ${currentQuiz.questions.length}`;

    // Show question
    quizQuestion.innerHTML = `
      <h3>Question ${index + 1}</h3>
      <p>${question.question}</p>
    `;

    // Show answers
    if (question.type === 'mcq') {
      showMCQAnswers(question);
    } else if (question.type === 'self_reflect') {
      showSelfReflectAnswer(question);
    }

    // Update navigation
    quizPrev.disabled = index === 0;
    quizNext.style.display = index < currentQuiz.questions.length - 1 ? 'inline-flex' : 'none';
    quizSubmitBtn.style.display = index === currentQuiz.questions.length - 1 ? 'inline-flex' : 'none';
  }

  function showMCQAnswers(question) {
    quizAnswers.innerHTML = '';
    
    question.options.forEach((option, index) => {
      const optionDiv = document.createElement('div');
      optionDiv.className = 'quiz-answer-option';
      optionDiv.innerHTML = `
        <input type="radio" name="question-${currentQuestionIndex}" value="${index}" id="option-${currentQuestionIndex}-${index}">
        <label for="option-${currentQuestionIndex}-${index}">${option}</label>
      `;
      
      // Check if already answered
      if (quizAnswers[currentQuestionIndex] !== undefined) {
        const radio = optionDiv.querySelector('input[type="radio"]');
        radio.checked = quizAnswers[currentQuestionIndex] === index;
        if (radio.checked) {
          optionDiv.classList.add('selected');
        }
      }
      
      // Add click handler
      optionDiv.addEventListener('click', () => {
        // Remove selection from other options
        quizAnswers.querySelectorAll('.quiz-answer-option').forEach(opt => {
          opt.classList.remove('selected');
        });
        
        // Select this option
        optionDiv.classList.add('selected');
        const radio = optionDiv.querySelector('input[type="radio"]');
        radio.checked = true;
        
        // Save answer
        quizAnswers[currentQuestionIndex] = index;
      });
      
      quizAnswers.appendChild(optionDiv);
    });
  }

  function showSelfReflectAnswer(question) {
    quizAnswers.innerHTML = `
      <textarea class="quiz-text-answer" id="self-reflect-${currentQuestionIndex}" placeholder="Enter your answer here...">${quizAnswers[currentQuestionIndex] || ''}</textarea>
    `;
    
    const textarea = quizAnswers.querySelector('textarea');
    textarea.addEventListener('input', (e) => {
      quizAnswers[currentQuestionIndex] = e.target.value;
    });
  }

  function prevQuestion() {
    if (currentQuestionIndex > 0) {
      showQuestion(currentQuestionIndex - 1);
    }
  }

  function nextQuestion() {
    if (currentQuestionIndex < currentQuiz.questions.length - 1) {
      showQuestion(currentQuestionIndex + 1);
    }
  }

  async function submitQuiz() {
    if (quizTimer) {
      clearInterval(quizTimer);
    }

    // Show loading
    showLoading('Submitting quiz...');

    try {
      const user = window.__sb_get_user();
      const currentProject = window.__sb_get_current_project && window.__sb_get_current_project();

      const formData = new FormData();
      formData.append('user_id', user.user_id);
      formData.append('project_id', currentProject.project_id);
      formData.append('quiz_id', currentQuiz.quiz_id);
      formData.append('answers', JSON.stringify(quizAnswers));

      const response = await fetch('/quiz/submit', {
        method: 'POST',
        body: formData
      });

      const data = await response.json();

      if (response.ok) {
        hideLoading();
        closeQuizModal();
        showQuizResults(data.results);
      } else {
        hideLoading();
        alert(data.detail || 'Failed to submit quiz');
      }
    } catch (error) {
      hideLoading();
      console.error('Quiz submission failed:', error);
      alert('Failed to submit quiz. Please try again.');
    }
  }

  function showQuizResults(results) {
    // Show results summary
    const totalQuestions = results.questions.length;
    const correctAnswers = results.questions.filter(q => q.status === 'correct').length;
    const partialAnswers = results.questions.filter(q => q.status === 'partial').length;
    const incorrectAnswers = results.questions.filter(q => q.status === 'incorrect').length;
    const score = Math.round((correctAnswers + partialAnswers * 0.5) / totalQuestions * 100);

    quizResultsContent.innerHTML = `
      <div class="quiz-result-summary">
        <div class="quiz-result-stat">
          <div class="quiz-result-stat-value">${score}%</div>
          <div class="quiz-result-stat-label">Score</div>
        </div>
        <div class="quiz-result-stat">
          <div class="quiz-result-stat-value">${correctAnswers}</div>
          <div class="quiz-result-stat-label">Correct</div>
        </div>
        <div class="quiz-result-stat">
          <div class="quiz-result-stat-value">${partialAnswers}</div>
          <div class="quiz-result-stat-label">Partial</div>
        </div>
        <div class="quiz-result-stat">
          <div class="quiz-result-stat-value">${incorrectAnswers}</div>
          <div class="quiz-result-stat-label">Incorrect</div>
        </div>
      </div>
      
      <div class="quiz-result-questions">
        ${results.questions.map((question, index) => `
          <div class="quiz-result-question">
            <div class="quiz-result-question-header">
              <div class="quiz-result-question-title">Question ${index + 1}</div>
              <div class="quiz-result-question-status ${question.status}">${question.status}</div>
            </div>
            <div class="quiz-result-question-text">${question.question}</div>
            
            ${question.type === 'mcq' ? `
              <div class="quiz-result-answer">
                <div class="quiz-result-answer-label">Your Answer:</div>
                <div class="quiz-result-answer-content">${question.options[question.user_answer] || 'No answer'}</div>
              </div>
              <div class="quiz-result-answer">
                <div class="quiz-result-answer-label">Correct Answer:</div>
                <div class="quiz-result-answer-content">${question.options[question.correct_answer]}</div>
              </div>
            ` : `
              <div class="quiz-result-answer">
                <div class="quiz-result-answer-label">Your Answer:</div>
                <div class="quiz-result-answer-content">${question.user_answer || 'No answer'}</div>
              </div>
            `}
            
            ${question.explanation ? `
              <div class="quiz-result-explanation">
                <strong>Explanation:</strong> ${question.explanation}
              </div>
            ` : ''}
          </div>
        `).join('')}
      </div>
    `;

    quizResultsModal.classList.remove('hidden');
  }

  function closeQuizModal() {
    quizModal.classList.add('hidden');
  }

  function closeQuizResults() {
    quizResultsModal.classList.add('hidden');
  }

  function closeAllQuizModals() {
    closeQuizSetup();
    closeQuizModal();
    closeQuizResults();
  }

  function showLoading(message = 'Loading...') {
    const loadingOverlay = document.getElementById('loading-overlay');
    const loadingMessage = document.getElementById('loading-message');
    
    if (loadingOverlay && loadingMessage) {
      loadingMessage.textContent = message;
      loadingOverlay.classList.remove('hidden');
    }
  }

  function hideLoading() {
    const loadingOverlay = document.getElementById('loading-overlay');
    if (loadingOverlay) {
      loadingOverlay.classList.add('hidden');
    }
  }

  // Expose functions globally
  window.__sb_open_quiz_setup = openQuizSetup;
  window.__sb_close_quiz_setup = closeQuizSetup;
})();
