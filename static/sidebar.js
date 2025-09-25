// ────────────────────────────── static/sidebar.js ──────────────────────────────
(function() {
  // DOM elements
  const sidebar = document.getElementById('sidebar');
  const sidebarToggle = document.getElementById('sidebar-toggle');
  const sidebarOverlay = document.getElementById('sidebar-overlay');
  const mainContent = document.querySelector('.main-content');
  const pageTitle = document.getElementById('page-title');
  const menuItems = document.querySelectorAll('.menu-item');

  // State
  let isSidebarOpen = true;
  let currentSection = 'projects';

  // Initialize
  init();

  function init() {
    setupEventListeners();
    updatePageTitle();
    
    // Check if we should start with collapsed sidebar on mobile
    if (window.innerWidth <= 1024) {
      collapseSidebar();
    }
  }

  function setupEventListeners() {
    // Sidebar toggle
    sidebarToggle.addEventListener('click', toggleSidebar);
    
    // Menu navigation
    menuItems.forEach(item => {
      item.addEventListener('click', (e) => {
        e.preventDefault();
        const section = item.dataset.section;
        navigateToSection(section);
      });
    });
    
    // Close sidebar when clicking overlay on mobile
    if (sidebarOverlay) {
      sidebarOverlay.addEventListener('click', () => {
        if (window.innerWidth <= 1024 && isSidebarOpen) {
          collapseSidebar();
        }
      });
    }
    
    // Close sidebar when clicking outside on mobile
    document.addEventListener('click', (e) => {
      if (window.innerWidth <= 1024 && isSidebarOpen) {
        if (!sidebar.contains(e.target) && !sidebarToggle.contains(e.target)) {
          collapseSidebar();
        }
      }
    });
    
    // Handle window resize
    window.addEventListener('resize', handleResize);
  }

  function toggleSidebar() {
    if (isSidebarOpen) {
      collapseSidebar();
    } else {
      expandSidebar();
    }
  }

  function expandSidebar() {
    sidebar.classList.remove('collapsed');
    // On mobile, use the 'open' class to slide in (as defined in CSS @media <=1024px)
    sidebar.classList.add('open');
    mainContent.classList.remove('sidebar-collapsed');
    isSidebarOpen = true;
    
    // Show overlay on mobile
    if (sidebarOverlay && window.innerWidth <= 1024) {
      sidebarOverlay.classList.add('active');
    }
    
    // Update hamburger icon to close icon
    updateHamburgerIcon();
  }

  function collapseSidebar() {
    sidebar.classList.add('collapsed');
    // On mobile, remove the 'open' class to hide
    sidebar.classList.remove('open');
    mainContent.classList.add('sidebar-collapsed');
    isSidebarOpen = false;
    
    // Hide overlay on mobile
    if (sidebarOverlay && window.innerWidth <= 1024) {
      sidebarOverlay.classList.remove('active');
    }
    
    // Update hamburger icon to menu icon
    updateHamburgerIcon();
  }

  function updateHamburgerIcon() {
    const svg = sidebarToggle.querySelector('svg');
    if (isSidebarOpen) {
      // Show close icon (X)
      svg.innerHTML = `
        <line x1="18" y1="6" x2="6" y2="18"/>
        <line x1="6" y1="6" x2="18" y2="18"/>
      `;
    } else {
      // Show hamburger icon (3 lines)
      svg.innerHTML = `
        <line x1="3" y1="6" x2="21" y2="6"/>
        <line x1="3" y1="12" x2="21" y2="12"/>
        <line x1="3" y1="18" x2="21" y2="18"/>
      `;
    }
  }

  function navigateToSection(section) {
    // Update active menu item
    menuItems.forEach(item => {
      item.classList.remove('active');
      if (item.dataset.section === section) {
        item.classList.add('active');
      }
    });
    
    currentSection = section;
    updatePageTitle();
    
    // Handle section-specific actions
    switch (section) {
      case 'projects':
        // Projects section shows upload by default, but keep chat visible too
        showSection('upload');
        // Also show chat section when in projects view
        const chat = document.getElementById('chat-section');
        if (chat) chat.style.display = 'block';
        break;
      case 'files':
        showSection('files');
        if (window.__sb_show_files_section) {
          window.__sb_show_files_section();
        }
        break;
      case 'chat':
        showSection('chat');
        break;
      case 'analytics':
        showSection('analytics');
        if (window.__sb_load_analytics) {
          window.__sb_load_analytics();
        }
        break;
      case 'settings':
        // Could show user settings or preferences
        break;
    }
    
    // Close sidebar on mobile after navigation
    if (window.innerWidth <= 1024) {
      collapseSidebar();
    }
  }

  function showSection(name) {
    const upload = document.getElementById('upload-section');
    const chat = document.getElementById('chat-section');
    const files = document.getElementById('files-section');
    const analytics = document.getElementById('analytics-section');
    
    if (!upload || !chat || !files) return;
    
    // Hide all sections first
    upload.style.display = 'none';
    chat.style.display = 'none';
    files.style.display = 'none';
    if (analytics) analytics.style.display = 'none';
    
    // Show selected section
    switch (name) {
      case 'upload':
        upload.style.display = 'block';
        break;
      case 'chat':
        chat.style.display = 'block';
        if (window.__sb_enable_chat) {
          window.__sb_enable_chat();
        }
        break;
      case 'files':
        files.style.display = 'block';
        break;
      case 'analytics':
        if (analytics) analytics.style.display = 'block';
        break;
    }
  }

  function updatePageTitle() {
    const titles = {
      'projects': 'Projects',
      'files': 'Files',
      'chat': 'Chat',
      'analytics': 'Analytics',
      'settings': 'Settings'
    };
    
    pageTitle.textContent = titles[currentSection] || 'StudyBuddy';
  }

  function setPageTitle(title) {
    pageTitle.textContent = title;
  }

  function handleResize() {
    if (window.innerWidth <= 1024) {
      // On mobile/tablet, start with collapsed sidebar
      if (!sidebar.classList.contains('collapsed')) {
        collapseSidebar();
      }
      // Hide overlay on desktop
      if (sidebarOverlay) {
        sidebarOverlay.classList.remove('active');
      }
    } else {
      // On desktop, ensure sidebar is visible
      if (sidebar.classList.contains('collapsed')) {
        expandSidebar();
      }
      // Hide overlay on desktop
      if (sidebarOverlay) {
        sidebarOverlay.classList.remove('active');
      }
    }
  }

  // Public API
  window.__sb_toggle_sidebar = toggleSidebar;
  window.__sb_collapse_sidebar = collapseSidebar;
  window.__sb_expand_sidebar = expandSidebar;
  window.__sb_navigate_to_section = navigateToSection;
  window.__sb_update_page_title = setPageTitle;
})();
