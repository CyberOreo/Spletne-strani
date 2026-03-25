// Campaign view — Scraping + pošiljanje
const Campaign = (() => {
  const COUNTRIES = [
    { code: 'si', name: 'Slovenija 🇸🇮' }, { code: 'hr', name: 'Hrvaška 🇭🇷' },
    { code: 'de', name: 'Nemčija 🇩🇪' }, { code: 'at', name: 'Avstrija 🇦🇹' },
    { code: 'it', name: 'Italija 🇮🇹' }, { code: 'cz', name: 'Češka 🇨🇿' },
    { code: 'hu', name: 'Madžarska 🇭🇺' }, { code: 'pl', name: 'Poljska 🇵🇱' },
    { code: 'ro', name: 'Romunija 🇷🇴' },
  ];

  const INDUSTRIES = [
    'vodovodarska dela', 'elektroinštalacije', 'frizerski salon', 'restavracija',
    'zobozdravstvene storitve', 'fitnes studio', 'avtomehanik', 'računovodstvo',
    'gradbena dela', 'krovstvo', 'mizarstvo', 'slikopleskarska dela',
    'kozmetični salon', 'pravne storitve', 'nepremičnine',
  ];

  async function render() {
    const app = document.getElementById('app');

    app.innerHTML = `
      <!-- Scraping -->
      <div class="section-header">Scraping</div>
      <div class="card" style="margin-top:0">
        <div class="form-group" style="margin:0 0 12px">
          <label class="form-label">Država</label>
          <select class="form-select" id="scrapeCountry">
            ${COUNTRIES.map((c) => `<option value="${c.code}">${c.name}</option>`).join('')}
          </select>
        </div>
        <div class="form-group" style="margin:0 0 12px">
          <label class="form-label">Dejavnost</label>
          <select class="form-select" id="scrapeIndustry">
            ${INDUSTRIES.map((i) => `<option value="${i}">${i}</option>`).join('')}
          </select>
        </div>
        <div class="form-group" style="margin:0 0 16px">
          <label class="form-label">Limit <span id="scrapeLimitVal">100</span></label>
          <input type="range" id="scrapeLimit" min="10" max="500" step="10" value="100"
            oninput="document.getElementById('scrapeLimitVal').textContent=this.value"
            style="width:100%;accent-color:var(--primary-light)">
        </div>
        <button class="btn btn-primary btn-full" id="scrapeBtn" onclick="Campaign._scrape()">
          Začni scraping
        </button>
        <div id="scrapeStatus" style="margin-top:10px;font-size:0.82rem;color:var(--text-muted);min-height:20px"></div>
      </div>

      <!-- Kvalifikacija -->
      <div class="section-header">Kvalifikacija & Emaili</div>
      <div class="card" style="margin-top:0">
        <div style="display:flex;gap:8px">
          <button class="btn btn-ghost" style="flex:1" id="qualifyBtn" onclick="Campaign._qualify()">
            Kvalificiraj
          </button>
          <button class="btn btn-ghost" style="flex:1" id="genEmailsBtn" onclick="Campaign._generateEmails()">
            Generiraj emaile
          </button>
        </div>
        <div id="qualifyStatus" style="margin-top:10px;font-size:0.82rem;color:var(--text-muted);min-height:20px"></div>
      </div>

      <!-- Pošiljanje -->
      <div class="section-header">Pošiljanje emailov</div>
      <div class="card" style="margin-top:0">
        <div class="form-group" style="margin:0 0 12px">
          <label class="form-label">Dnevni limit <span id="sendLimitVal">500</span></label>
          <input type="range" id="sendLimit" min="50" max="3000" step="50" value="500"
            oninput="document.getElementById('sendLimitVal').textContent=this.value"
            style="width:100%;accent-color:var(--primary-light)">
        </div>
        <div class="form-toggle">
          <span style="font-size:0.9rem">Dry run (brez dejanskega pošiljanja)</span>
          <label class="toggle-switch">
            <input type="checkbox" id="dryRunToggle">
            <span class="toggle-slider"></span>
          </label>
        </div>
        <button class="btn btn-primary btn-full" style="margin-top:12px" id="sendBtn" onclick="Campaign._send()">
          Pošlji emaile
        </button>
        <div id="sendStatus" style="margin-top:10px;font-size:0.82rem;color:var(--text-muted);min-height:20px"></div>
      </div>

      <!-- Follow-up -->
      <div class="section-header">Follow-up</div>
      <div class="card" style="margin-top:0">
        <div style="font-size:0.85rem;color:var(--text-muted);margin-bottom:12px">
          Generiraj follow-up emaile za leade brez odgovora po 5+ dneh.
        </div>
        <button class="btn btn-ghost btn-full" id="followupBtn" onclick="Campaign._followup()">
          Generiraj follow-up emaile
        </button>
        <div id="followupStatus" style="margin-top:10px;font-size:0.82rem;color:var(--text-muted);min-height:20px"></div>
      </div>
    `;
  }

  function _setStatus(elId, msg, color) {
    const el = document.getElementById(elId);
    if (el) el.innerHTML = `<span style="color:var(--${color || 'text-muted'})">${msg}</span>`;
  }

  async function _scrape() {
    const country = document.getElementById('scrapeCountry')?.value;
    const industry = document.getElementById('scrapeIndustry')?.value;
    const limit = parseInt(document.getElementById('scrapeLimit')?.value || '100');
    const btn = document.getElementById('scrapeBtn');
    if (btn) btn.disabled = true;
    _setStatus('scrapeStatus', 'Scraping v teku...', 'yellow');
    try {
      const res = await API.triggerScrape({ country, industry, limit });
      _setStatus('scrapeStatus', res.message || 'Scraping zagnan', 'green');
      App.toast('Scraping zagnan', 'success');
    } catch (e) {
      _setStatus('scrapeStatus', 'Napaka: ' + e.message, 'red');
      App.toast('Napaka: ' + e.message, 'error');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function _qualify() {
    const btn = document.getElementById('qualifyBtn');
    if (btn) btn.disabled = true;
    _setStatus('qualifyStatus', 'Kvalifikacija...', 'yellow');
    try {
      const res = await API.triggerQualify();
      _setStatus('qualifyStatus', `Kvalificirano: ${res.qualified || 0} · Diskvalificirano: ${res.disqualified || 0}`, 'green');
      App.toast('Kvalifikacija končana', 'success');
    } catch (e) {
      _setStatus('qualifyStatus', 'Napaka: ' + e.message, 'red');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function _generateEmails() {
    const btn = document.getElementById('genEmailsBtn');
    if (btn) btn.disabled = true;
    _setStatus('qualifyStatus', 'Generacija emailov...', 'yellow');
    try {
      const res = await API.generateEmails();
      _setStatus('qualifyStatus', `Emailov generirano: ${res.generated || 0}`, 'green');
      App.toast('Emaili generirani', 'success');
    } catch (e) {
      _setStatus('qualifyStatus', 'Napaka: ' + e.message, 'red');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function _send() {
    const daily_limit = parseInt(document.getElementById('sendLimit')?.value || '500');
    const dry_run = document.getElementById('dryRunToggle')?.checked || false;
    const btn = document.getElementById('sendBtn');
    if (btn) btn.disabled = true;
    _setStatus('sendStatus', 'Pošiljanje...', 'yellow');
    try {
      const res = await API.triggerSend({ daily_limit, dry_run });
      _setStatus('sendStatus', res.message || 'Pošiljanje zagnjeno', 'green');
      App.toast('Pošiljanje zagnjeno', 'success');
    } catch (e) {
      _setStatus('sendStatus', 'Napaka: ' + e.message, 'red');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function _followup() {
    const btn = document.getElementById('followupBtn');
    if (btn) btn.disabled = true;
    _setStatus('followupStatus', 'Generacija follow-up emailov...', 'yellow');
    try {
      const res = await API.triggerFollowup(5);
      _setStatus('followupStatus', `Follow-up emailov: ${res.generated || 0}`, 'green');
      App.toast('Follow-up emaili generirani', 'success');
    } catch (e) {
      _setStatus('followupStatus', 'Napaka: ' + e.message, 'red');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  return { render, _scrape, _qualify, _generateEmails, _send, _followup };
})();
