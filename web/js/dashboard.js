// Dashboard — KPI kartice + zagon pipeline
const Dashboard = (() => {
  const STAGES = ['start', 'scraping', 'qualify', 'generate', 'replies', 'followup', 'sending', 'cleanup', 'complete'];

  function kpiColor(val, good, ok) {
    if (val >= good) return 'green';
    if (val >= ok) return 'yellow';
    return 'red';
  }

  function stageIndex(stage) {
    return STAGES.indexOf(stage);
  }

  function renderPipeline(ps) {
    const pct = ps.status === 'done' ? 100 : ps.status === 'running'
      ? Math.round((stageIndex(ps.stage) / (STAGES.length - 1)) * 100)
      : 0;

    const stageLabels = { start: 'Start', scraping: 'Scraping', qualify: 'Kvalif.', generate: 'Emaili',
      replies: 'Odgovori', followup: 'Follow-up', sending: 'Pošiljanje', cleanup: 'GDPR', complete: 'Končano' };

    const cur = stageIndex(ps.stage);

    return `
      <div class="progress-wrap">
        <div class="progress-bar-outer">
          <div class="progress-bar-inner" style="width:${pct}%"></div>
        </div>
        <div class="progress-stages">
          ${STAGES.filter((_, i) => i % 2 === 0).map((s, i) => {
            const si = stageIndex(s);
            const cls = si < cur ? 'done' : si === cur ? 'active' : '';
            return `<span class="stage-item ${cls}">${stageLabels[s]}</span>`;
          }).join('')}
        </div>
      </div>
      <div style="padding: 0 16px 8px; font-size:0.8rem; color:var(--text-muted)">
        ${ps.scraped ? `Scrapano: ${ps.scraped} · ` : ''}
        ${ps.qualified ? `Kvaificirano: ${ps.qualified} · ` : ''}
        ${ps.emails_sent ? `Poslano: ${ps.emails_sent}` : ''}
        ${ps.message ? `<br><span style="color:var(--primary-light)">${ps.message}</span>` : ''}
      </div>`;
  }

  async function render() {
    const app = document.getElementById('app');
    let stats, ps;
    try {
      [stats, ps] = await Promise.all([API.fetchStats(), API.fetchPipelineStatus()]);
    } catch (e) {
      app.innerHTML = `<div class="empty-state">
        <p style="color:var(--red)">Napaka pri nalaganju: ${e.message}</p>
        <button class="btn btn-ghost" onclick="App.go('settings')" style="margin-top:16px">Nastavi API URL</button>
      </div>`;
      return;
    }

    const openColor = kpiColor(stats.open_rate, 30, 15);
    const replyColor = kpiColor(stats.reply_rate, 5, 2);
    const convColor = kpiColor(stats.conversion_rate, 1, 0.5);

    const running = ps.status === 'running';

    app.innerHTML = `
      <div class="card-grid">
        <div class="kpi-card">
          <div class="kpi-value primary">${stats.total_leads.toLocaleString()}</div>
          <div class="kpi-label">Skupaj leadov</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-value">${stats.emails_sent.toLocaleString()}</div>
          <div class="kpi-label">Emailov poslanih</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-value ${openColor}">${stats.open_rate.toFixed(1)}%</div>
          <div class="kpi-label">Open rate</div>
          <div class="kpi-sub">cilj &gt;30%</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-value ${replyColor}">${stats.reply_rate.toFixed(1)}%</div>
          <div class="kpi-label">Reply rate</div>
          <div class="kpi-sub">cilj &gt;5%</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-value ${convColor}">${stats.conversion_rate.toFixed(1)}%</div>
          <div class="kpi-label">Konverzije</div>
          <div class="kpi-sub">cilj &gt;1%</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-value green">${stats.converted || 0}</div>
          <div class="kpi-label">Konvertiranih</div>
        </div>
      </div>

      <div class="card" id="pipelineCard">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
          <span style="font-weight:600">Dnevni pipeline</span>
          <span class="badge ${running ? 'badge-yellow' : ps.status === 'done' ? 'badge-green' : 'badge-muted'}">
            ${running ? 'V teku' : ps.status === 'done' ? 'Končan' : ps.status === 'error' ? 'Napaka' : 'Čaka'}
          </span>
        </div>
        ${running || ps.status !== 'idle' ? renderPipeline(ps) : ''}
        <div style="display:flex;gap:8px;margin-top:12px">
          <button class="btn btn-primary btn-full" id="runBtn" onclick="Dashboard._run(false)" ${running ? 'disabled' : ''}>
            ${running ? '<div class="spinner" style="width:18px;height:18px;border-width:2px"></div>' : '▶ Zaženi danes'}
          </button>
          <button class="btn btn-ghost" id="dryBtn" onclick="Dashboard._run(true)" title="Dry run (brez pošiljanja)" ${running ? 'disabled' : ''}>
            Test
          </button>
        </div>
      </div>

      <div class="section-header">Statusi leadov</div>
      <ul class="list" style="margin:0 16px;border:1px solid var(--border);border-radius:var(--radius);overflow:hidden">
        ${Object.entries(stats.by_status || {}).sort().map(([s, n]) => `
          <li style="display:flex;justify-content:space-between;padding:10px 14px;border-bottom:1px solid var(--border);font-size:0.9rem">
            <span>${s}</span><span style="font-weight:600">${n}</span>
          </li>`).join('')}
      </ul>
    `;

    // Listen for pipeline updates via WebSocket
    WS.on((msg) => {
      if (msg.status || msg.stage) {
        const card = document.getElementById('pipelineCard');
        if (card) {
          const bar = card.querySelector('.progress-wrap, .progress-stages');
          // Re-render just the progress
          const progressDiv = card.querySelector('#progressArea');
          if (progressDiv) progressDiv.innerHTML = renderPipeline(msg);
        }
      }
    });
  }

  async function _run(dry_run) {
    const btn = document.getElementById('runBtn');
    if (btn) btn.disabled = true;
    try {
      const res = await API.runDailyPipeline(dry_run);
      App.toast(dry_run ? 'Test pipeline zagnan' : 'Pipeline zagnan!', 'success');
      setTimeout(() => render(), 500);
    } catch (e) {
      App.toast('Napaka: ' + e.message, 'error');
      if (btn) btn.disabled = false;
    }
  }

  return { render, _run };
})();
