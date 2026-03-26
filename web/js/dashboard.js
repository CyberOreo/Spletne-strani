// Dashboard — real-time pipeline tracker + KPI kartice
const Dashboard = (() => {
  // ── Constants ────────────────────────────────────────────────────────────
  const STAGES = ['start','scraping','qualify','generate','replies','followup','sending','cleanup','complete'];
  const STAGE_LABELS = {
    start:'Zaganjam', scraping:'Scraping', qualify:'Kvalifikacija',
    generate:'Emaili', replies:'Odgovori', followup:'Follow-up',
    sending:'Pošiljanje', cleanup:'GDPR', complete:'Končano',
  };

  // ── State ─────────────────────────────────────────────────────────────────
  let _wsHandler = null;
  let _statsTimer = null;
  let _countdownTimer = null;
  let _lastStats = null;
  let _lastPipeline = null;
  let _active = false;

  // ── Helpers ───────────────────────────────────────────────────────────────
  function stageIdx(s) { return STAGES.indexOf(s); }

  function kpiColor(val, good, warn) {
    if (val >= good) return 'green';
    if (val >= warn) return 'yellow';
    return 'red';
  }

  function fmt(n) { return Number(n || 0).toLocaleString('sl-SI'); }

  function nextOccurrence(hhmm) {
    const now = new Date();
    const [h, m] = hhmm.split(':').map(Number);
    const t = new Date(now);
    t.setHours(h, m, 0, 0);
    if (t <= now) t.setDate(t.getDate() + 1);
    return t;
  }

  function formatCountdown(ms) {
    if (ms <= 0) return '00:00:00';
    const s = Math.floor(ms / 1000);
    const h = Math.floor(s / 3600);
    const min = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    return `${String(h).padStart(2,'0')}:${String(min).padStart(2,'0')}:${String(sec).padStart(2,'0')}`;
  }

  // ── Activity feed ─────────────────────────────────────────────────────────
  function renderActivity(items) {
    if (!items || !items.length) {
      return `<div class="activity-empty">Še ni aktivnosti</div>`;
    }
    return items.slice(0, 20).map(ev => {
      const cls = ev.type === 'success' ? 'act-success' : ev.type === 'error' ? 'act-error' : ev.type === 'warning' ? 'act-warn' : 'act-info';
      const icon = ev.type === 'success' ? '✓' : ev.type === 'error' ? '✗' : ev.type === 'warning' ? '!' : '·';
      return `<div class="act-item ${cls}"><span class="act-icon">${icon}</span><span class="act-time">${ev.time || ''}</span><span class="act-msg">${ev.message}</span></div>`;
    }).join('');
  }

  // ── Pipeline card ─────────────────────────────────────────────────────────
  function renderPipelineCard(ps) {
    const status = ps?.status || 'idle';
    const stage = ps?.stage || '';
    const pct = ps?.progress_pct ?? (status === 'done' ? 100 : status === 'running' ? Math.max(5, Math.round((stageIdx(stage) / (STAGES.length - 1)) * 100)) : 0);
    const cur = stageIdx(stage);

    const statusClass = status === 'running' ? 'status-running' : status === 'done' ? 'status-done' : status === 'error' ? 'status-error' : 'status-idle';
    const statusLabel = status === 'running' ? (ps?.stage_label || 'V teku...') : status === 'done' ? 'Končano ✓' : status === 'error' ? 'Napaka!' : 'Čaka';

    const counters = [
      { label: 'Scrapano', val: ps?.scraped || 0, icon: '🔍' },
      { label: 'Kvalificirano', val: ps?.qualified || 0, icon: '✓' },
      { label: 'Emaili', val: ps?.emails_generated || 0, icon: '✉' },
      { label: 'Poslano', val: ps?.emails_sent || 0, icon: '🚀' },
    ];

    const showProgress = status === 'running' || status === 'done' || status === 'error';

    return `
      <div class="pipeline-status-row">
        <div class="pipeline-dot ${statusClass}"></div>
        <div class="pipeline-status-text">
          <div class="pipeline-status-label">${statusLabel}</div>
          ${ps?.message ? `<div class="pipeline-msg">${ps.message}</div>` : ''}
          ${ps?.started_at ? `<div class="pipeline-started">Zagnan: ${new Date(ps.started_at).toLocaleTimeString('sl-SI', {hour:'2-digit',minute:'2-digit'})}</div>` : ''}
        </div>
        <div style="margin-left:auto;display:flex;gap:8px">
          <button class="btn btn-primary" id="runBtn" onclick="Dashboard._run(false)" ${status === 'running' ? 'disabled' : ''} style="min-width:100px">
            ${status === 'running' ? '<div class="spinner" style="width:16px;height:16px;border-width:2px;display:inline-block"></div>' : '▶ Zaženi'}
          </button>
          <button class="btn btn-ghost" onclick="Dashboard._run(true)" title="Test (brez pošiljanja)" ${status === 'running' ? 'disabled' : ''}>
            Test
          </button>
        </div>
      </div>

      ${showProgress ? `
      <div class="progress-wrap" style="margin-top:14px">
        <div class="progress-bar-outer">
          <div class="progress-bar-inner ${status === 'error' ? 'progress-error' : ''}" style="width:${pct}%;transition:width 0.6s ease"></div>
        </div>
        <div class="progress-pct">${pct}%</div>
      </div>
      <div class="stage-pills">
        ${STAGES.map((s, i) => {
          const done = i < cur || status === 'done';
          const active = i === cur && status === 'running';
          return `<span class="stage-pill ${done ? 'pill-done' : active ? 'pill-active' : 'pill-idle'}">${STAGE_LABELS[s]}</span>`;
        }).join('')}
      </div>` : ''}

      <div class="counters-row" id="counters">
        ${counters.map(c => `
          <div class="counter-box">
            <div class="counter-icon">${c.icon}</div>
            <div class="counter-val" data-key="${c.label}">${fmt(c.val)}</div>
            <div class="counter-label">${c.label}</div>
          </div>`).join('')}
      </div>`;
  }

  // ── Overnight schedule card ───────────────────────────────────────────────
  function renderScheduleCard() {
    const scrapeTime = '22:00';
    const sendTime = '08:00';
    const nextScrape = nextOccurrence(scrapeTime);
    const nextSend = nextOccurrence(sendTime);
    const nowMs = Date.now();
    const scrapeMs = nextScrape - nowMs;
    const sendMs = nextSend - nowMs;
    const nextEvent = scrapeMs < sendMs ? { label: 'Scraping', time: scrapeTime, ms: scrapeMs } : { label: 'Pošiljanje', time: sendTime, ms: sendMs };

    return `
      <div class="schedule-card">
        <div class="schedule-title">Overnight načrt</div>
        <div class="schedule-row">
          <span class="schedule-icon">🌙</span>
          <span class="schedule-event">Scraping</span>
          <span class="schedule-time">${scrapeTime}</span>
        </div>
        <div class="schedule-row">
          <span class="schedule-icon">☀️</span>
          <span class="schedule-event">Pošiljanje</span>
          <span class="schedule-time">${sendTime}</span>
        </div>
        <div class="countdown-row">
          <span class="countdown-label">Naslednje: ${nextEvent.label}</span>
          <span class="countdown-timer" id="countdownTimer">${formatCountdown(nextEvent.ms)}</span>
        </div>
      </div>`;
  }

  // ── KPI grid ──────────────────────────────────────────────────────────────
  function renderKPI(stats) {
    const openColor = kpiColor(stats.open_rate, 30, 15);
    const replyColor = kpiColor(stats.reply_rate, 5, 2);
    const convColor = kpiColor(stats.conversion_rate, 1, 0.5);

    return `
      <div class="kpi-grid">
        <div class="kpi-card">
          <div class="kpi-val primary">${fmt(stats.total_leads)}</div>
          <div class="kpi-lbl">Skupaj leadov</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val">${fmt(stats.emails_sent)}</div>
          <div class="kpi-lbl">Emailov poslanih</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val ${openColor}">${(stats.open_rate || 0).toFixed(1)}%</div>
          <div class="kpi-lbl">Open rate</div>
          <div class="kpi-sub">cilj &gt;30%</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val ${replyColor}">${(stats.reply_rate || 0).toFixed(1)}%</div>
          <div class="kpi-lbl">Reply rate</div>
          <div class="kpi-sub">cilj &gt;5%</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val ${convColor}">${(stats.conversion_rate || 0).toFixed(1)}%</div>
          <div class="kpi-lbl">Konverzije</div>
          <div class="kpi-sub">cilj &gt;1%</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val green">${fmt(stats.converted)}</div>
          <div class="kpi-lbl">Konvertiranih</div>
        </div>
      </div>`;
  }

  // ── Status table ──────────────────────────────────────────────────────────
  function renderStatusTable(byStatus) {
    const entries = Object.entries(byStatus || {}).sort(([,a],[,b]) => b - a);
    if (!entries.length) return '';
    return `
      <div class="section-header">Statusi leadov</div>
      <div class="status-table">
        ${entries.map(([s,n]) => `
          <div class="status-row">
            <span class="status-badge status-${s.toLowerCase()}">${s}</span>
            <div class="status-bar-wrap"><div class="status-bar" style="width:${Math.min(100, (n / (entries[0][1] || 1)) * 100)}%"></div></div>
            <span class="status-count">${fmt(n)}</span>
          </div>`).join('')}
      </div>`;
  }

  // ── Full render ───────────────────────────────────────────────────────────
  async function render() {
    _active = true;
    const app = document.getElementById('app');

    let stats = _lastStats;
    let pipeline = _lastPipeline;
    let activity = [];

    try {
      const [statsRes, actRes] = await Promise.all([
        API.fetchStats(),
        API.get('/api/activity'),
      ]);
      stats = statsRes;
      pipeline = actRes.pipeline;
      activity = actRes.activity || [];
      _lastStats = stats;
      _lastPipeline = pipeline;
    } catch (e) {
      if (!stats) {
        app.innerHTML = `<div class="empty-state">
          <div style="font-size:2rem;margin-bottom:12px">⚠️</div>
          <div style="color:var(--red);margin-bottom:16px">Napaka pri povezavi: ${e.message}</div>
          <button class="btn btn-ghost" onclick="App.go('settings')">Nastavi API URL</button>
        </div>`;
        return;
      }
    }

    app.innerHTML = `
      <div class="dashboard-wrap">

        <!-- Pipeline card -->
        <div class="card pipeline-card" id="pipelineCard">
          <div class="card-title">Pipeline status</div>
          <div id="pipelineInner">${renderPipelineCard(pipeline)}</div>
        </div>

        <!-- Overnight schedule -->
        <div id="scheduleWrap">${renderScheduleCard()}</div>

        <!-- KPI -->
        <div class="card">
          <div class="card-title">Statistike</div>
          ${renderKPI(stats)}
        </div>

        <!-- Activity feed -->
        <div class="card">
          <div class="card-title" style="display:flex;justify-content:space-between;align-items:center">
            <span>Aktivnost</span>
            <span class="ws-dot ${WS.connected() ? 'ws-live' : 'ws-offline'}" id="wsDot" title="${WS.connected() ? 'Live' : 'Offline'}"></span>
          </div>
          <div class="activity-feed" id="activityFeed">${renderActivity(activity)}</div>
        </div>

        <!-- Status table -->
        ${renderStatusTable(stats?.by_status)}

      </div>`;

    // Start countdown
    _startCountdown();

    // WebSocket handler
    if (_wsHandler) WS.off(_wsHandler);
    _wsHandler = (msg) => {
      if (!_active) return;
      if (msg.type === 'heartbeat' || msg.type === 'pipeline_done') {
        if (msg.pipeline) {
          _lastPipeline = msg.pipeline;
          _updatePipelineDOM(msg.pipeline);
        }
        if (msg.activity) {
          _updateActivityDOM(msg.activity);
        }
      }
    };
    WS.on(_wsHandler);

    // Stats refresh every 30s
    if (_statsTimer) clearInterval(_statsTimer);
    _statsTimer = setInterval(async () => {
      if (!_active) return;
      try {
        const s = await API.fetchStats();
        _lastStats = s;
        const kpiEl = document.querySelector('.kpi-grid');
        if (kpiEl) kpiEl.outerHTML = renderKPI(s);
        const st = document.querySelector('.status-table');
        if (st) st.outerHTML = renderStatusTable(s?.by_status);
      } catch (_) {}
    }, 30000);
  }

  // ── Live DOM updates (no full re-render) ──────────────────────────────────
  function _updatePipelineDOM(ps) {
    const inner = document.getElementById('pipelineInner');
    if (!inner) return;
    inner.innerHTML = renderPipelineCard(ps);
    // Update WS dot
    const dot = document.getElementById('wsDot');
    if (dot) { dot.className = 'ws-dot ws-live'; dot.title = 'Live'; }
  }

  function _updateActivityDOM(items) {
    const feed = document.getElementById('activityFeed');
    if (!feed) return;
    feed.innerHTML = renderActivity(items);
  }

  function _startCountdown() {
    if (_countdownTimer) clearInterval(_countdownTimer);
    _countdownTimer = setInterval(() => {
      if (!_active) { clearInterval(_countdownTimer); return; }
      const wrap = document.getElementById('scheduleWrap');
      if (wrap) wrap.innerHTML = renderScheduleCard();
    }, 1000);
  }

  // ── Run pipeline ──────────────────────────────────────────────────────────
  async function _run(dry_run) {
    const btn = document.getElementById('runBtn');
    if (btn) btn.disabled = true;
    try {
      await API.runDailyPipeline(dry_run);
      App.toast(dry_run ? '🧪 Test pipeline zagnan' : '🚀 Pipeline zagnan!', 'success');
      // Immediate update
      const actRes = await API.get('/api/activity');
      _lastPipeline = actRes.pipeline;
      _updatePipelineDOM(actRes.pipeline);
      _updateActivityDOM(actRes.activity || []);
    } catch (e) {
      App.toast('Napaka: ' + e.message, 'error');
      if (btn) btn.disabled = false;
    }
  }

  // ── Cleanup on navigation away ────────────────────────────────────────────
  function destroy() {
    _active = false;
    if (_wsHandler) { WS.off(_wsHandler); _wsHandler = null; }
    if (_statsTimer) { clearInterval(_statsTimer); _statsTimer = null; }
    if (_countdownTimer) { clearInterval(_countdownTimer); _countdownTimer = null; }
  }

  return { render, _run, destroy };
})();
