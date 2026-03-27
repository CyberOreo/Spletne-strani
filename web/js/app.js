// SPA Router — LeadGen EU
const App = (() => {
  const views = {
    dashboard:    () => Dashboard.render(),
    leads:        () => Leads.render(),
    emails:       () => Emails.render(),
    campaign:     () => Campaign.render(),
    reports:      () => Reports.render(),
    settings:     () => Settings.render(),
  };

  const titles = {
    dashboard: 'LeadGen EU',
    leads:     'Leadi',
    emails:    'Pregled emailov',
    campaign:  'Kampanja',
    reports:   'Poročila',
    settings:  'Nastavitve',
  };

  function getRoute() {
    const hash = location.hash.slice(1) || 'dashboard';
    if (hash.startsWith('lead/')) return { view: 'lead-detail', id: hash.slice(5) };
    return { view: hash, id: null };
  }

  let _currentView = null;

  async function navigate() {
    const { view, id } = getRoute();
    const app = document.getElementById('app');
    const title = document.getElementById('headerTitle');
    const backBtn = document.getElementById('backBtn');

    // Destroy previous view if it has a destroy() method
    if (_currentView && _currentView !== view) {
      if (typeof Dashboard.destroy === 'function' && _currentView === 'dashboard') Dashboard.destroy();
    }
    _currentView = view;

    // Update nav
    document.querySelectorAll('.nav-item').forEach((el) => {
      const href = el.getAttribute('href').slice(1);
      el.classList.toggle('active', href === view || (view === 'lead-detail' && href === 'leads'));
    });

    // Header
    title.textContent = id ? '' : (titles[view] || 'LeadGen EU');
    backBtn.style.display = id ? 'block' : 'none';

    // Render view
    app.innerHTML = '<div class="loading-screen"><div class="spinner"></div></div>';

    try {
      if (view === 'lead-detail' && id) {
        await LeadDetail.render(id);
      } else if (views[view]) {
        await views[view]();
      } else {
        await Dashboard.render();
      }
    } catch (err) {
      app.innerHTML = `<div class="empty-state"><p style="color:var(--red)">Napaka: ${err.message}</p>
        <button class="btn btn-ghost" onclick="App.go('settings')" style="margin-top:16px">Nastavitve API</button></div>`;
    }
  }

  function go(view, id) {
    location.hash = id ? `${view}/${id}` : view;
  }

  // Toast notification
  function toast(msg, type = '', duration = 2800) {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.className = 'toast show' + (type ? ` ${type}` : '');
    clearTimeout(el._t);
    el._t = setTimeout(() => { el.className = 'toast'; }, duration);
  }

  // API connectivity check
  async function checkAPI() {
    const dot = document.getElementById('statusDot');
    try {
      await API.fetchStats();
      dot.className = 'status-dot online';
    } catch {
      dot.className = 'status-dot offline';
    }
  }

  // Init
  function init() {
    window.addEventListener('hashchange', navigate);
    WS.connect();
    WS.on((msg) => {
      // Global toast for pipeline completion (when not on dashboard)
      const onDash = (_currentView === 'dashboard' || !_currentView);
      if (msg.type === 'pipeline_done' && !onDash) {
        const s = msg.pipeline?.status;
        if (s === 'done') toast('Pipeline končan ✓', 'success');
        if (s === 'error') toast('Napaka: ' + msg.pipeline?.message, 'error');
      }
    });
    navigate();
    checkAPI();
    setInterval(checkAPI, 30000);
  }

  return { init, go, toast, checkAPI };
})();

document.addEventListener('DOMContentLoaded', App.init);
