// Lead detail view
const LeadDetail = (() => {
  const STATUS_OPTS = ['ČAKA', 'POSLANO', 'ODPRT', 'ODGOVORIL', 'ZAVRNIL', 'KONVERTIRAN'];

  function scoreClass(s) {
    if (s >= 7) return 'high';
    if (s >= 4) return 'medium';
    return 'low';
  }

  function wsBadge(ws) {
    const map = { none: ['red', 'Ni strani'], outdated: ['yellow', 'Zastarela'], modern: ['green', 'Moderna'] };
    const [cls, label] = map[ws] || ['muted', ws || '—'];
    return `<span class="badge badge-${cls}">${label}</span>`;
  }

  function _esc(s) {
    return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  async function render(leadId) {
    const app = document.getElementById('app');
    const header = document.getElementById('headerTitle');
    let lead, emails;
    try {
      [lead, emails] = await Promise.all([
        API.fetchLead(leadId),
        API.fetchLeadEmails(leadId),
      ]);
    } catch (e) {
      app.innerHTML = `<div class="empty-state"><p style="color:var(--red)">Lead ne obstaja ali napaka: ${e.message}</p></div>`;
      return;
    }

    if (header) header.textContent = lead.company_name || leadId;

    const score = lead.qualification_score || 0;
    const draft = (emails.emails || []).find((e) => e.template_type !== 'PREVIEW');
    const phone = lead.phone;
    const email = lead.email;

    app.innerHTML = `
      <!-- Contact actions -->
      <div class="contact-actions" style="padding-top:12px">
        ${phone ? `<a class="contact-btn" href="tel:${_esc(phone)}">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.69 12 19.79 19.79 0 0 1 1.6 3.35 2 2 0 0 1 3.59 1h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L7.91 8.6a16 16 0 0 0 5.49 5.49l.96-.96a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>
          </svg>
          Pokliči
        </a>` : ''}
        ${email ? `<a class="contact-btn" href="mailto:${_esc(email)}">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
            <polyline points="22,6 12,13 2,6"/>
          </svg>
          Email
        </a>` : ''}
        <button class="contact-btn" onclick="LeadDetail._preview('${_esc(leadId)}')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
            <circle cx="12" cy="12" r="3"/>
          </svg>
          Preview
        </button>
      </div>

      <!-- Score + info -->
      <div class="card" style="margin-top:0">
        <div class="score-ring-wrap">
          <div class="score-ring ${scoreClass(score)}">${score}</div>
          <div>
            <div style="font-size:0.9rem;color:var(--text-muted)">Kvalifikacijska ocena</div>
            <div style="margin-top:4px">${wsBadge(lead.website_status)}</div>
          </div>
        </div>
        <div class="divider"></div>
        ${[
          ['Podjetje', lead.company_name],
          ['Dejavnost', lead.activity],
          ['Kraj', lead.city],
          ['Regija', lead.region],
          ['Država', (lead.country || '').toUpperCase() || '—'],
          ['Naslov', lead.address],
          ['SKD koda', lead.skd_code],
          ['Vir podatkov', lead.data_source],
          ['Prioriteta', lead.priority],
          ['Priporočen template', lead.recommended_template],
        ].filter(([, v]) => v).map(([k, v]) => `
          <div class="detail-row">
            <span class="detail-key">${k}</span>
            <span class="detail-val">${_esc(v)}</span>
          </div>`).join('')}
      </div>

      <!-- Status sprememba -->
      <div class="section-header">Posodobi status</div>
      <div style="padding:0 16px;display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px">
        ${STATUS_OPTS.map((s) => `
          <button class="pill ${lead.status === s ? 'active' : ''}"
            onclick="LeadDetail._setStatus('${leadId}','${s}')">
            ${s}
          </button>`).join('')}
      </div>

      <!-- Email preview -->
      ${draft ? `
        <div class="section-header">Email draft (${draft.template_type})</div>
        <div class="card" style="margin-top:0">
          <div style="font-size:0.8rem;color:var(--text-muted);margin-bottom:8px">Zadeva: ${_esc(draft.subject || '')}</div>
          <div class="email-preview">${_esc(draft.body || '')}</div>
        </div>
      ` : ''}

      <!-- Notes -->
      <div class="section-header">Opombe</div>
      <div class="form-group" style="margin-top:0">
        <textarea class="form-input" id="notesInput" rows="3" placeholder="Dodaj opombo..."
          style="resize:vertical">${_esc(lead.notes || '')}</textarea>
        <button class="btn btn-ghost btn-full" style="margin-top:8px"
          onclick="LeadDetail._saveNotes('${leadId}')">Shrani opombo</button>
      </div>

      <!-- Metadata -->
      <div style="padding:0 16px 24px;font-size:0.75rem;color:var(--text-muted)">
        ID: ${_esc(leadId)} · Dodan: ${(lead.created_at || '').slice(0, 10)}
      </div>
    `;
  }

  async function _setStatus(leadId, status) {
    try {
      await API.updateLead(leadId, { status });
      App.toast(`Status → ${status}`, 'success');
      render(leadId);
    } catch (e) {
      App.toast('Napaka: ' + e.message, 'error');
    }
  }

  async function _preview(leadId) {
    try {
      const res = await API.generatePreview(leadId);
      App.toast('Preview ustvarjen!', 'success');
      if (res.url) window.open(res.url, '_blank');
    } catch (e) {
      App.toast('Napaka: ' + e.message, 'error');
    }
  }

  async function _saveNotes(leadId) {
    const notes = document.getElementById('notesInput')?.value || '';
    try {
      await API.updateLead(leadId, { notes });
      App.toast('Opomba shranjena', 'success');
    } catch (e) {
      App.toast('Napaka: ' + e.message, 'error');
    }
  }

  return { render, _setStatus, _preview, _saveNotes };
})();
