// ────────────────────────────── static/auth.js ──────────────────────────────
(function() {
  const modal = document.getElementById('auth-modal');
  const openBtn = document.getElementById('open-auth');
  const closeBtn = document.getElementById('close-auth');
  const logoutBtn = document.getElementById('logout');
  const authStatus = document.getElementById('auth-status');
  const tabs = document.querySelectorAll('.tab');
  const tabLogin = document.getElementById('tab-login');
  const tabSignup = document.getElementById('tab-signup');
  const themeToggle = document.getElementById('theme-toggle');

  function setAuthUI(user) {
    if (user && user.user_id) {
      authStatus.textContent = `Signed in as ${user.email}`;
      logoutBtn.style.display = '';
      openBtn.style.display = 'none';
    } else {
      authStatus.textContent = 'Not signed in';
      logoutBtn.style.display = 'none';
      openBtn.style.display = '';
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
    setAuthUI(null);
  }

  // Initialize UI
  setAuthUI(getUser());

  // Theme
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

  openBtn.addEventListener('click', () => {
    modal.classList.remove('hidden');
    modal.setAttribute('aria-hidden', 'false');
  });
  closeBtn.addEventListener('click', () => {
    modal.classList.add('hidden');
    modal.setAttribute('aria-hidden', 'true');
  });
  logoutBtn.addEventListener('click', () => {
    clearUser();
    alert('You have been logged out.');
  });

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
    const fd = new FormData();
    fd.append('email', email);
    fd.append('password', password);
    const res = await fetch('/auth/login', { method: 'POST', body: fd });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(err.detail || 'Login failed');
      return;
    }
    const data = await res.json();
    setUser(data);
    modal.classList.add('hidden');
  });

  document.getElementById('signup-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const email = document.getElementById('signup-email').value.trim();
    const password = document.getElementById('signup-password').value;
    const fd = new FormData();
    fd.append('email', email);
    fd.append('password', password);
    const res = await fetch('/auth/signup', { method: 'POST', body: fd });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(err.detail || 'Signup failed');
      return;
    }
    const data = await res.json();
    setUser(data);
    modal.classList.add('hidden');
  });

  // Expose helper to other scripts
  window.__sb_get_user = getUser;
})();


