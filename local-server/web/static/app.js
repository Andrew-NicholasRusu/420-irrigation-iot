// Chart.js dashboard. Charts are created ONCE; refresh() only replaces their data.
const REFRESH_MS = 5000;
let minutes = 60;
let device = '';                       // '' = all devices
const deviceQuery = () => (device ? `&device=${encodeURIComponent(device)}` : '');

// SQLite stores 'YYYY-MM-DD HH:MM:SS' in UTC -> Date in the browser's time zone
const toDate = (s) => new Date(s.replace(' ', 'T') + 'Z');
const timeLabel = (s) => {
  const d = toDate(s);
  return minutes > 120
    ? d.toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' })
    : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
};
const fmt = (v, unit, digits = 1) => (v === null || v === undefined ? '–' : `${v.toFixed(digits)} ${unit}`);

function makeChart(id, type, label, color, unit, extra = {}) {
  return new Chart(document.getElementById(id), {
    type,
    data: { labels: [], datasets: [{ label, data: [], borderColor: color, backgroundColor: color + '55',
                                      pointRadius: 0, tension: 0.25, spanGaps: false, ...extra }] },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { title: { display: true, text: label } },
      scales: { x: { ticks: { maxTicksLimit: 8 } }, y: { title: { display: true, text: unit } } },
    },
  });
}

const tempChart = makeChart('tempChart', 'line', 'Temperature (°C)', '#e0435f', '°C');
const humChart = makeChart('humChart', 'bar', 'Humidity (%)', '#2a64c8', '%');
humChart.options.scales.y.min = 0;
humChart.options.scales.y.max = 100;
const pressChart = makeChart('pressChart', 'line', 'Water pressure (kPa)', '#e8650a', 'kPa', { fill: true });

function setData(chart, labels, values) {
  chart.data.labels = labels;
  chart.data.datasets[0].data = values;
  chart.update();
}

async function refresh() {
  try {
    const [hist, latest, recent, devs] = await Promise.all([
      fetch(`/api/history?minutes=${minutes}${deviceQuery()}`).then((r) => r.json()),
      fetch(`/api/latest?x=1${deviceQuery()}`).then((r) => r.json()),
      fetch(`/api/recent?limit=10${deviceQuery()}`).then((r) => r.json()),
      fetch('/api/devices').then((r) => r.json()),
    ]);
    updateDeviceList(devs.devices);

    const labels = hist.readings.map((r) => timeLabel(r.collected_at));
    setData(tempChart, labels, hist.readings.map((r) => r.temperature));
    setData(humChart, labels, hist.readings.map((r) => r.humidity));
    setData(pressChart, labels, hist.readings.map((r) => r.water_pressure));

    const r = latest.reading;
    document.getElementById('tempValue').textContent = r ? fmt(r.temperature, '°C') : '–';
    document.getElementById('humValue').textContent = r ? fmt(r.humidity, '%') : '–';
    document.getElementById('pressValue').textContent = r ? fmt(r.water_pressure, 'kPa', 0) : '–';
    document.getElementById('bufferedValue').textContent = latest.buffered_last_hour;

    const badge = document.getElementById('deviceStatus');
    if (latest.devices.length === 1) {
      const d = latest.devices[0];
      badge.textContent = `${d.device}: ${d.status}`;
      badge.className = 'badge ' + d.status;
    } else {
      const online = latest.devices.filter((d) => d.status === 'online').length;
      badge.textContent = `${online}/${latest.devices.length} online`;
      badge.className = 'badge' + (latest.devices.length && online === latest.devices.length ? ' online' : '');
    }

    document.getElementById('recentRows').innerHTML = recent.readings.map((row) => {
      const late = row.delay_s > recent.buffered_after_s;
      return `<tr>
        <td>${toDate(row.collected_at).toLocaleString()}</td>
        <td>${row.device}</td>
        <td>${fmt(row.temperature, '')}</td>
        <td>${fmt(row.humidity, '')}</td>
        <td>${fmt(row.water_pressure, '', 0)}</td>
        <td>${late ? `<span class="badge offline">buffered, +${row.delay_s}s</span>` : 'live'}</td>
      </tr>`;
    }).join('');

    document.getElementById('lastUpdate').textContent = 'last update: ' + new Date().toLocaleTimeString();
  } catch (err) {
    document.getElementById('lastUpdate').textContent = 'update failed: ' + err;
  }
}

// Keep the dropdown in sync with the devices found in the database (new Pis appear automatically).
function updateDeviceList(devices) {
  const select = document.getElementById('deviceSelect');
  const known = new Set([...select.options].map((o) => o.value));
  devices.forEach((d) => {
    if (!known.has(d.device)) select.add(new Option(d.device, d.device));
  });
}

document.getElementById('deviceSelect').addEventListener('change', (e) => {
  device = e.target.value;
  refresh();
});

document.querySelectorAll('.toolbar button').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.toolbar button').forEach((b) => b.classList.remove('active'));
    btn.classList.add('active');
    minutes = Number(btn.dataset.min);
    refresh();
  });
});

refresh();
setInterval(refresh, REFRESH_MS);
