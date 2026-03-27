// Emails — pregled in odobritev emailov pred pošiljanjem
const Emails = (() => {

  const PRIORITY_COLORS = { VISOKA: 'red', SREDNJA: 'yellow', NIZKA: 'muted' };
  const FLAG = {
    si:'🇸🇮', hr:'🇭🇷', at:'🇦🇹', de:'🇩🇪', it:'🇮🇹',
    pl:'🇵🇱', cz:'🇨🇿', hu:'🇭🇺', ro:'🇷🇴', sk:'🇸🇰',
  };

  let _drafts   = [];
  let _approved = new Set();
  let _rejected = new Set();

  // ── Render ────────────────────────────────────────────────────────────────

  async function render() {
    const app = document.getElementById('app');
    app.innerHTML = '<div class="loading-screen"><div class="spinner"></div></div>';

    try {
      const data = await API.fetchEmailDrafts();
      _drafts   = data.emails || [];
      _approved = new Set();
      _rejected = new Set();
      _paint();
    } catch (err) {
      app.innerHTML = `<div class="empty-state"><p style="color:var(--red)">Napaka: ${err.message}</p></div>`;
    }
  }

  function _paint() {
    const app = document.getElementById('app');
    const remaining = _drafts.filter(e => !_approved.has(e.id) && !_rejected.has(e.id));
    const approvedCount = _approved.size;
    const total = _drafts.length;

    if (total === 0) {
      app.innerHTML = `
        <div class="emails-empty">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
            <polyline points="22,6 12,13 2,6"/>
          </svg>
          <p><strong>Ni email draftov</strong></p>
          <p style="margin-top:8px;font-size:0.85rem">Najprej generiraj emaile v zavihku Kampanja.</p>
          <button class="btn" style="margin-top:20px" onclick="App.go('campaign')">Kampanja →</button>
        </div>`;
      return;
    }

    app.innerHTML = `
      <div class="emails-toolbar">
        <div class="emails-toolbar-count">
          <strong>${remaining.length}</strong> čakajo ·
          <span style="color:var(--green)">${approvedCount} odobreno</span> ·
          <span style="color:var(--red)">${_rejected.size} zavrnjeno</span>
          &nbsp;/ skupaj ${total}
        </div>
        <button class="btn btn-ghost" style="font-size:0.8rem;padding:7px 12px" onclick="Emails._approveAll()">✓ Odobri vse</button>
        <button class="btn btn-ghost" style="font-size:0.8rem;padding:7px 12px;color:var(--red);border-color:var(--red)" onclick="Emails._rejectAll()">✗ Zavrni vse</button>
      </div>

      <div class="emails-list" id="emailsList">
        ${_drafts.map(e => _renderCard(e)).join('')}
      </div>

      ${approvedCount > 0 ? `
      <div class="emails-send-bar">
        <button class="btn" onclick="Emails._send()">
          📤 Pošlji ${approvedCount} odobrenih emailov
        </button>
      </div>` : ''}
    `;
  }

  function _renderCard(email) {
    const approved = _approved.has(email.id);
    const rejected = _rejected.has(email.id);
    const cls      = approved ? ' approved' : rejected ? ' rejected' : '';
    const pColor   = PRIORITY_COLORS[email.priority] || 'muted';
    const flag     = FLAG[email.country] || '🌍';
    const bodyPreview = (email.body || '').substring(0, 220);
    const hasMore     = (email.body || '').length > 220;

    return `
    <div class="email-card${cls}" id="ecard-${email.id}">
      <div class="email-card-header">
        <div class="email-card-meta">
          <div class="email-card-company">
            ${flag} ${_esc(email.company_name || '—')}
            <span class="badge badge-${pColor}" style="font-size:0.68rem;margin-left:6px">${email.priority || ''}</span>
            ${approved ? '<span style="color:var(--green);font-size:0.78rem;margin-left:4px">✓ Odobreno</span>' : ''}
            ${rejected ? '<span style="color:var(--red);font-size:0.78rem;margin-left:4px">✗ Zavrnjeno</span>' : ''}
          </div>
          <div class="email-card-sub">📧 ${_esc(email.recipient_email || '')} &nbsp;·&nbsp; ${_esc(email.city || '')} &nbsp;·&nbsp; ${email.template_type || ''}</div>
        </div>
      </div>

      <div class="email-card-subject">${_esc(email.subject || '(brez zadeve)')}</div>

      <div class="email-card-body" id="ebody-${email.id}">${_esc(bodyPreview)}${hasMore ? '…' : ''}</div>
      ${hasMore ? `<button class="email-toggle-body" onclick="Emails._toggleBody(${email.id})">Pokaži celoten email ▼</button>` : ''}

      ${!approved && !rejected ? `
      <div class="email-card-actions">
        <button class="btn-approve" onclick="Emails._approve(${email.id})">✓ Odobri</button>
        <button class="btn-reject"  onclick="Emails._reject(${email.id})">✗ Zavrni</button>
      </div>` : ''}
    </div>`;
  }

  // ── Akcije ────────────────────────────────────────────────────────────────

  async function _approve(id) {
    try {
      await API.approveEmail(id);
      _approved.add(id);
      _updateCard(id);
      App.toast('Email odobren ✓', 'success');
    } catch (err) {
      App.toast('Napaka: ' + err.message, 'error');
    }
  }

  async function _reject(id) {
    try {
      await API.rejectEmail(id);
      _rejected.add(id);
      _updateCard(id);
      App.toast('Email zavrnjen', '');
    } catch (err) {
      App.toast('Napaka: ' + err.message, 'error');
    }
  }

  async function _approveAll() {
    try {
      const res = await API.approveAllEmails();
      App.toast(`Vsi emaili odobreni (${res.approved}) ✓`, 'success');
      await render();
    } catch (err) {
      App.toast('Napaka: ' + err.message, 'error');
    }
  }

  async function _rejectAll() {
    if (!confirm(`Zavrni vseh ${_drafts.length} emailov? To jih ne bo izbrisalo, samo ne bodo poslani.`)) return;
    let count = 0;
    for (const e of _drafts) {
      if (!_approved.has(e.id) && !_rejected.has(e.id)) {
        try { await API.rejectEmail(e.id); _rejected.add(e.id); count++; } catch {}
      }
    }
    App.toast(`${count} emailov zavrnjenih`, '');
    _repaintToolbar();
  }

  async function _send() {
    const approved = _approved.size;
    if (approved === 0) { App.toast('Najprej odobri vsaj en email', 'error'); return; }
    if (!confirm(`Pošlji ${approved} odobrenih emailov?`)) return;
    try {
      await API.triggerSend({ daily_limit: approved, dry_run: false });
      App.toast(`Pošiljanje ${approved} emailov zaganjam... ✓`, 'success');
      setTimeout(() => App.go('campaign'), 1500);
    } catch (err) {
      App.toast('Napaka: ' + err.message, 'error');
    }
  }

  function _toggleBody(id) {
    const el  = document.getElementById(`ebody-${id}`);
    const btn = el && el.nextElementSibling;
    const email = _drafts.find(e => e.id === id);
    if (!el || !email) return;
    const expanded = el.classList.toggle('expanded');
    if (expanded) {
      el.textContent = email.body || '';
      if (btn) btn.textContent = 'Skrij ▲';
    } else {
      el.textContent = (email.body || '').substring(0, 220) + ((email.body || '').length > 220 ? '…' : '');
      if (btn) btn.textContent = 'Pokaži celoten email ▼';
    }
  }

  // ── Pomožne ───────────────────────────────────────────────────────────────

  function _updateCard(id) {
    const card = document.getElementById(`ecard-${id}`);
    if (!card) { _repaintToolbar(); return; }
    const email = _drafts.find(e => e.id === id);
    if (email) card.outerHTML = _renderCard(email);
    _repaintToolbar();
  }

  function _repaintToolbar() {
    const toolbar = document.querySelector('.emails-toolbar .emails-toolbar-count');
    if (!toolbar) return;
    const remaining = _drafts.filter(e => !_approved.has(e.id) && !_rejected.has(e.id));
    toolbar.innerHTML = `<strong>${remaining.length}</strong> čakajo ·
      <span style="color:var(--green)">${_approved.size} odobreno</span> ·
      <span style="color:var(--red)">${_rejected.size} zavrnjeno</span>
      &nbsp;/ skupaj ${_drafts.length}`;
    // Update send bar
    const sendBar = document.querySelector('.emails-send-bar button');
    if (sendBar) sendBar.textContent = `📤 Pošlji ${_approved.size} odobrenih emailov`;
    else if (_approved.size > 0) _paint();
  }

  function _esc(s) {
    return String(s)
      .replace(/&/g,'&amp;')
      .replace(/</g,'&lt;')
      .replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;');
  }

  return { render, _approve, _reject, _approveAll, _rejectAll, _send, _toggleBody };
})();
