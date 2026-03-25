// Settings view
const Settings = (() => {
  async function render() {
    const app = document.getElementById('app');
    const currentURL = API.getBaseURL() || '';

    app.innerHTML = `
      <div class="section-header">API strežnik</div>
      <div class="card" style="margin-top:0">
        <div class="form-group" style="margin:0 0 12px">
          <label class="form-label">API URL</label>
          <input class="form-input" id="apiURLInput" type="url"
            placeholder="http://192.168.1.100:8000"
            value="${_esc(currentURL)}">
          <div style="margin-top:6px;font-size:0.75rem;color:var(--text-muted)">
            Pusti prazno, če je PWA na istem strežniku kot API.
          </div>
        </div>
        <button class="btn btn-primary btn-full" onclick="Settings._saveURL()">Shrani URL</button>
        <button class="btn btn-ghost btn-full" style="margin-top:8px" onclick="Settings._testAPI()">
          Testiraj povezavo
        </button>
        <div id="apiTestStatus" style="margin-top:10px;font-size:0.82rem;min-height:20px"></div>
      </div>

      <div class="section-header">iOS namestitev</div>
      <div class="card" style="margin-top:0">
        <p style="font-size:0.88rem;line-height:1.6;color:var(--text-muted)">
          Za namestitev kot aplikacija na začetni zaslon:<br><br>
          1. Odpri Safari na iPhonu<br>
          2. Obišči ta naslov<br>
          3. Tapni gumb <strong style="color:var(--text)">Deli</strong> (kvadrat s puščico navzgor)<br>
          4. Izberi <strong style="color:var(--text)">Dodaj na začetni zaslon</strong><br>
          5. Potrdi z <strong style="color:var(--text)">Dodaj</strong>
        </p>
      </div>

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

      <div class="section-header">O aplikaciji</div>
      <div class="card" style="margin-top:0;font-size:0.85rem;color:var(--text-muted);line-height:1.7">
        <strong style="color:var(--text)">LeadGen EU</strong> v1.0.0<br>
        B2B Lead Generation System za EU<br>
        3.000 leadov/dan · 3.000 emailov/dan · 10 držav<br><br>
        <a href="/docs" target="_blank" style="color:var(--primary-light)">API dokumentacija (Swagger)</a>
      </div>
    `;
  }

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
      if (el) el.innerHTML = `<span style="color:var(--green)">✓ Povezava OK · ${stats.total_leads} leadov</span>`;
    } catch (e) {
      if (el) el.innerHTML = `<span style="color:var(--red)">✗ Napaka: ${e.message}</span>`;
    }
  }

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

  function _esc(s) {
    return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  return { render, _saveURL, _testAPI, _cleanup };
})();
