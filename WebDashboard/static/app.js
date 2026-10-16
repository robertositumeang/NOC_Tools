/**
 * NOC Dashboard – Frontend Application Logic
 * Vanilla JS + ApexCharts, communicates with FastAPI backend
 */

// ══════════════════════ State ══════════════════════
const PAGE_SIZE = 200;
let _state = {
  allTickets: [],       // raw open tickets from last /api/tickets call
  filtered: [],         // after search/filter
  sortKey: 'no',
  sortAsc: true,
  page: 0,
  currentAging: 'ALL',
  theme: localStorage.getItem('noc_theme') || 'dark',
};

let _chartTrend     = null;
let _chartProblems  = null;
let _chartAging     = null;
let _chartSla       = null;
let _chartProvinces = null;
let _lastSummary    = null;

// ══════════════════════ Init ══════════════════════
document.addEventListener('DOMContentLoaded', async () => {
  applyTheme(_state.theme);
  startClock();
  await bootstrap();
  setInterval(() => silentRefresh(), 10 * 60 * 1000); // auto-sync every 10 min
});

async function bootstrap() {
  setStatus('loading', 'Memuat data dari cache / Google Sheets...');
  try {
    // 1. Load summary (fast — uses cache)
    const sum = await api('/api/summary');
    renderSummary(sum);

    // 2. Trigger background fetch (non-blocking)
    fetch(apiUrl('/api/refresh'), { method: 'POST' }).catch(() => {});

    // 3. Load charts & tables
    await Promise.all([loadTrend(), loadProblems(), loadProvinces(), loadTopClosedSites()]);

    setStatus('ok', 'Data berhasil dimuat');
  } catch (e) {
    setStatus('error', 'Gagal memuat data: ' + e.message);
  }
}

async function silentRefresh() {
  try {
    await fetch(apiUrl('/api/refresh'), { method: 'POST' });
    const sum = await api('/api/summary');
    renderSummary(sum);
    await refreshCharts();
    setStatus('ok', 'Data diperbarui (auto-sync)');
  } catch (_) {}
}

async function refreshData(force = false) {
  const btn = document.getElementById('btnRefresh');
  btn.innerHTML = '<span class="spin">⟳</span> Memuat...';
  btn.disabled = true;
  setStatus('loading', 'Mengunduh data terbaru dari Google Sheets...');

  try {
    await api('/api/refresh?force=' + (force ? 'true' : 'false'), { method: 'POST' });
    const sum = await api('/api/summary');
    renderSummary(sum);
    await refreshCharts();
    setStatus('ok', 'Data berhasil diperbarui');
  } catch (e) {
    setStatus('error', 'Gagal refresh: ' + e.message);
  } finally {
    btn.innerHTML = '🔄 Refresh DB';
    btn.disabled = false;
  }
}

// ══════════════════════ API helper ══════════════════════
async function api(path, opts = {}) {
  const resp = await fetch(apiUrl(path), opts);
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || resp.statusText);
  }
  return resp.json();
}

function apiUrl(path) {
  return path.startsWith('/api/') ? `/dashboard${path}` : path;
}

// ══════════════════════ Summary / KPI ══════════════════════
function renderSummary(sum) {
  _lastSummary = sum;
  setText('kpiTotal', sum.total ?? '—');
  setText('kpiOpen',  sum.open  ?? '—');
  setText('kpiClose', sum.close ?? '—');
  setText('kpiSla',   sum.slaBreached ?? '—');

  const ag = sum.aging || {};
  setText('agAll',  ag.ALL ?? '—');
  setText('agD1',   ag.d1  ?? '—');
  setText('agD3',   ag.d3  ?? '—');
  setText('agD7',   ag.d7  ?? '—');
  setText('agMax',  ag.max ?? '—');

  renderAgingAndSla(sum);

  // Populate dropdowns
  fillSelect('filterPkg',  sum.packages  || [], 'Semua paket');
  fillSelect('filterProv', sum.provinces || [], 'Semua provinsi');
  fillSelect('modalPkg',   sum.packages  || [], 'Semua Paket');
  fillSelect('modalProv',  sum.provinces || [], 'Semua Provinsi');

  document.getElementById('statusCount').textContent =
    `${sum.total || 0} tiket total · ${sum.open || 0} open · ${sum.slaBreached || 0} SLA breached`;
}

function fillSelect(id, items, placeholder) {
  const el = document.getElementById(id);
  const cur = el.value;
  el.innerHTML = `<option value="">${placeholder}</option>` +
    items.map(v => `<option value="${v}">${v}</option>`).join('');
  if (cur && items.includes(cur)) el.value = cur;
}

// ══════════════════════ Charts ══════════════════════
function getChartTheme() {
  const dark = document.documentElement.getAttribute('data-theme') === 'dark';
  return {
    bg:      dark ? '#10213A' : '#FFFFFF',
    appBg:   dark ? '#091526' : '#F2F6FC',
    text:    dark ? '#EEF5FF' : '#15263B',
    muted:   dark ? '#A8B9CF' : '#52677F',
    grid:    dark ? '#294363' : '#D2DFEE',
    accent:  dark ? '#2AA8F2' : '#126FE8',
    secondary: dark ? '#4C83E6' : '#3F67C8',
  };
}

async function loadTrend() {
  const pkg  = document.getElementById('filterPkg')?.value  || '';
  const prov = document.getElementById('filterProv')?.value || '';
  const data = await api(`/api/trend?package=${encodeURIComponent(pkg)}&province=${encodeURIComponent(prov)}`);
  renderTrendChart(data.dates || [], data.counts || []);
}

function renderTrendChart(dates, counts) {
  const t = getChartTheme();
  const opts = {
    series: [{ name: 'Jumlah Tiket', data: counts }],
    chart: {
      type: 'area', height: '100%',
      background: t.bg,
      toolbar: { show: false },
      animations: { enabled: true, easing: 'easeinout', speed: 600 },
    },
    theme: { mode: document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light' },
    dataLabels: { enabled: counts.length <= 20, style: { fontSize: '10px', fontWeight: 700 } },
    stroke: { curve: 'smooth', width: 2.5 },
    fill: {
      type: 'gradient',
      gradient: { shadeIntensity: 1, opacityFrom: .35, opacityTo: .02, stops: [0, 90, 100] },
    },
    colors: [t.accent],
    xaxis: {
      categories: dates,
      labels: { style: { colors: t.muted, fontSize: '10px' }, rotate: -35 },
      axisBorder: { show: false }, axisTicks: { show: false },
    },
    yaxis: { labels: { style: { colors: t.muted } } },
    grid: { borderColor: t.grid, strokeDashArray: 4 },
    tooltip: { theme: document.documentElement.getAttribute('data-theme') },
    markers: { size: counts.length <= 20 ? 4 : 0 },
  };

  const el = document.getElementById('chartTrend');
  if (_chartTrend) { _chartTrend.updateOptions(opts); }
  else { _chartTrend = new ApexCharts(el, opts); _chartTrend.render(); }
}

async function loadProblems() {
  const pkg  = document.getElementById('filterPkg')?.value  || '';
  const prov = document.getElementById('filterProv')?.value || '';
  const data = await api(`/api/problems?package=${encodeURIComponent(pkg)}&province=${encodeURIComponent(prov)}&top=10`);
  renderProblemsChart(data.labels || [], data.values || []);
}

function renderProblemsChart(labels, values) {
  const t = getChartTheme();
  const reversed_labels = [...labels].reverse();
  const reversed_values = [...values].reverse();
  const total = values.reduce((a, b) => a + b, 0) || 1;

  const opts = {
    series: [{ name: 'Jumlah', data: reversed_values }],
    chart: {
      type: 'bar', height: '100%',
      background: t.bg,
      toolbar: { show: false },
      animations: { enabled: true, easing: 'easeinout', speed: 600 },
    },
    theme: { mode: document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light' },
    plotOptions: {
      bar: {
        horizontal: true, barHeight: '55%', borderRadius: 4,
        dataLabels: { position: 'end' },
      },
    },
    dataLabels: {
      enabled: true,
      formatter: (v) => `${v} (${Math.round(v / total * 100)}%)`,
      style: { fontSize: '10px', fontWeight: 700, colors: [t.muted] },
      offsetX: -4,
    },
    colors: [t.secondary],
    xaxis: {
      categories: reversed_labels,
      labels: { style: { colors: t.muted, fontSize: '10px' } },
    },
    yaxis: {
      labels: {
        style: { colors: t.muted, fontSize: '10px' },
        maxWidth: 220,
        formatter: (v) => v.length > 30 ? v.substring(0, 28) + '…' : v,
      },
    },
    grid: { borderColor: t.grid, strokeDashArray: 4, xaxis: { lines: { show: true } }, yaxis: { lines: { show: false } } },
    tooltip: { theme: document.documentElement.getAttribute('data-theme') },
  };

  const el = document.getElementById('chartProblems');
  if (_chartProblems) { _chartProblems.updateOptions(opts); }
  else { _chartProblems = new ApexCharts(el, opts); _chartProblems.render(); }
}

async function refreshCharts() {
  if (_lastSummary) renderAgingAndSla(_lastSummary);
  await Promise.all([loadTrend(), loadProblems(), loadProvinces(), loadTopClosedSites()]);
}

function renderAgingAndSla(sum) {
  if (!sum) return;
  const t = getChartTheme();
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  const ag = sum.aging || {};

  // 1. Donut Chart for Aging
  const agingOpts = {
    series: [ag.d1 || 0, ag.d3 || 0, ag.d7 || 0, ag.max || 0],
    labels: ['< 1 Hari', '1–3 Hari', '3–7 Hari', '> 7 Hari'],
    chart: {
      type: 'donut',
      height: 240,
      background: t.bg,
      animations: { enabled: true, speed: 600 },
    },
    theme: { mode: isDark ? 'dark' : 'light' },
    colors: ['#10b981', '#2aa8f2', '#f4b94e', '#f43f5e'],
    legend: {
      position: 'bottom',
      fontSize: '11px',
      labels: { colors: t.muted },
      markers: { width: 8, height: 8, radius: 2 },
    },
    dataLabels: {
      enabled: true,
      formatter: (val, opts) => opts.w.config.series[opts.seriesIndex],
      style: { fontSize: '11px', fontWeight: 700 },
      dropShadow: { enabled: false },
    },
    plotOptions: {
      pie: {
        donut: {
          size: '65%',
          labels: {
            show: true,
            total: {
              show: true,
              label: 'Total Open',
              color: t.muted,
              fontSize: '11px',
              formatter: () => (sum.open || 0).toLocaleString('id-ID'),
            },
            value: {
              fontSize: '20px',
              fontWeight: 800,
              color: t.text,
              formatter: (v) => Number(v).toLocaleString('id-ID'),
            },
          },
        },
      },
    },
    stroke: { width: 1, colors: [t.card] },
    tooltip: { theme: isDark ? 'dark' : 'light' },
  };

  const elAging = document.getElementById('chartAging');
  if (elAging) {
    if (_chartAging) { _chartAging.updateOptions(agingOpts); }
    else { _chartAging = new ApexCharts(elAging, agingOpts); _chartAging.render(); }
  }

  // 2. Radial Gauge for SLA Compliance
  const openCount = sum.open || 0;
  const breached  = sum.slaBreached || 0;
  const onTime    = Math.max(0, openCount - breached);
  const pct       = openCount > 0 ? Math.max(0, Math.min(100, Math.round((onTime / openCount) * 100))) : 100;
  const slaColor  = pct >= 85 ? '#10b981' : (pct >= 65 ? '#f4b94e' : '#f43f5e');

  const slaOpts = {
    series: [pct],
    chart: {
      type: 'radialBar',
      height: 240,
      background: t.bg,
      animations: { enabled: true, speed: 600 },
    },
    theme: { mode: isDark ? 'dark' : 'light' },
    colors: [slaColor],
    plotOptions: {
      radialBar: {
        startAngle: -135,
        endAngle: 135,
        hollow: { size: '60%', background: 'transparent' },
        track: {
          background: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)',
          strokeWidth: '100%',
        },
        dataLabels: {
          name: {
            show: true,
            label: 'SLA COMPLIANCE',
            fontSize: '10px',
            fontWeight: 700,
            color: t.muted,
            offsetY: -6,
          },
          value: {
            show: true,
            fontSize: '22px',
            fontWeight: 800,
            color: slaColor,
            offsetY: 6,
            formatter: (v) => `${v}%`,
          },
        },
      },
    },
    stroke: { dashArray: 4 },
    labels: ['SLA Target (4h)'],
    tooltip: { enabled: false },
  };

  const elSla = document.getElementById('chartSla');
  if (elSla) {
    if (_chartSla) { _chartSla.updateOptions(slaOpts); }
    else { _chartSla = new ApexCharts(elSla, slaOpts); _chartSla.render(); }
  }
}

async function loadProvinces() {
  const pkg = document.getElementById('filterPkg')?.value || '';
  try {
    const data = await api(`/api/province-stats?package=${encodeURIComponent(pkg)}&top=7`);
    renderProvincesChart(data.labels || [], data.open || [], data.close || []);
  } catch (_) {}
}

function renderProvincesChart(labels, openCounts, closeCounts) {
  const t = getChartTheme();
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';

  const opts = {
    series: [
      { name: 'Tiket Open', data: openCounts },
      { name: 'Tiket Selesai (Close)', data: closeCounts },
    ],
    chart: {
      type: 'bar',
      height: '100%',
      background: t.bg,
      stacked: true,
      toolbar: { show: false },
      animations: { enabled: true, speed: 600 },
    },
    theme: { mode: isDark ? 'dark' : 'light' },
    colors: ['#f43f5e', '#10b981'],
    plotOptions: {
      bar: {
        horizontal: false,
        columnWidth: '45%',
        borderRadius: 4,
      },
    },
    dataLabels: { enabled: false },
    xaxis: {
      categories: labels,
      labels: {
        style: { colors: t.muted, fontSize: '10px' },
        rotate: -20,
        rotateAlways: false,
      },
    },
    yaxis: {
      labels: { style: { colors: t.muted, fontSize: '10px' } },
    },
    legend: {
      position: 'top',
      fontSize: '11px',
      labels: { colors: t.muted },
      markers: { width: 8, height: 8, radius: 2 },
    },
    grid: {
      borderColor: t.grid,
      strokeDashArray: 4,
      yaxis: { lines: { show: true } },
      xaxis: { lines: { show: false } },
    },
    tooltip: { theme: isDark ? 'dark' : 'light' },
  };

  const el = document.getElementById('chartProvinces');
  if (_chartProvinces) { _chartProvinces.updateOptions(opts); }
  else { _chartProvinces = new ApexCharts(el, opts); _chartProvinces.render(); }
}

async function loadTopClosedSites() {
  const pkg   = document.getElementById('filterPkg')?.value || '';
  const prov  = document.getElementById('filterProv')?.value || '';
  const limit = document.getElementById('limitTopClosed')?.value || '15';

  const tbody = document.getElementById('topClosedTbody');
  if (!tbody) return;

  try {
    const data = await api(`/api/top-closed-sites?package=${encodeURIComponent(pkg)}&province=${encodeURIComponent(prov)}&limit=${limit}`);
    const sites = data.sites || [];

    if (sites.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:24px;color:var(--muted);">
        Belum ada data tiket close yang sesuai dengan filter.
      </td></tr>`;
      return;
    }

    const medals = ['🥇', '🥈', '🥉'];
    tbody.innerHTML = sites.map((s, idx) => {
      const rank = idx < 3 ? `<span class="medal">${medals[idx]}</span> ${idx + 1}` : `${idx + 1}`;
      const sid = esc(s.siteId);
      const sname = esc(s.siteName);
      const sprov = esc(s.province);
      const spkg = esc(s.package);
      const domProb = esc(s.dominantProblem);
      const lastClose = esc(s.lastClose || '—');

      return `<tr>
        <td style="text-align:center;font-weight:700;color:var(--muted);">${rank}</td>
        <td><span style="font-family:Consolas,monospace;font-weight:700;color:var(--accent);">${sid}</span></td>
        <td>${sname}</td>
        <td>${sprov}</td>
        <td><small style="color:var(--muted);">${spkg}</small></td>
        <td style="text-align:center;">
          <span style="background:rgba(16,185,129,.15);color:var(--green);font-weight:800;padding:2px 10px;border-radius:12px;font-size:11px;">
            ${s.closeCount} Tiket
          </span>
        </td>
        <td style="max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${domProb}">
          ${domProb}
        </td>
        <td style="white-space:nowrap;font-size:11px;color:var(--muted);">${lastClose}</td>
      </tr>`;
    }).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:20px;color:var(--alert);">
      Gagal memuat top closed sites: ${esc(err.message)}
    </td></tr>`;
  }
}

// ══════════════════════ Open Tickets Modal ══════════════════════
async function openTicketsDialog(aging = 'ALL') {
  _state.currentAging = aging;
  _state.page = 0;
  document.getElementById('modalAging').value = aging === 'ALL' ? '' : aging;
  showModal();
  await fetchAndRenderTickets();
}

function showModal() {
  document.getElementById('modalOverlay').classList.add('show');
}

function closeModal() {
  document.getElementById('modalOverlay').classList.remove('show');
}

async function fetchAndRenderTickets() {
  const search = document.getElementById('modalSearch').value.trim();
  const aging  = document.getElementById('modalAging').value;
  const pkg    = document.getElementById('modalPkg').value;
  const prov   = document.getElementById('modalProv').value;

  const params = new URLSearchParams({
    status: 'OPEN',
    aging:  aging || _state.currentAging,
    package: pkg || '',
    province: prov || '',
    search: search,
    limit: PAGE_SIZE,
    offset: _state.page * PAGE_SIZE,
  });

  try {
    const data = await api('/api/tickets?' + params);
    _state.allTickets = data.tickets || [];
    _state.filtered   = data.tickets || [];
    renderTicketTable(_state.filtered, data.total);
    document.getElementById('modalBadge').textContent = data.total + ' tiket';
    document.getElementById('modalInfo').textContent =
      `Menampilkan ${_state.page * PAGE_SIZE + 1}–${Math.min((_state.page + 1) * PAGE_SIZE, data.total)} dari ${data.total} tiket`;
    document.getElementById('pageInfo').textContent =
      `Halaman ${_state.page + 1} / ${Math.max(1, Math.ceil(data.total / PAGE_SIZE))}`;
  } catch (e) {
    document.getElementById('ticketBody').innerHTML =
      `<tr><td colspan="9" style="text-align:center;padding:30px;color:var(--alert);">Error: ${e.message}</td></tr>`;
  }
}

function filterTable() {
  _state.page = 0;
  fetchAndRenderTickets();
}

function sortTable(key) {
  if (_state.sortKey === key) _state.sortAsc = !_state.sortAsc;
  else { _state.sortKey = key; _state.sortAsc = true; }
  renderTicketTable(_state.filtered);
}

function prevPage() {
  if (_state.page > 0) { _state.page--; fetchAndRenderTickets(); }
}

function nextPage() {
  _state.page++;
  fetchAndRenderTickets();
}

function renderTicketTable(tickets, total) {
  const aging_badge = {
    d1:  '<span class="badge badge-d1">&lt;1 Hari</span>',
    d3:  '<span class="badge badge-d3">1–3 Hari</span>',
    d7:  '<span class="badge badge-d7">3–7 Hari</span>',
    max: '<span class="badge badge-max">&gt;7 Hari</span>',
  };

  if (!tickets.length) {
    document.getElementById('ticketBody').innerHTML =
      '<tr><td colspan="9" style="text-align:center;padding:30px;color:var(--muted);">Tidak ada tiket yang sesuai filter.</td></tr>';
    return;
  }

  const rows = tickets.map((t, i) => {
    const ab  = aging_badge[t.agingBucket] || '<span class="badge" style="background:rgba(148,163,184,.15);color:#94a3b8">—</span>';
    const slaBadge = t.slaStatus === 'BREACHED' || t.slaStatus === 'CRITICAL'
      ? `<span class="badge badge-sla-breach">${esc(t.slaLabel)}</span>`
      : t.slaStatus === 'WARNING'
        ? `<span class="badge badge-sla-warn">${esc(t.slaLabel)}</span>`
        : `<span class="badge badge-sla-ok">${esc(t.slaLabel)}</span>`;

    return `<tr ondblclick="openTimeline(${i})" style="cursor:pointer;">
      <td style="color:var(--muted);font-family:Consolas,monospace;font-size:11px;">${_state.page * PAGE_SIZE + i + 1}</td>
      <td style="color:var(--muted);">${esc(t.dateQuery || '—')}</td>
      <td class="site-id">${esc(t.ticketId || '—')}</td>
      <td class="site-id">${esc(t.siteId || '—')}</td>
      <td>${esc(t.siteName || '—')}</td>
      <td style="color:var(--muted);">${esc(t.package || '—')}</td>
      <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;" title="${esc(t.problem || '')}">${esc(t.problem || '—')}</td>
      <td>${ab}</td>
      <td>${slaBadge}</td>
    </tr>`;
  });

  document.getElementById('ticketBody').innerHTML = rows.join('');
  if (total !== undefined) {
    document.getElementById('modalInfo').textContent =
      `Menampilkan ${_state.page * PAGE_SIZE + 1}–${Math.min((_state.page + 1) * PAGE_SIZE, total)} dari ${total} tiket`;
  }
}

function openTimeline(idx) {
  const t = _state.filtered[idx];
  if (!t) return;
  alert(`📋 Timeline: ${t.siteId} – ${t.siteName}\n\nTicket: ${t.ticketId}\nProblem: ${t.problem}\nAging: ${t.agingLabel}\nSLA: ${t.slaLabel}\nTanggal: ${t.dateQuery}`);
}

// ══════════════════════ CSV Export ══════════════════════
async function exportCSV() {
  const search = document.getElementById('modalSearch').value.trim();
  const aging  = document.getElementById('modalAging').value;
  const pkg    = document.getElementById('modalPkg').value;
  const prov   = document.getElementById('modalProv').value;

  const params = new URLSearchParams({
    status: 'OPEN',
    aging: aging || _state.currentAging,
    package: pkg || '',
    province: prov || '',
    search: search,
    limit: 5000,
    offset: 0,
  });

  const data = await api('/api/tickets?' + params);
  const tickets = data.tickets || [];
  if (!tickets.length) { alert('Tidak ada data untuk diekspor.'); return; }

  const headers = ['No','Tanggal','Ticket ID','Site ID','Nama Site','Paket','Provinsi','Regency','Problem','Aging','SLA Label','SLA Status'];
  const rows = tickets.map((t, i) => [
    i + 1,
    t.dateQuery || '',
    t.ticketId || '',
    t.siteId || '',
    t.siteName || '',
    t.package || '',
    t.province || '',
    t.regency || '',
    t.problem || '',
    t.agingLabel || '',
    t.slaLabel || '',
    t.slaStatus || '',
  ].map(v => `"${String(v).replace(/"/g, '""')}"`).join(','));

  const csv = [headers.join(','), ...rows].join('\r\n');
  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url;
  a.download = `NOC_Open_Tickets_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

// ══════════════════════ Settings ══════════════════════
async function openSettings() {
  const s = await api('/api/settings');
  document.getElementById('urlInput').value = s.spreadsheet_url || '';
  document.getElementById('settingsOverlay').classList.add('show');
}

function closeSettings() {
  document.getElementById('settingsOverlay').classList.remove('show');
}

async function saveSettings() {
  const url = document.getElementById('urlInput').value.trim();
  if (!url) { alert('URL tidak boleh kosong.'); return; }
  try {
    await api('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ spreadsheet_url: url }),
    });
    closeSettings();
    await refreshData(true);
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

// ══════════════════════ Theme ══════════════════════
function setTheme(t) {
  _state.theme = t;
  localStorage.setItem('noc_theme', t);
  applyTheme(t);
}

function applyTheme(t) {
  document.documentElement.setAttribute('data-theme', t);
  document.getElementById('btnLight').classList.toggle('active', t === 'light');
  document.getElementById('btnDark').classList.toggle('active',  t === 'dark');
  // Re-render charts with new theme colors
  if (_chartTrend || _chartProblems) {
    setTimeout(() => {
      if (_chartTrend)    refreshCharts();
    }, 50);
  }
}

// ══════════════════════ Clock ══════════════════════
function startClock() {
  const el = document.getElementById('clock');
  function tick() {
    const now = new Date();
    el.textContent =
      String(now.getHours()).padStart(2, '0') + ':' +
      String(now.getMinutes()).padStart(2, '0') + ':' +
      String(now.getSeconds()).padStart(2, '0');
  }
  tick();
  setInterval(tick, 1000);
}

// ══════════════════════ Status bar ══════════════════════
function setStatus(state, msg) {
  const dot  = document.getElementById('statusDot');
  const text = document.getElementById('statusText');
  dot.className  = 'status-dot' + (state !== 'ok' ? ' ' + state : '');
  text.textContent = msg;
}

// ══════════════════════ Helpers ══════════════════════
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ══════════════════════ Reporting & Shift Handover ══════════════════════
let _reportType = 'handover';

function openReportModal(type = 'handover') {
  _reportType = type;
  document.getElementById('reportModalOverlay').classList.add('show');
  switchReportTab(type);
}

function closeReportModal() {
  document.getElementById('reportModalOverlay').classList.remove('show');
  const toast = document.getElementById('copyToast');
  if (toast) toast.style.display = 'none';
}

function switchReportTab(type) {
  _reportType = type;
  const isHandover = type === 'handover';

  const tabHo = document.getElementById('tabBtnHandover');
  const tabNoc = document.getElementById('tabBtnNoc');
  const officers = document.getElementById('handoverOfficersGroup');
  const title = document.getElementById('reportModalTitle');

  if (tabHo) tabHo.classList.toggle('active', isHandover);
  if (tabNoc) tabNoc.classList.toggle('active', !isHandover);
  if (officers) officers.style.display = isHandover ? 'flex' : 'none';
  if (title) {
    title.textContent = isHandover
      ? '📋 Format Laporan Shift Handover NOC'
      : '📡 Format Laporan WhatsApp NOC (Status Problem)';
  }

  updateReportPreview();
}

function setQuickReportTime(val) {
  const customInput = document.getElementById('reportTimeInput');
  if (val === 'custom') {
    customInput.style.display = 'inline-block';
    customInput.focus();
  } else {
    customInput.style.display = 'none';
    updateReportPreview();
  }
}

async function updateReportPreview() {
  const preview = document.getElementById('reportPreviewText');
  const charCount = document.getElementById('reportCharCount');
  if (!preview) return;

  const area = document.getElementById('reportArea')?.value || 'all';
  const quickTime = document.getElementById('reportTimeQuick')?.value || 'auto';
  const customTime = document.getElementById('reportTimeInput')?.value.trim() || '';
  const timeStr = quickTime === 'custom' ? customTime : (quickTime === 'auto' ? '' : quickTime);
  const pagi = document.getElementById('officerPagi')?.value.trim() || '';
  const malam = document.getElementById('officerMalam')?.value.trim() || '';
  const includeList = document.getElementById('reportIncludeList')?.checked || false;

  preview.value = 'Membuat draft laporan...';

  try {
    let url = '';
    if (_reportType === 'handover') {
      const q = new URLSearchParams({
        area,
        pagi,
        malam,
        time_str: timeStr,
        include_list: includeList,
      });
      url = '/api/reports/handover?' + q.toString();
    } else {
      const q = new URLSearchParams({
        area,
        time_str: timeStr || '12:00',
        include_list: includeList,
      });
      url = '/api/reports/noc?' + q.toString();
    }

    const data = await api(url);
    const text = data.report || '';
    preview.value = text;
    if (charCount) charCount.textContent = `${text.length} karakter`;
  } catch (err) {
    preview.value = `Gagal membuat laporan: ${err.message}`;
  }
}

async function copyReportText() {
  const preview = document.getElementById('reportPreviewText');
  const toast = document.getElementById('copyToast');
  if (!preview || !preview.value) return;

  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(preview.value);
    } else {
      preview.select();
      document.execCommand('copy');
    }
    if (toast) {
      toast.style.display = 'block';
      setTimeout(() => { toast.style.display = 'none'; }, 2500);
    }
  } catch (err) {
    alert('Gagal menyalin teks: ' + err.message);
  }
}

function openReportWhatsApp(mode = 'web') {
  const preview = document.getElementById('reportPreviewText');
  if (!preview || !preview.value) {
    alert('Teks laporan belum siap.');
    return;
  }
  const encoded = encodeURIComponent(preview.value);
  if (mode === 'web') {
    window.open(`https://web.whatsapp.com/send?text=${encoded}`, '_blank');
  } else {
    window.location.href = `whatsapp://send?text=${encoded}`;
  }
}

function downloadReportTxt() {
  const preview = document.getElementById('reportPreviewText');
  if (!preview || !preview.value) {
    alert('Teks laporan belum siap.');
    return;
  }
  const dateStr = new Date().toISOString().slice(0, 10);
  const blob = new Blob([preview.value], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `NOC_${_reportType.toUpperCase()}_${dateStr}.txt`;
  a.click();
  URL.revokeObjectURL(url);
}

// ══════════════════════ Direct CSV Download & Launcher ══════════════════════
function downloadAllTicketsCSV() {
  window.location.href = apiUrl('/api/export-tickets');
}

async function openTicketCheckerApp() {
  try {
    const res = await api('/api/open-ticket-checker', { method: 'POST' });
    if (res.success) {
      window.location.href = res.url;
    } else {
      alert(res.message || 'Gagal membuka NOC Web Ticket Checker');
    }
  } catch (err) {
    alert('Gagal membuka Ticket Checker: ' + err.message);
  }
}

