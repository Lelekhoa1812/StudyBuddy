// ────────────────────────────── static/sidebar.js ──────────────────────────────
(function() {
  // DOM elements
  const sidebar = document.getElementById('sidebar');
  const sidebarToggle = document.getElementById('sidebar-toggle');
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
    
    // Update hamburger icon to close icon
    updateHamburgerIcon();
  }

  function collapseSidebar() {
    sidebar.classList.add('collapsed');
    // On mobile, remove the 'open' class to hide
    sidebar.classList.remove('open');
    mainContent.classList.add('sidebar-collapsed');
    isSidebarOpen = false;
    
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
        // Projects section is always visible, no action needed
        showSection('upload');
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
        // Could show usage analytics or insights
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
    if (!upload || !chat || !files) return;
    upload.style.display = name === 'upload' ? 'block' : 'none';
    chat.style.display = name === 'chat' ? 'block' : 'none';
    files.style.display = name === 'files' ? 'block' : 'none';
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
    } else {
      // On desktop, ensure sidebar is visible
      if (sidebar.classList.contains('collapsed')) {
        expandSidebar();
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
