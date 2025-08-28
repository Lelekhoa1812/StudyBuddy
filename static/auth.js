// ────────────────────────────── static/auth.js ──────────────────────────────
(function() {
  const modal = document.getElementById('auth-modal');
  const logoutBtn = document.getElementById('logout');
  const userInfo = document.getElementById('user-info');
  const userEmail = document.getElementById('user-email');
  const themeToggle = document.getElementById('theme-toggle');
  const tabs = document.querySelectorAll('.tab');
  const tabLogin = document.getElementById('tab-login');
  const tabSignup = document.getElementById('tab-signup');
  const uploadSection = document.getElementById('upload-section');
  const chatSection = document.getElementById('chat-section');

  function setAuthUI(user) {
    if (user && user.user_id) {
      userInfo.style.display = 'flex';
      userEmail.textContent = user.email;
      // Enable app sections
      uploadSection.style.display = 'block';
      chatSection.style.display = 'block';
      // Hide modal if it was open
      modal.classList.add('hidden');
      
      // Trigger project loading after successful auth
      if (window.__sb_load_projects) {
        window.__sb_load_projects();
      }
    } else {
      userInfo.style.display = 'none';
      // Disable app sections for unauthenticated users
      uploadSection.style.display = 'none';
      chatSection.style.display = 'none';
      // Show auth modal
      showAuthModal();
    }
  }

  function getUser() {
    try {
      return JSON.parse(localStorage.getItem('sb_user')) || null;
    } catch { return null; }
  }

  function setUser(u) {
    localStorage.setItem('sb_user', JSON.stringify(u));
    setAuthUI(u);
  }

  function clearUser() {
    localStorage.removeItem('sb_user');
    localStorage.removeItem('sb_current_project');
    setAuthUI(null);
  }

  function showAuthModal() {
    modal.classList.remove('hidden');
    modal.setAttribute('aria-hidden', 'false');
  }

  function hideAuthModal() {
    modal.classList.add('hidden');
    modal.setAttribute('aria-hidden', 'true');
  }

  // Initialize UI and check auth status
  (function init() {
    const user = getUser();
    if (!user) {
      // No user found, show modal immediately
      showAuthModal();
    } else {
      setAuthUI(user);
    }
  })();

  // Theme management
  (function initTheme() {
    const saved = localStorage.getItem('sb_theme');
    if (saved === 'light') document.documentElement.classList.add('light');
    themeToggle.textContent = document.documentElement.classList.contains('light') ? '☀️' : '🌙';
  })();

  themeToggle.addEventListener('click', () => {
    document.documentElement.classList.toggle('light');
    const isLight = document.documentElement.classList.contains('light');
    localStorage.setItem('sb_theme', isLight ? 'light' : 'dark');
    themeToggle.textContent = isLight ? '☀️' : '🌙';
  });

  // Logout
  logoutBtn.addEventListener('click', () => {
    clearUser();
    showAuthModal();
  });

  // Tab switching
  tabs.forEach(tab => tab.addEventListener('click', () => {
    tabs.forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    const target = tab.dataset.tab;
    if (target === 'login') {
      tabLogin.classList.remove('hidden');
      tabSignup.classList.add('hidden');
    } else {
      tabSignup.classList.remove('hidden');
      tabLogin.classList.add('hidden');
    }
  }));

  // Forms
  document.getElementById('login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const email = document.getElementById('login-email').value.trim();
    const password = document.getElementById('login-password').value;
    
    if (!email || !password) {
      alert('Please fill in all fields');
      return;
    }

    const fd = new FormData();
    fd.append('email', email);
    fd.append('password', password);
    
    try {
      const res = await fetch('/auth/login', { method: 'POST', body: fd });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        alert(err.detail || 'Login failed');
        return;
      }
      const data = await res.json();
      setUser(data);
      hideAuthModal();
    } catch (error) {
      alert('Network error. Please try again.');
    }
  });

  document.getElementById('signup-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const email = document.getElementById('signup-email').value.trim();
    const password = document.getElementById('signup-password').value;
    
    if (!email || !password) {
      alert('Please fill in all fields');
      return;
    }

    if (password.length < 8) {
      alert('Password must be at least 8 characters long');
      return;
    }

    const fd = new FormData();
    fd.append('email', email);
    fd.append('password', password);
    
    try {
      const res = await fetch('/auth/signup', { method: 'POST', body: fd });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        alert(err.detail || 'Signup failed');
        return;
      }
      const data = await res.json();
      setUser(data);
      hideAuthModal();
    } catch (error) {
      alert('Network error. Please try again.');
    }
  });

  // Expose helper to other scripts
  window.__sb_get_user = getUser;
  window.__sb_show_auth_modal = showAuthModal;
})();


