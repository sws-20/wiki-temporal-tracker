// ── State ──────────────────────────────────────────────────────────────────
let allData = [];
let filteredData = [];
let chart = null;
let sortCol = 'timestamp';
let sortDir = 1;
let tableFilter = '';

// ── Anomaly detection (IQR method) ─────────────────────────────────────────
function detectAnomalies(data) {
  if (data.length < 4) return data.map(d => ({ ...d, isAnomaly: false }));
  const vals = [...data].map(d => d.value).sort((a, b) => a - b);
  const q1 = vals[Math.floor(vals.length * 0.25)];
  const q3 = vals[Math.floor(vals.length * 0.75)];
  const iqr = q3 - q1;
  const lo = q1 - 1.5 * iqr;
  const hi = q3 + 1.5 * iqr;
  return data.map(d => ({ ...d, isAnomaly: d.value < lo || d.value > hi }));
}

// ── Metrics computation ─────────────────────────────────────────────────────
function computeMetrics(data) {
  if (data.length < 2) return { velocity: 0, stability: 0, anomalies: 0 };

  const sorted = [...data].sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
  const first = sorted[0], last = sorted[sorted.length - 1];
  const months = (new Date(last.timestamp) - new Date(first.timestamp)) / (1000 * 60 * 60 * 24 * 30.44);
  const velocity = months > 0 ? (last.value - first.value) / months : 0;

  let changes = 0;
  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i].value !== sorted[i - 1].value) changes++;
  }
  const stability = months > 0 ? (changes / months).toFixed(2) : 0;
  const anomalies = data.filter(d => d.isAnomaly).length;

  return { velocity, stability, anomalies };
}

// ── Format helpers ──────────────────────────────────────────────────────────
function fmtValue(v) {
  if (Math.abs(v) >= 1e9) return (v / 1e9).toFixed(2) + 'B';
  if (Math.abs(v) >= 1e6) return (v / 1e6).toFixed(2) + 'M';
  if (Math.abs(v) >= 1e3) return (v / 1e3).toFixed(1) + 'K';
  return v.toLocaleString();
}

function fmtVelocity(v) {
  const sign = v >= 0 ? '+' : '';
  return sign + fmtValue(v) + ' / mo';
}

// ── Chart ───────────────────────────────────────────────────────────────────
function renderChart(data, entity, attribute) {
  const sorted = [...data].sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
  const labels = sorted.map(d => d.timestamp);
  const values = sorted.map(d => d.value);

  const normalPoints = sorted.map((d, i) => d.isAnomaly ? null : { x: labels[i], y: d.value });
  const anomalyPoints = sorted.map((d, i) => d.isAnomaly ? { x: labels[i], y: d.value } : null);

  const ctx = document.getElementById('timelineChart').getContext('2d');
  if (chart) chart.destroy();

  chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: attribute,
          data: values,
          borderColor: '#6c63ff',
          backgroundColor: 'rgba(108,99,255,0.08)',
          borderWidth: 2,
          pointRadius: 4,
          pointBackgroundColor: sorted.map(d => d.isAnomaly ? '#ff4d6d' : '#6c63ff'),
          pointBorderColor: sorted.map(d => d.isAnomaly ? '#ff4d6d' : '#6c63ff'),
          pointRadius: sorted.map(d => d.isAnomaly ? 7 : 4),
          tension: 0.35,
          fill: true,
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        title: {
          display: true,
          text: `Temporal Evolution of ${attribute} for ${entity || 'Entity'}`,
          color: '#e2e8f0',
          font: { size: 13, weight: '600' },
          padding: { bottom: 16 }
        },
        tooltip: {
          callbacks: {
            label: ctx => {
              const d = sorted[ctx.dataIndex];
              return [
                ` Value: ${fmtValue(d.value)} ${d.unit}`,
                ` Text: "${d.text}"`,
                d.isAnomaly ? ' ⚠ Anomaly' : ''
              ].filter(Boolean);
            }
          },
          backgroundColor: '#1a1d27',
          borderColor: '#2e3250',
          borderWidth: 1,
          titleColor: '#e2e8f0',
          bodyColor: '#8892a4',
        }
      },
      scales: {
        x: {
          ticks: { color: '#8892a4', maxRotation: 45, font: { size: 11 } },
          grid: { color: 'rgba(46,50,80,0.6)' }
        },
        y: {
          ticks: {
            color: '#8892a4',
            font: { size: 11 },
            callback: v => fmtValue(v)
          },
          grid: { color: 'rgba(46,50,80,0.6)' }
        }
      }
    }
  });
}

// ── Metrics cards ───────────────────────────────────────────────────────────
function renderMetrics(metrics) {
  document.getElementById('metricVelocity').textContent = fmtVelocity(metrics.velocity);
  document.getElementById('metricStability').textContent = metrics.stability;
  document.getElementById('metricAnomalies').textContent = metrics.anomalies;
}

// ── Table ───────────────────────────────────────────────────────────────────
function renderTable(data) {
  const tbody = document.getElementById('tableBody');
  let rows = [...data];

  // filter
  if (tableFilter) {
    const q = tableFilter.toLowerCase();
    rows = rows.filter(d =>
      d.timestamp.includes(q) ||
      d.text.toLowerCase().includes(q) ||
      d.attribute.toLowerCase().includes(q) ||
      String(d.value).includes(q)
    );
  }

  // sort
  rows.sort((a, b) => {
    let av = a[sortCol], bv = b[sortCol];
    if (sortCol === 'timestamp') { av = new Date(av); bv = new Date(bv); }
    if (sortCol === 'value') { av = Number(av); bv = Number(bv); }
    return av < bv ? -sortDir : av > bv ? sortDir : 0;
  });

  if (rows.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:30px;color:var(--text-muted)">No data found</td></tr>`;
    return;
  }

  tbody.innerHTML = rows.map(d => `
    <tr class="${d.isAnomaly ? 'anomaly-row' : ''}">
      <td>${d.timestamp}</td>
      <td>${fmtValue(d.value)}</td>
      <td>${d.unit}</td>
      <td>${d.text}</td>
      <td>${d.attribute}</td>
      <td><span class="badge ${d.isAnomaly ? 'badge-anomaly' : 'badge-normal'}">${d.isAnomaly ? '⚠ Anomaly' : '✓ Normal'}</span></td>
    </tr>
  `).join('');
}

// ── Sort headers ────────────────────────────────────────────────────────────
function initSortHeaders() {
  document.querySelectorAll('thead th[data-col]').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.dataset.col;
      if (sortCol === col) sortDir *= -1;
      else { sortCol = col; sortDir = 1; }
      document.querySelectorAll('thead th').forEach(t => t.classList.remove('active'));
      th.classList.add('active');
      th.querySelector('.sort-icon').textContent = sortDir === 1 ? '↑' : '↓';
      renderTable(filteredData);
    });
  });
}

// ── Load & render pipeline ──────────────────────────────────────────────────
function loadAndRender(data, entity, attribute) {
  // filter by attribute if specified
  filteredData = attribute
    ? data.filter(d => d.attribute.toLowerCase().includes(attribute.toLowerCase()))
    : data;

  if (filteredData.length === 0) {
    alert(`No data found for attribute "${attribute}". Try: net_worth, population`);
    return;
  }

  filteredData = detectAnomalies(filteredData);
  const metrics = computeMetrics(filteredData);

  renderChart(filteredData, entity, attribute || 'quantity');
  renderMetrics(metrics);
  renderTable(filteredData);

  // populate attribute dropdown from data
  const attrs = [...new Set(data.map(d => d.attribute))];
  const sel = document.getElementById('attrSelect');
  sel.innerHTML = '<option value="">All</option>' +
    attrs.map(a => `<option value="${a}" ${a === attribute ? 'selected' : ''}>${a}</option>`).join('');
}

// ── Fetch default data.json ─────────────────────────────────────────────────
async function fetchDefault() {
  try {
    const res = await fetch('data.json');
    if (!res.ok) throw new Error('Not found');
    allData = await res.json();
    const attr = document.getElementById('attrInput').value.trim() || allData[0]?.attribute || '';
    const entity = document.getElementById('entityInput').value.trim() || 'Entity';
    loadAndRender(allData, entity, attr);
  } catch (e) {
    console.warn('Could not load data.json:', e);
  }
}

// ── Events ──────────────────────────────────────────────────────────────────
document.getElementById('loadBtn').addEventListener('click', () => {
  const entity = document.getElementById('entityInput').value.trim();
  const attr = document.getElementById('attrInput').value.trim();
  if (allData.length === 0) { fetchDefault(); return; }
  loadAndRender(allData, entity, attr);
});

document.getElementById('attrSelect').addEventListener('change', e => {
  const entity = document.getElementById('entityInput').value.trim();
  document.getElementById('attrInput').value = e.target.value;
  loadAndRender(allData, entity, e.target.value);
});

document.getElementById('tableSearch').addEventListener('input', e => {
  tableFilter = e.target.value;
  renderTable(filteredData);
});

document.getElementById('uploadBtn').addEventListener('click', () => {
  document.getElementById('fileInput').click();
});

document.getElementById('fileInput').addEventListener('change', e => {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = ev => {
    try {
      allData = JSON.parse(ev.target.result);
      const attr = document.getElementById('attrInput').value.trim() || allData[0]?.attribute || '';
      const entity = document.getElementById('entityInput').value.trim() || file.name.replace('.json', '');
      loadAndRender(allData, entity, attr);
    } catch {
      alert('Invalid JSON file.');
    }
  };
  reader.readAsText(file);
  e.target.value = '';
});

document.getElementById('themeToggle').addEventListener('click', () => {
  document.body.classList.toggle('light');
  const btn = document.getElementById('themeToggle');
  btn.textContent = document.body.classList.contains('light') ? '🌙 Dark' : '☀️ Light';

  // update chart colors for light mode
  if (chart) {
    const isLight = document.body.classList.contains('light');
    const textColor = isLight ? '#1a1d27' : '#e2e8f0';
    const mutedColor = isLight ? '#6b7280' : '#8892a4';
    const gridColor = isLight ? 'rgba(0,0,0,0.08)' : 'rgba(46,50,80,0.6)';
    chart.options.plugins.title.color = textColor;
    chart.options.scales.x.ticks.color = mutedColor;
    chart.options.scales.y.ticks.color = mutedColor;
    chart.options.scales.x.grid.color = gridColor;
    chart.options.scales.y.grid.color = gridColor;
    chart.options.plugins.tooltip.backgroundColor = isLight ? '#fff' : '#1a1d27';
    chart.options.plugins.tooltip.titleColor = textColor;
    chart.update();
  }
});

// ── Init ────────────────────────────────────────────────────────────────────
initSortHeaders();
fetchDefault();
