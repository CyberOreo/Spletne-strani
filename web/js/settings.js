// Settings view
const Settings = (() => {

  async function render() {
    const app = document.getElementById('app');
    app.innerHTML = '<div class="loading-screen"><div class="spinner"></div></div>';

    let cfg = {};
    try { cfg = await API.fetchSettings(); } catch (_) {}

    app.innerHTML = `

      <!-- ── EMAIL NASTAVITVE ── -->
      <div class="section-header">Email nastavitve</div>
      <div class="card" style="margin-top:0">

        <div class="settings-row">
          <div class="form-group">
            <label class="form-label">SMTP strežnik</label>
            <input class="form-input" id="s_smtp_host" type="text"
              placeholder="smtp.gmail.com" value="${_esc(cfg.smtp_host)}">
            <div class="form-hint">Gmail: smtp.gmail.com · Outlook: smtp-mail.outlook.com</div>
          </div>
          <div class="form-group" style="max-width:100px">
            <label class="form-label">Port</label>
            <input class="form-input" id="s_smtp_port" type="number"
              placeholder="587" value="${_esc(cfg.smtp_port || '587')}">
          </div>
        </div>

        <div class="form-group">
          <label class="form-label">Email naslov (pošiljatelj)</label>
          <input class="form-input" id="s_smtp_user" type="email"
            placeholder="tvoj@gmail.com" value="${_esc(cfg.smtp_user)}"
            autocomplete="email" autocapitalize="none">
        </div>

        <div class="form-group">
          <label class="form-label">Geslo / App Password</label>
          <div style="position:relative">
            <input class="form-input" id="s_smtp_password" type="password"
              placeholder="${cfg.smtp_password ? '••••••••  (nastavljeno)' : 'Vnesi geslo'}"
              autocomplete="new-password" style="padding-right:44px">
            <button onclick="Settings._togglePw()" style="position:absolute;right:10px;top:50%;transform:translateY(-50%);background:none;border:none;color:var(--text-muted);cursor:pointer;font-size:1rem;padding:4px" title="Pokaži/skrij">👁</button>
          </div>
          <div class="form-hint">
            Gmail zahteva <strong style="color:var(--text)">App Password</strong> (ne navadnega gesla).<br>
            Gmail → Nastavitve → Varnost → 2-koračna verif. → App passwords
          </div>
        </div>

        <div class="form-group">
          <label class="form-label">Ime pošiljatelja</label>
          <input class="form-input" id="s_sender_name" type="text"
            placeholder="Janez Novak" value="${_esc(cfg.sender_name)}">
        </div>

        <div class="form-group">
          <label class="form-label">Reply-To (neobvezno)</label>
          <input class="form-input" id="s_reply_to" type="email"
            placeholder="isto kot email, ali drug naslov" value="${_esc(cfg.reply_to)}"
            autocomplete="email" autocapitalize="none">
        </div>

        <div style="display:flex;gap:8px;margin-top:4px">
          <button class="btn btn-primary" style="flex:1" onclick="Settings._save()">
            💾 Shrani nastavitve
          </button>
          <button class="btn btn-ghost" onclick="Settings._testSMTP()" title="Pošlje testni email na tvoj naslov">
            Testiraj
          </button>
        </div>
        <div id="smtpStatus" style="margin-top:10px;font-size:0.82rem;min-height:18px"></div>
      </div>

      <!-- ── URNIK ── -->
      <div class="section-header">Overnight urnik</div>
      <div class="card" style="margin-top:0">

        <div class="settings-row">
          <div class="form-group">
            <label class="form-label">🌙 Scraping ob</label>
            <input class="form-input" id="s_scrape_time" type="time"
              value="${_esc(cfg.overnight_scrape_time || '22:00')}">
          </div>
          <div class="form-group">
            <label class="form-label">☀️ Pošiljanje ob</label>
            <input class="form-input" id="s_send_time" type="time"
              value="${_esc(cfg.overnight_send_time || '08:00')}">
          </div>
        </div>

        <div class="settings-row">
          <div class="form-group">
            <label class="form-label">Pošiljaj od</label>
            <input class="form-input" id="s_win_start" type="time"
              value="${_esc(cfg.send_window_start || '07:00')}">
          </div>
          <div class="form-group">
            <label class="form-label">Pošiljaj do</label>
            <input class="form-input" id="s_win_end" type="time"
              value="${_esc(cfg.send_window_end || '18:00')}">
          </div>
        </div>

        <div class="form-group">
          <label class="form-label">Dnevna omejitev emailov</label>
          <input class="form-input" id="s_daily_limit" type="number"
            placeholder="3000" value="${_esc(cfg.daily_limit || '3000')}" min="1" max="10000">
          <div class="form-hint">Priporočeno: max 500/dan za nov Gmail račun, 3000+ za stare</div>
        </div>

        <button class="btn btn-primary btn-full" onclick="Settings._save()">💾 Shrani urnik</button>
        <div id="scheduleStatus" style="margin-top:10px;font-size:0.82rem;min-height:18px"></div>
      </div>

      <!-- ── OPCIJSKO ── -->
      <div class="section-header">Opcijsko</div>
      <div class="card" style="margin-top:0">
        <div class="form-group">
          <label class="form-label">SerpAPI ključ (Google Maps)</label>
          <input class="form-input" id="s_serpapi" type="password"
            placeholder="${cfg.serpapi_key ? '••••••••  (nastavljeno)' : 'Vnesi ključ...'}"
            autocomplete="new-password">
          <div class="form-hint">Brez ključa Maps scraper ne deluje. Dobis na serpapi.com (~$50/mes)</div>
        </div>
        <button class="btn btn-ghost btn-full" onclick="Settings._save()">💾 Shrani</button>
      </div>

      <!-- ── API STREŽNIK ── -->
      <div class="section-header">API strežnik</div>
      <div class="card" style="margin-top:0">
        <div class="form-group" style="margin:0 0 12px">
          <label class="form-label">API URL</label>
          <input class="form-input" id="apiURLInput" type="url"
            placeholder="http://192.168.1.100:8000"
            value="${_esc(API.getBaseURL())}">
          <div class="form-hint">Pusti prazno, če je PWA na istem računalniku kot strežnik.</div>
        </div>
        <div style="display:flex;gap:8px">
          <button class="btn btn-primary" style="flex:1" onclick="Settings._saveURL()">Shrani URL</button>
          <button class="btn btn-ghost" onclick="Settings._testAPI()">Testiraj</button>
        </div>
        <div id="apiTestStatus" style="margin-top:10px;font-size:0.82rem;min-height:20px"></div>
      </div>

      <!-- ── IOS ── -->
      <div class="section-header">iOS namestitev</div>
      <div class="card" style="margin-top:0">
        <p style="font-size:0.88rem;line-height:1.8;color:var(--text-muted)">
          1. Odpri Safari na iPhonu in pojdi na ta naslov<br>
          2. Tapni gumb <strong style="color:var(--text)">Deli</strong> (kvadrat s puščico)<br>
          3. Izberi <strong style="color:var(--text)">Dodaj na začetni zaslon</strong><br>
          4. Potrdi z <strong style="color:var(--text)">Dodaj</strong>
        </p>
      </div>

      <!-- ── VZDRŽEVANJE ── -->
      <div class="section-header">Vzdrževanje</div>
      <div class="card" style="margin-top:0">
        <div style="font-size:0.85rem;color:var(--text-muted);margin-bottom:12px">
          GDPR: Izbriši stare zapise (starejše od 12 mesecev).
        </div>
        <button class="btn btn-danger btn-full" onclick="Settings._cleanup()">
          GDPR čiščenje (12 mes.)
        </button>
        <div id="cleanupStatus" style="margin-top:10px;font-size:0.82rem;min-height:20px"></div>
      </div>

      <!-- ── O APLIKACIJI ── -->
      <div class="card" style="font-size:0.85rem;color:var(--text-muted);line-height:1.7">
        <strong style="color:var(--text)">LeadGen EU</strong> v1.0.0<br>
        B2B Lead Generation · 10 držav · 3.000 leadov/dan<br><br>
        <a href="/docs" target="_blank" style="color:var(--primary-light)">API dokumentacija (Swagger)</a>
      </div>
    `;
  }

  // ── Shrani SMTP + urnik ───────────────────────────────────────────────────

  async function _save() {
    const pw = document.getElementById('s_smtp_password')?.value?.trim();
    const serpapi = document.getElementById('s_serpapi')?.value?.trim();

    const body = {
      smtp_host:             _val('s_smtp_host'),
      smtp_port:             _val('s_smtp_port'),
      smtp_user:             _val('s_smtp_user'),
      sender_name:           _val('s_sender_name'),
      reply_to:              _val('s_reply_to'),
      daily_limit:           _val('s_daily_limit'),
      send_window_start:     _val('s_win_start'),
      send_window_end:       _val('s_win_end'),
      overnight_scrape_time: _val('s_scrape_time'),
      overnight_send_time:   _val('s_send_time'),
    };
    if (pw) body.smtp_password = pw;
    if (serpapi) body.serpapi_key = serpapi;

    const st = document.getElementById('smtpStatus');
    const ss = document.getElementById('scheduleStatus');
    if (st) st.innerHTML = '<span style="color:var(--yellow)">Shranjujem...</span>';

    try {
      const res = await API.saveSettings(body);
      const msg = `<span style="color:var(--green)">✓ Shranjeno (${res.updated?.length || 0} polj)</span>`;
      if (st) st.innerHTML = msg;
      if (ss) ss.innerHTML = msg;
      App.toast('Nastavitve shranjene ✓', 'success');
      // Počisti geslo polje
      const pwEl = document.getElementById('s_smtp_password');
      if (pwEl) pwEl.value = '';
      const saEl = document.getElementById('s_serpapi');
      if (saEl) saEl.value = '';
    } catch (e) {
      const msg = `<span style="color:var(--red)">✗ Napaka: ${e.message}</span>`;
      if (st) st.innerHTML = msg;
      App.toast('Napaka: ' + e.message, 'error');
    }
  }

  // ── Testiraj SMTP ─────────────────────────────────────────────────────────

  async function _testSMTP() {
    const el = document.getElementById('smtpStatus');
    if (el) el.innerHTML = '<span style="color:var(--yellow)">Pošiljam testni email...</span>';
    try {
      const res = await API.testSMTP();
      if (el) el.innerHTML = `<span style="color:var(--green)">✓ ${res.message}</span>`;
      App.toast(res.message, 'success');
    } catch (e) {
      if (el) el.innerHTML = `<span style="color:var(--red)">✗ ${e.message}</span>`;
      App.toast('SMTP napaka: ' + e.message, 'error');
    }
  }

  // ── API URL ───────────────────────────────────────────────────────────────

  function _saveURL() {
    const val = document.getElementById('apiURLInput')?.value?.trim() || '';
    API.setBaseURL(val);
    App.toast('API URL shranjen', 'success');
    App.checkAPI();
  }

  async function _testAPI() {
    const el = document.getElementById('apiTestStatus');
    if (el) el.innerHTML = '<span style="color:var(--yellow)">Testiram...</span>';
    try {
      const stats = await API.fetchStats();
      if (el) el.innerHTML = `<span style="color:var(--green)">✓ OK · ${stats.total_leads} leadov v bazi</span>`;
    } catch (e) {
      if (el) el.innerHTML = `<span style="color:var(--red)">✗ ${e.message}</span>`;
    }
  }

  // ── GDPR ──────────────────────────────────────────────────────────────────

  async function _cleanup() {
    if (!confirm('GDPR: Izbrisati stare zapise (>12 mesecev)?')) return;
    try {
      const res = await API.cleanup(12);
      document.getElementById('cleanupStatus').innerHTML =
        `<span style="color:var(--green)">Izbrisano: ${res.deleted} zapisov</span>`;
      App.toast(`GDPR: Izbrisano ${res.deleted} zapisov`, 'success');
    } catch (e) {
      App.toast('Napaka: ' + e.message, 'error');
    }
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  function _togglePw() {
    const el = document.getElementById('s_smtp_password');
    if (el) el.type = el.type === 'password' ? 'text' : 'password';
  }

  function _val(id) {
    return document.getElementById(id)?.value?.trim() || '';
  }

  function _esc(s) {
    return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  return { render, _save, _testSMTP, _saveURL, _testAPI, _cleanup, _togglePw };
})();
