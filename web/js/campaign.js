// Campaign view — poenostavljen: scraping vse EU, 3000 leadov, brez duplikatov
const Campaign = (() => {

  async function render() {
    const app = document.getElementById('app');

    app.innerHTML = `

      <!-- Scraping -->
      <div class="section-header">Scraping leadov</div>
      <div class="card" style="margin-top:0">
        <div class="campaign-info">
          <div class="campaign-info-row">
            <span class="ci-icon">🌍</span>
            <span>Vse EU države: SI · HR · AT · DE · IT · CZ · SK · HU · PL · RO</span>
          </div>
          <div class="campaign-info-row">
            <span class="ci-icon">🎯</span>
            <span>Cilj: <strong>3.000 novih leadov</strong> — brez duplikatov</span>
          </div>
          <div class="campaign-info-row">
            <span class="ci-icon">⏱</span>
            <span>Trajanje: ~30–60 min (teče v ozadju)</span>
          </div>
        </div>
        <button class="btn btn-primary btn-full" id="scrapeBtn" onclick="Campaign._scrape()">
          🔍 Začni scraping (3.000 leadov)
        </button>
        <div id="scrapeStatus" style="margin-top:10px;font-size:0.82rem;min-height:20px"></div>
      </div>

      <!-- Kvalifikacija & Emaili -->
      <div class="section-header">Kvalifikacija & Emaili</div>
      <div class="card" style="margin-top:0">
        <div style="font-size:0.82rem;color:var(--text-muted);margin-bottom:12px">
          Kvalificiraj scrapane leade in jim generiraj personalizirane emaile.
        </div>
        <div style="display:flex;gap:8px">
          <button class="btn btn-ghost" style="flex:1" id="qualifyBtn" onclick="Campaign._qualify()">
            ✓ Kvalificiraj
          </button>
          <button class="btn btn-ghost" style="flex:1" id="genEmailsBtn" onclick="Campaign._generateEmails()">
            ✉ Generiraj emaile
          </button>
        </div>
        <div id="qualifyStatus" style="margin-top:10px;font-size:0.82rem;min-height:20px"></div>
      </div>

      <!-- Pošiljanje -->
      <div class="section-header">Pošiljanje emailov</div>
      <div class="card" style="margin-top:0">
        <div class="campaign-info" style="margin-bottom:12px">
          <div class="campaign-info-row">
            <span class="ci-icon">🚀</span>
            <span>Pošlje do <strong>3.000 emailov/dan</strong> (nastavljivo v Nastavitvah)</span>
          </div>
          <div class="campaign-info-row">
            <span class="ci-icon">⏰</span>
            <span>Samodejno pošilja samo v delovnem času (07:00–18:00)</span>
          </div>
        </div>
        <button class="btn btn-primary btn-full" id="sendBtn" onclick="Campaign._send(false)">
          🚀 Pošlji emaile
        </button>
        <button class="btn btn-ghost btn-full" style="margin-top:8px" onclick="Campaign._send(true)">
          🧪 Test pošiljanje (brez dejanskega pošiljanja)
        </button>
        <div id="sendStatus" style="margin-top:10px;font-size:0.82rem;min-height:20px"></div>
      </div>

      <!-- Follow-up -->
      <div class="section-header">Follow-up</div>
      <div class="card" style="margin-top:0">
        <div style="font-size:0.82rem;color:var(--text-muted);margin-bottom:12px">
          Pošlje follow-up emaile leadom ki niso odgovorili po 5+ dneh.
        </div>
        <button class="btn btn-ghost btn-full" id="followupBtn" onclick="Campaign._followup()">
          🔄 Generiraj follow-up emaile
        </button>
        <div id="followupStatus" style="margin-top:10px;font-size:0.82rem;min-height:20px"></div>
      </div>

    `;
  }

  function _setStatus(elId, msg, color) {
    const el = document.getElementById(elId);
    if (el) el.innerHTML = `<span style="color:var(--${color || 'text-muted'})">${msg}</span>`;
  }

  async function _scrape() {
    const btn = document.getElementById('scrapeBtn');
    if (btn) btn.disabled = true;
    _setStatus('scrapeStatus', '⏳ Scraping zagnan — teče v ozadju, traja 30–60 min...', 'yellow');
    try {
      // Pošljemo prazen request — backend uporabi DAILY_BULK_CONFIG (vse EU, 3000 leadov)
      const res = await API.triggerScrape({ country: 'all', industry: '', limit: 3000 });
      _setStatus('scrapeStatus', '✓ ' + (res.message || 'Scraping zagnan'), 'green');
      App.toast('Scraping zagnan za vse EU države', 'success');
    } catch (e) {
      _setStatus('scrapeStatus', '✗ Napaka: ' + e.message, 'red');
      App.toast('Napaka: ' + e.message, 'error');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function _qualify() {
    const btn = document.getElementById('qualifyBtn');
    if (btn) btn.disabled = true;
    _setStatus('qualifyStatus', '⏳ Kvalifikacija...', 'yellow');
    try {
      const res = await API.triggerQualify();
      _setStatus('qualifyStatus', `✓ Kvalificirano: ${res.qualified || 0} · Izločeno: ${res.disqualified || 0}`, 'green');
      App.toast('Kvalifikacija končana', 'success');
    } catch (e) {
      _setStatus('qualifyStatus', '✗ Napaka: ' + e.message, 'red');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function _generateEmails() {
    const btn = document.getElementById('genEmailsBtn');
    if (btn) btn.disabled = true;
    _setStatus('qualifyStatus', '⏳ Generacija emailov...', 'yellow');
    try {
      const res = await API.generateEmails();
      _setStatus('qualifyStatus', `✓ Emailov generirano: ${res.generated || 0}`, 'green');
      App.toast('Emaili generirani', 'success');
    } catch (e) {
      _setStatus('qualifyStatus', '✗ Napaka: ' + e.message, 'red');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function _send(dry_run) {
    const btn = document.getElementById('sendBtn');
    if (btn) btn.disabled = true;
    _setStatus('sendStatus', dry_run ? '⏳ Test pošiljanje...' : '⏳ Pošiljanje...', 'yellow');
    try {
      const res = await API.triggerSend({ daily_limit: 3000, dry_run });
      _setStatus('sendStatus', '✓ ' + (res.message || 'Pošiljanje zagnjeno'), 'green');
      App.toast(dry_run ? 'Test pošiljanje zagnjeno' : 'Pošiljanje zagnjeno', 'success');
    } catch (e) {
      _setStatus('sendStatus', '✗ Napaka: ' + e.message, 'red');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function _followup() {
    const btn = document.getElementById('followupBtn');
    if (btn) btn.disabled = true;
    _setStatus('followupStatus', '⏳ Generacija follow-up emailov...', 'yellow');
    try {
      const res = await API.triggerFollowup(5);
      _setStatus('followupStatus', `✓ Follow-up emailov: ${res.generated || 0}`, 'green');
      App.toast('Follow-up emaili generirani', 'success');
    } catch (e) {
      _setStatus('followupStatus', '✗ Napaka: ' + e.message, 'red');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  return { render, _scrape, _qualify, _generateEmails, _send, _followup };
})();
