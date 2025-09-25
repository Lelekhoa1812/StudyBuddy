// ────────────────────────────── static/analytics.js ──────────────────────────────
(function() {
  // DOM elements
  const analyticsSection = document.getElementById('analytics-section');
  const analyticsPeriod = document.getElementById('analytics-period');
  const refreshAnalytics = document.getElementById('refresh-analytics');
  const debugAnalytics = document.getElementById('debug-analytics');
  const modelUsageChart = document.getElementById('model-usage-chart');
  const agentUsageChart = document.getElementById('agent-usage-chart');
  const dailyTrendsChart = document.getElementById('daily-trends-chart');
  const usageSummary = document.getElementById('usage-summary');
  
  // State
  let currentAnalyticsData = null;
  let isAnalyticsVisible = false;
  
  // Initialize
  init();
  
  function init() {
    setupEventListeners();
    
    // Check if analytics section is already visible on page load
    checkAnalyticsVisibility();
    
    // Load analytics when section becomes visible
    document.addEventListener('sectionChanged', (event) => {
      console.log('[ANALYTICS] Section changed to:', event.detail.section);
      if (event.detail.section === 'analytics') {
        isAnalyticsVisible = true;
        console.log('[ANALYTICS] Analytics section is now visible');
        // Small delay to ensure DOM is ready
        setTimeout(() => {
          loadAnalytics();
        }, 100);
      } else {
        isAnalyticsVisible = false;
        console.log('[ANALYTICS] Analytics section is now hidden');
      }
    });
    
    // Also listen for direct analytics section visibility changes
    if (analyticsSection) {
      const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
          if (mutation.type === 'attributes' && mutation.attributeName === 'style') {
            const isVisible = analyticsSection.style.display !== 'none' && analyticsSection.style.display !== '';
            console.log('[ANALYTICS] Direct visibility change detected:', isVisible);
            if (isVisible && !isAnalyticsVisible) {
              isAnalyticsVisible = true;
              setTimeout(() => {
                loadAnalytics();
              }, 100);
            } else if (!isVisible) {
              isAnalyticsVisible = false;
            }
          }
        });
      });
      
      observer.observe(analyticsSection, { attributes: true, attributeFilter: ['style'] });
    }
  }
  
  function checkAnalyticsVisibility() {
    if (analyticsSection) {
      const isVisible = analyticsSection.style.display !== 'none' && analyticsSection.style.display !== '';
      console.log('[ANALYTICS] Initial visibility check:', isVisible);
      if (isVisible) {
        isAnalyticsVisible = true;
        setTimeout(() => {
          loadAnalytics();
        }, 200);
      }
    }
  }
  
  function setupEventListeners() {
    // Period change
    if (analyticsPeriod) {
      analyticsPeriod.addEventListener('change', () => {
        if (isAnalyticsVisible) {
          loadAnalytics();
        }
      });
    }
    
    // Refresh button
    if (refreshAnalytics) {
      refreshAnalytics.addEventListener('click', () => {
        loadAnalytics();
      });
    }
    
    // Debug button
    if (debugAnalytics) {
      debugAnalytics.addEventListener('click', () => {
        console.log('[ANALYTICS] Debug button clicked');
        console.log('[ANALYTICS] Current state:', {
          isAnalyticsVisible,
          analyticsSection: analyticsSection ? analyticsSection.style.display : 'not found',
          user: window.__sb_get_user ? window.__sb_get_user() : 'not available'
        });
        forceLoadAnalytics();
      });
    }
  }
  
  async function loadAnalytics() {
    console.log('[ANALYTICS] loadAnalytics called, isAnalyticsVisible:', isAnalyticsVisible);
    
    if (!isAnalyticsVisible) {
      console.log('[ANALYTICS] Analytics not visible, skipping load');
      return;
    }
    
    const user = window.__sb_get_user();
    console.log('[ANALYTICS] User:', user);
    
    if (!user) {
      showAnalyticsError('Please sign in to view analytics');
      return;
    }
    
    const period = analyticsPeriod ? analyticsPeriod.value : '30';
    console.log('[ANALYTICS] Loading analytics for period:', period);
    
    try {
      showAnalyticsLoading();
      
      // First test if analytics system is working
      console.log('[ANALYTICS] Testing analytics system...');
      const testResponse = await fetch('/analytics/test');
      const testData = await testResponse.json();
      console.log('[ANALYTICS] Test response:', testData);
      
      if (!testData.success) {
        throw new Error(`Analytics system not working: ${testData.message}`);
      }
      
      const url = `/analytics/user?user_id=${encodeURIComponent(user.user_id)}&days=${period}`;
      console.log('[ANALYTICS] Fetching from URL:', url);
      
      const response = await fetch(url);
      console.log('[ANALYTICS] Response status:', response.status);
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      
      const data = await response.json();
      console.log('[ANALYTICS] Response data:', data);
      
      if (data.success) {
        currentAnalyticsData = data.data;
        renderAnalytics(data.data);
      } else {
        throw new Error(data.message || 'Failed to load analytics');
      }
      
    } catch (error) {
      console.error('Analytics loading error:', error);
      showAnalyticsError(`Failed to load analytics: ${error.message}`);
    }
  }
  
  function showAnalyticsLoading() {
    const loadingHtml = `
      <div class="analytics-loading">
        <div class="spinner"></div>
        <div class="loading-text">Loading analytics...</div>
      </div>
    `;
    if (modelUsageChart) modelUsageChart.innerHTML = loadingHtml;
    if (agentUsageChart) agentUsageChart.innerHTML = loadingHtml;
    if (dailyTrendsChart) dailyTrendsChart.innerHTML = loadingHtml;
    if (usageSummary) usageSummary.innerHTML = loadingHtml;
  }
  
  function showAnalyticsError(message) {
    const errorHtml = `<div class="analytics-error">${message}</div>`;
    if (modelUsageChart) modelUsageChart.innerHTML = errorHtml;
    if (agentUsageChart) agentUsageChart.innerHTML = errorHtml;
    if (dailyTrendsChart) dailyTrendsChart.innerHTML = errorHtml;
    if (usageSummary) usageSummary.innerHTML = errorHtml;
  }
  
  function renderAnalytics(data) {
    renderModelUsage(data.model_usage);
    renderAgentUsage(data.agent_usage);
    renderDailyTrends(data.daily_usage);
    renderUsageSummary(data);
  }
  
  function renderModelUsage(modelUsage) {
    if (!modelUsageChart) return;
    
    if (!modelUsage || modelUsage.length === 0) {
      modelUsageChart.innerHTML = '<div class="analytics-empty">No model usage data available</div>';
      return;
    }
    
    // Sort by usage count
    const sortedModels = modelUsage.sort((a, b) => b.count - a.count);
    const totalUsage = sortedModels.reduce((sum, model) => sum + model.count, 0);
    
    let html = '<div class="model-usage-list">';
    sortedModels.forEach(model => {
      const percentage = totalUsage > 0 ? Math.round((model.count / totalUsage) * 100) : 0;
      const lastUsed = new Date(model.last_used * 1000).toLocaleDateString();
      
      html += `
        <div class="model-usage-item">
          <div class="model-info">
            <div class="model-name">${model._id}</div>
            <div class="model-provider">${model.provider}</div>
          </div>
          <div class="model-stats">
            <div class="model-count">${model.count} requests</div>
            <div class="model-percentage">${percentage}%</div>
            <div class="model-last-used">Last used: ${lastUsed}</div>
          </div>
          <div class="model-bar">
            <div class="model-bar-fill" style="width: ${percentage}%"></div>
          </div>
        </div>
      `;
    });
    html += '</div>';
    
    modelUsageChart.innerHTML = html;
  }
  
  function renderAgentUsage(agentUsage) {
    if (!agentUsageChart) return;
    
    if (!agentUsage || agentUsage.length === 0) {
      agentUsageChart.innerHTML = '<div class="analytics-empty">No agent usage data available</div>';
      return;
    }
    
    // Sort by usage count
    const sortedAgents = agentUsage.sort((a, b) => b.count - a.count);
    const totalUsage = sortedAgents.reduce((sum, agent) => sum + agent.count, 0);
    
    let html = '<div class="agent-usage-list">';
    sortedAgents.forEach(agent => {
      const percentage = totalUsage > 0 ? Math.round((agent.count / totalUsage) * 100) : 0;
      const lastUsed = new Date(agent.last_used * 1000).toLocaleDateString();
      const actions = agent.actions ? agent.actions.join(', ') : 'N/A';
      
      html += `
        <div class="agent-usage-item">
          <div class="agent-info">
            <div class="agent-name">${agent._id}</div>
            <div class="agent-actions">Actions: ${actions}</div>
          </div>
          <div class="agent-stats">
            <div class="agent-count">${agent.count} requests</div>
            <div class="agent-percentage">${percentage}%</div>
            <div class="agent-last-used">Last used: ${lastUsed}</div>
          </div>
          <div class="agent-bar">
            <div class="agent-bar-fill" style="width: ${percentage}%"></div>
          </div>
        </div>
      `;
    });
    html += '</div>';
    
    agentUsageChart.innerHTML = html;
  }
  
  function renderDailyTrends(dailyUsage) {
    if (!dailyTrendsChart) return;
    
    if (!dailyUsage || dailyUsage.length === 0) {
      dailyTrendsChart.innerHTML = '<div class="analytics-empty">No daily usage data available</div>';
      return;
    }
    
    // Sort by date
    const sortedDaily = dailyUsage.sort((a, b) => {
      const dateA = new Date(a._id.year, a._id.month - 1, a._id.day);
      const dateB = new Date(b._id.year, b._id.month - 1, b._id.day);
      return dateA - dateB;
    });
    
    const maxUsage = Math.max(...sortedDaily.map(d => d.total_requests));
    
    let html = '<div class="daily-trends-chart">';
    sortedDaily.forEach(day => {
      const date = new Date(day._id.year, day._id.month - 1, day._id.day);
      const dateStr = date.toLocaleDateString();
      const height = maxUsage > 0 ? (day.total_requests / maxUsage) * 100 : 0;
      
      html += `
        <div class="daily-bar">
          <div class="daily-bar-fill" style="height: ${height}%"></div>
          <div class="daily-label">${dateStr}</div>
          <div class="daily-count">${day.total_requests}</div>
        </div>
      `;
    });
    html += '</div>';
    
    dailyTrendsChart.innerHTML = html;
  }
  
  function renderUsageSummary(data) {
    if (!usageSummary) return;
    
    const totalRequests = data.total_requests || 0;
    const periodDays = data.period_days || 30;
    const avgPerDay = Math.round(totalRequests / periodDays * 10) / 10;
    
    const modelCount = data.model_usage ? data.model_usage.length : 0;
    const agentCount = data.agent_usage ? data.agent_usage.length : 0;
    
    const mostUsedModel = data.model_usage && data.model_usage.length > 0 
      ? data.model_usage[0] 
      : null;
    const mostUsedAgent = data.agent_usage && data.agent_usage.length > 0 
      ? data.agent_usage[0] 
      : null;
    
    let html = `
      <div class="usage-summary-content">
        <div class="summary-stat">
          <div class="summary-value">${totalRequests}</div>
          <div class="summary-label">Total Requests</div>
        </div>
        <div class="summary-stat">
          <div class="summary-value">${avgPerDay}</div>
          <div class="summary-label">Avg per Day</div>
        </div>
        <div class="summary-stat">
          <div class="summary-value">${modelCount}</div>
          <div class="summary-label">Models Used</div>
        </div>
        <div class="summary-stat">
          <div class="summary-value">${agentCount}</div>
          <div class="summary-label">Agents Used</div>
        </div>
    `;
    
    if (mostUsedModel) {
      html += `
        <div class="summary-highlight">
          <div class="highlight-label">Most Used Model:</div>
          <div class="highlight-value">${mostUsedModel._id} (${mostUsedModel.count} times)</div>
        </div>
      `;
    }
    
    if (mostUsedAgent) {
      html += `
        <div class="summary-highlight">
          <div class="highlight-label">Most Used Agent:</div>
          <div class="highlight-value">${mostUsedAgent._id} (${mostUsedAgent.count} times)</div>
        </div>
      `;
    }
    
    html += '</div>';
    usageSummary.innerHTML = html;
  }
  
  // Manual trigger function for debugging
  function forceLoadAnalytics() {
    console.log('[ANALYTICS] Force loading analytics...');
    isAnalyticsVisible = true;
    loadAnalytics();
  }
  
  // Expose functions for external use
  window.__sb_load_analytics = loadAnalytics;
  window.__sb_force_load_analytics = forceLoadAnalytics;
  window.__sb_show_analytics_section = () => {
    console.log('[ANALYTICS] Showing analytics section...');
    if (analyticsSection) {
      analyticsSection.style.display = 'block';
      isAnalyticsVisible = true;
      // Trigger analytics loading
      setTimeout(() => {
        loadAnalytics();
      }, 100);
    }
  };
  window.__sb_hide_analytics_section = () => {
    console.log('[ANALYTICS] Hiding analytics section...');
    if (analyticsSection) {
      analyticsSection.style.display = 'none';
      isAnalyticsVisible = false;
    }
  };
})();
