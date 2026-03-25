// Leads list view
const Leads = (() => {
  let _state = { status: '', priority: '', search: '', offset: 0, limit: 50 };

  const STATUS_OPTS = ['', 'ČAKA', 'POSLANO', 'ODPRT', 'ODGOVORIL', 'ZAVRNIL', 'KONVERTIRAN'];
  const PRIO_OPTS   = ['', 'VISOKA', 'SREDNJA', 'NIZKA'];

  function priorityBadge(p) {
    return `<span class="badge badge-${p}">${p || '—'}</span>`;
  }

  function statusBadge(s) {
    const map = { ČAKA: 'muted', POSLANO: 'blue', ODPRT: 'yellow', ODGOVORIL: 'green', ZAVRNIL: 'red', KONVERTIRAN: 'green' };
    return `<span class="badge badge-${map[s] || 'muted'}">${s || '—'}</span>`;
  }

  function filterLeads(leads) {
    let l = leads;
    if (_state.search) {
      const q = _state.search.toLowerCase();
      l = l.filter((x) => (x.company_name || '').toLowerCase().includes(q)
        || (x.email || '').toLowerCase().includes(q)
        || (x.city || '').toLowerCase().includes(q));
    }
    return l;
  }

  async function render() {
    const app = document.getElementById('app');

    let data;
    try {
      const params = { limit: _state.limit, offset: _state.offset };
      if (_state.status)   params.status   = _state.status;
      if (_state.priority) params.priority = _state.priority;
      data = await API.fetchLeads(params);
    } catch (e) {
      app.innerHTML = `<div class="empty-state"><p style="color:var(--red)">Napaka: ${e.message}</p></div>`;
      return;
    }

    const filtered = filterLeads(data.leads);

    app.innerHTML = `
      <!-- Search -->
      <div class="search-wrap">
        <svg class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
        </svg>
        <input class="search-input" id="searchInput" placeholder="Iskanje podjetja, email, kraj..."
          value="${_state.search}" oninput="Leads._search(this.value)">
      </div>

      <!-- Priority filter -->
      <div class="filter-bar" id="prioBar">
        ${PRIO_OPTS.map((p) => `
          <span class="pill ${_state.priority === p ? 'active' : ''}"
            onclick="Leads._filter('priority','${p}')">
            ${p || 'Vse prioritete'}
          </span>`).join('')}
      </div>

      <!-- Status filter -->
      <div class="filter-bar" id="statusBar">
        ${STATUS_OPTS.map((s) => `
          <span class="pill ${_state.status === s ? 'active' : ''}"
            onclick="Leads._filter('status','${s}')">
            ${s || 'Vsi statusi'}
          </span>`).join('')}
      </div>

      <!-- Count -->
      <div style="padding:4px 16px 8px;font-size:0.78rem;color:var(--text-muted)">
        ${filtered.length} leadov${data.total > _state.limit ? ` od ${data.total}` : ''}
      </div>

      <!-- List -->
      ${filtered.length === 0
        ? '<div class="empty-state"><p>Ni leadov z izbranimi filtri</p></div>'
        : `<ul class="list" style="margin:0 16px;border:1px solid var(--border);border-radius:var(--radius);overflow:hidden">
            ${filtered.map((l) => `
              <a class="list-item" href="#lead/${l.lead_id}">
                <div class="list-item-content">
                  <div class="list-item-title">${_esc(l.company_name)}</div>
                  <div class="list-item-sub">${_esc(l.email || l.phone || '—')} · ${_esc(l.city || '—')}</div>
                </div>
                <div class="list-item-right" style="display:flex;flex-direction:column;align-items:flex-end;gap:4px">
                  ${priorityBadge(l.priority)}
                  ${statusBadge(l.status)}
                </div>
                <span class="chevron">›</span>
              </a>`).join('')}
          </ul>
          ${data.total > _state.offset + _state.limit
            ? `<div style="padding:16px;text-align:center">
                <button class="btn btn-ghost" onclick="Leads._loadMore()">Naloži več</button>
              </div>` : ''}`
      }
    `;
  }

  function _filter(key, val) {
    _state[key] = val;
    _state.offset = 0;
    render();
  }

  let _searchTimer;
  function _search(val) {
    _state.search = val;
    clearTimeout(_searchTimer);
    _searchTimer = setTimeout(() => render(), 300);
  }

  function _loadMore() {
    _state.offset += _state.limit;
    render();
  }

  function _esc(s) {
    return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  return { render, _filter, _search, _loadMore };
})();
