// Reports view — KPI grafi (Chart.js)
const Reports = (() => {
  let _charts = [];

  function destroyCharts() {
    _charts.forEach((c) => { try { c.destroy(); } catch {} });
    _charts = [];
  }

  async function render() {
    const app = document.getElementById('app');

    let stats;
    try {
      stats = await API.fetchStats();
    } catch (e) {
      app.innerHTML = `<div class="empty-state"><p style="color:var(--red)">Napaka: ${e.message}</p></div>`;
      return;
    }

    destroyCharts();

    app.innerHTML = `
      <div class="section-header">KPI povzetek</div>
      <div class="card-grid" style="padding-top:0">
        <div class="kpi-card">
          <div class="kpi-value">${stats.emails_sent}</div>
          <div class="kpi-label">Poslano</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-value">${stats.emails_opened}</div>
          <div class="kpi-label">Odprtih</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-value">${stats.emails_replied}</div>
          <div class="kpi-label">Odgovorov</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-value green">${stats.converted || 0}</div>
          <div class="kpi-label">Konverzij</div>
        </div>
      </div>

      <div class="section-header">Statusi leadov</div>
      <div class="chart-wrap">
        <div class="chart-title">Porazdelitev leadov po statusu</div>
        <canvas id="statusChart" height="220"></canvas>
      </div>

      <div class="section-header">Funnel</div>
      <div class="chart-wrap">
        <div class="chart-title">Email funnel</div>
        <canvas id="funnelChart" height="200"></canvas>
      </div>

      <div style="padding:0 16px 16px">
        <button class="btn btn-ghost btn-full" onclick="API.exportCSV()">
          Izvozi CSV
        </button>
      </div>
    `;

    await window._loadChartJs();
    _renderCharts(stats);
  }

  function _renderCharts(stats) {
    Chart.defaults.color = '#8888aa';
    Chart.defaults.borderColor = '#2e2e50';

    // Status pie chart
    const byStatus = stats.by_status || {};
    const statusColors = {
      'ČAKA': '#8888aa', 'POSLANO': '#3a7ab5', 'ODPRT': '#eab308',
      'ODGOVORIL': '#22c55e', 'ZAVRNIL': '#ef4444', 'KONVERTIRAN': '#00e676',
    };
    const statusCtx = document.getElementById('statusChart');
    if (statusCtx) {
      const labels = Object.keys(byStatus);
      const c1 = new Chart(statusCtx, {
        type: 'doughnut',
        data: {
          labels,
          datasets: [{
            data: labels.map((l) => byStatus[l]),
            backgroundColor: labels.map((l) => statusColors[l] || '#555'),
            borderWidth: 0,
          }],
        },
        options: {
          plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, padding: 12 } } },
          cutout: '65%',
        },
      });
      _charts.push(c1);
    }

    // Funnel bar chart
    const funnelCtx = document.getElementById('funnelChart');
    if (funnelCtx) {
      const c2 = new Chart(funnelCtx, {
        type: 'bar',
        data: {
          labels: ['Skupaj leadov', 'Emailov poslanih', 'Odprtih', 'Odgovorov', 'Konverzij'],
          datasets: [{
            data: [stats.total_leads, stats.emails_sent, stats.emails_opened, stats.emails_replied, stats.converted || 0],
            backgroundColor: ['#2c5f8a', '#3a7ab5', '#eab308', '#22c55e', '#00e676'],
            borderRadius: 6,
          }],
        },
        options: {
          plugins: { legend: { display: false } },
          scales: {
            y: { beginAtZero: true, ticks: { maxTicksLimit: 5 } },
            x: { ticks: { font: { size: 10 } } },
          },
        },
      });
      _charts.push(c2);
    }
  }

  return { render };
})();
