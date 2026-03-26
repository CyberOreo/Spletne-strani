// API klient — fetch() REST wrapper
const API = (() => {
  function baseURL() {
    return localStorage.getItem('apiURL') || '';
  }

  async function request(method, path, body) {
    const url = baseURL() + path;
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json' },
    };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const res = await fetch(url, opts);
    if (!res.ok) {
      let detail = res.statusText;
      try { detail = (await res.json()).detail || detail; } catch {}
      throw new Error(detail);
    }
    const ct = res.headers.get('content-type') || '';
    if (ct.includes('application/json')) return res.json();
    return res;
  }

  return {
    setBaseURL(url) { localStorage.setItem('apiURL', url.replace(/\/$/, '')); },
    getBaseURL: baseURL,
    get: (path) => request('GET', path),

    // Stats
    fetchStats:          ()           => request('GET',    '/api/stats'),

    // Leads
    fetchLeads:          (params)     => request('GET',    '/api/leads?' + new URLSearchParams(params || {})),
    fetchLead:           (id)         => request('GET',    `/api/leads/${id}`),
    updateLead:          (id, body)   => request('PATCH',  `/api/leads/${id}`, body),

    // Emails
    fetchPendingEmails:  (limit)      => request('GET',    `/api/emails/pending?limit=${limit || 50}`),
    fetchLeadEmails:     (id)         => request('GET',    `/api/emails/${id}`),

    // Pipeline
    runDailyPipeline:    (dry_run)    => request('POST',   '/api/run/daily' + (dry_run ? '?dry_run=true' : ''), {}),
    fetchPipelineStatus: ()           => request('GET',    '/api/run/status'),

    // Operations
    triggerScrape:       (body)       => request('POST',   '/api/scrape', body),
    triggerQualify:      ()           => request('POST',   '/api/qualify', {}),
    generateEmails:      ()           => request('POST',   '/api/generate-emails', {}),
    triggerSend:         (body)       => request('POST',   '/api/send', body),
    triggerFollowup:     (days)       => request('POST',   '/api/followup', { days: days || 5 }),
    generatePreview:     (id)         => request('POST',   `/api/preview/${id}`, {}),
    unsubscribe:         (email)      => request('POST',   '/api/unsubscribe', { email }),
    cleanup:             (months)     => request('DELETE', `/api/cleanup?months=${months || 12}`),

    // Settings
    fetchSettings:       ()           => request('GET',  '/api/settings'),
    saveSettings:        (body)       => request('POST', '/api/settings', body),
    testSMTP:            ()           => request('POST', '/api/settings/test-smtp', {}),

    // Server info & update
    fetchServerInfo:     ()   => request('GET',  '/api/server-info'),
    triggerUpdate:       ()   => request('POST', '/api/update', {}),

    // Export
    exportCSV() {
      window.open((baseURL() || '') + '/api/export/csv', '_blank');
    },
  };
})();

// WebSocket manager
const WS = (() => {
  let socket = null;
  const handlers = [];

  function connect() {
    const apiURL = localStorage.getItem('apiURL') || '';
    const wsURL = apiURL.replace(/^http/, 'ws') + '/ws';
    try {
      socket = new WebSocket(wsURL);
      socket.onmessage = (e) => {
        let msg;
        try { msg = JSON.parse(e.data); } catch { return; }
        handlers.forEach((h) => h(msg));
      };
      socket.onclose = () => { setTimeout(connect, 3000); };
      socket.onerror = () => { socket.close(); };
    } catch {}
  }

  return {
    connect,
    on(handler)  { if (!handlers.includes(handler)) handlers.push(handler); },
    off(handler) { const i = handlers.indexOf(handler); if (i !== -1) handlers.splice(i, 1); },
    connected()  { return socket && socket.readyState === 1; },
    send(msg)    { if (socket && socket.readyState === 1) socket.send(JSON.stringify(msg)); },
  };
})();
