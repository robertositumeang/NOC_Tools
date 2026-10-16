/* ──────────────────────────────────────────────
   NOC Ticket Checker – app.js
   FastAPI backend: http://127.0.0.1:{port}
   ────────────────────────────────────────────── */

"use strict";

// ── State ────────────────────────────────────────────────────────
let _filter     = "all";
let _search     = "";
let _offset     = 0;
const LIMIT     = 200;
let _totalGaps  = 0;
let _currentGaps = [];
let _searchTimer = null;
let _dbPollTimer = null;

// Checkbox selection state
let _selectedGapIndices = new Set();  // absolute indices in _currentGaps (by page-relative index mapped to global)
let _gapPageIndices     = [];         // maps row position (0-based in page) → global index (offset + i)

// ── Clock ─────────────────────────────────────────────────────────
function startClock() {
  function tick() {
    const now = new Date();
    const h = String(now.getHours()).padStart(2,'0');
    const m = String(now.getMinutes()).padStart(2,'0');
    const s = String(now.getSeconds()).padStart(2,'0');
    const el = document.getElementById("clock");
    if (el) el.textContent = `${h}:${m}:${s}`;
  }
  tick();
  setInterval(tick, 1000);
}

// ── Theme ─────────────────────────────────────────────────────────
function applyTheme(t) {
  document.documentElement.setAttribute("data-theme", t);
  const btn = document.getElementById("themeBtn");
  if (btn) btn.textContent = t === "dark" ? "☀ Light" : "🌙 Dark";
  localStorage.setItem("noc_theme", t);
}
function toggleTheme() {
  const cur = document.documentElement.getAttribute("data-theme") || "dark";
  applyTheme(cur === "dark" ? "light" : "dark");
}

// ── Status bar ─────────────────────────────────────────────────────
function setStatus(msg, ok = true) {
  const el  = document.getElementById("status-msg");
  const dot = document.getElementById("statusDot");
  if (el)  el.textContent  = msg;
  if (dot) dot.style.background = ok ? "var(--green)" : "var(--alert)";
}

// ── API helpers ───────────────────────────────────────────────────
async function apiFetch(url, opts = {}) {
  const res = await fetch(url, opts);
  if (!res.ok) {
    let detail = "";
    try { const j = await res.json(); detail = j.detail || ""; } catch {}
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── DB Status ─────────────────────────────────────────────────────
let _dbPollTimer = null;

function stopDbPolling() {
  if (_dbPollTimer) {
    clearInterval(_dbPollTimer);
    _dbPollTimer = null;
  }
}

function startDbPolling() {
  if (_dbPollTimer) return;
  _dbPollTimer = setInterval(async () => {
    try {
      const d = await apiFetch("/api/db-status");
      updateDbCard(d);
      checkReady(d);
      if (d.loaded || d.error) {
        stopDbPolling();
        const btn = document.getElementById("refreshDbBtn");
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg> Refresh DB`;
        }
      }
    } catch (e) {
      // transient polling error
    }
  }, 1000);
}

async function loadDbStatus() {
  try {
    const d = await apiFetch("/api/db-status");
    updateDbCard(d);
    updateUploadCards(d);
    checkReady(d);

    if (d.loading || (!d.loaded && !d.error)) {
      startDbPolling();
    }

    if (d.checked) {
      await fetchGaps(_filter, _search, 0);
      showResults(d);
    }
  } catch (e) {
    setDbCardError(e.message);
  }
}

function updateDbCard(d) {
  const badge = document.getElementById("dbStatusBadge");
  const count = document.getElementById("dbCountText");

  if (d.loading) {
    if (badge) {
      badge.className = "db-badge badge-loading";
      badge.innerHTML = `<span class="spinner"></span> Sinkronisasi Google Sheets...`;
    }
    if (count) count.textContent = "Sedang mengunduh dan membaca database Trouble Ticket...";
    setStatus("Sedang sinkronisasi database dari Google Sheets...");
  } else if (d.error) {
    if (badge) {
      badge.className = "db-badge badge-error";
      badge.textContent = "Gagal Terhubung";
    }
    if (count) count.textContent = d.error;
    setStatus("Gagal memuat DB: " + d.error, false);
  } else if (d.loaded) {
    if (badge) {
      badge.className = "db-badge badge-connected";
      badge.textContent = "● Terhubung";
    }
    const at = d.loaded_at ? new Date(d.loaded_at * 1000).toLocaleTimeString("id-ID") : "";
    if (count) count.textContent = `${d.count.toLocaleString("id-ID")} tiket database siap` + (at ? ` (${at})` : "");
    setStatus(`Database siap: ${d.count.toLocaleString("id-ID")} tiket dimuat`);
  } else {
    if (badge) {
      badge.className = "db-badge badge-idle";
      badge.textContent = "Belum dimuat";
    }
    if (count) count.textContent = "Klik Refresh DB untuk memuat data.";
  }
}

function setDbCardError(msg) {
  const badge = document.getElementById("dbStatusBadge");
  const count = document.getElementById("dbCountText");
  if (badge) {
    badge.className = "db-badge badge-error";
    badge.textContent = "Error";
  }
  if (count) count.textContent = msg;
  setStatus("Gagal memuat DB: " + msg, false);
}

function updateUploadCards(d) {
  if (d.down_filename && d.down_count > 0) {
    markUploadLoaded("down", d.down_filename, d.down_count);
  }
  if (d.unmon_filename && d.unmon_count > 0) {
    markUploadLoaded("unmon", d.unmon_filename, d.unmon_count);
  }
}

// ── Refresh DB ────────────────────────────────────────────────────
async function refreshDb() {
  const btn = document.getElementById("refreshDbBtn");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner"></span> Sinkronisasi...`;
  }

  const badge = document.getElementById("dbStatusBadge");
  const count = document.getElementById("dbCountText");
  if (badge) {
    badge.className = "db-badge badge-loading";
    badge.innerHTML = `<span class="spinner"></span> Sinkronisasi...`;
  }
  if (count) count.textContent = "Sedang mengambil data terbaru dari Google Sheets...";

  setStatus("Memuat ulang database TT dari Google Sheets...");

  try {
    await apiFetch("/api/refresh-db?force=true", { method: "POST" });
    startDbPolling();
  } catch (e) {
    setDbCardError(e.message);
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg> Refresh DB`;
    }
  }
}

// ── Upload Cards ──────────────────────────────────────────────────
function triggerUpload(type) {
  // Prevent double-click from re-opening if already uploaded
  document.getElementById(`${type}Input`).click();
}

function handleDragOver(e, type) {
  e.preventDefault();
  document.getElementById(`${type}Card`).classList.add("dragging");
}
function handleDragLeave(type) {
  document.getElementById(`${type}Card`).classList.remove("dragging");
}
function handleDrop(e, type) {
  e.preventDefault();
  document.getElementById(`${type}Card`).classList.remove("dragging");
  const files = Array.from(e.dataTransfer.files).filter(f =>
    /\.(xlsx|xlsm|xls)$/i.test(f.name)
  );
  if (files.length) uploadFiles(type, files);
  else alert("Please drop .xlsx / .xlsm / .xls files.");
}
function handleFileChange(type, input) {
  const files = Array.from(input.files);
  if (files.length) uploadFiles(type, files);
  input.value = ""; // allow re-uploading same file
}

function markUploadLoaded(type, filename, count, fileCount) {
  const card    = document.getElementById(`${type}Card`);
  const fnDiv   = document.getElementById(`${type}Filename`);
  const fnText  = document.getElementById(`${type}FnText`);
  const cntText = document.getElementById(`${type}CountText`);
  const subText = document.getElementById(`${type}SubText`);

  if (card) card.classList.add("loaded");
  if (fnDiv) fnDiv.classList.remove("hidden");
  if (subText) subText.classList.add("hidden");

  // If multiple files, show count badge
  if (fileCount && fileCount > 1) {
    if (fnText) fnText.textContent = `${fileCount} files (${filename})`;
    if (cntText) cntText.textContent = `• ${count.toLocaleString("id-ID")} rows total`;
  } else {
    if (fnText) fnText.textContent = filename;
    if (cntText) cntText.textContent = `• ${count.toLocaleString("id-ID")} rows`;
  }
}

async function uploadFiles(type, files) {
  for (const f of files) {
    const suffix = f.name.split(".").pop().toLowerCase();
    if (!["xlsx","xlsm","xls"].includes(suffix)) {
      alert(`File '${f.name}' harus berformat .xlsx, .xlsm, atau .xls`);
      return;
    }
  }

  const card = document.getElementById(`${type}Card`);
  card.style.opacity = ".6";
  card.style.pointerEvents = "none";
  setStatus(`Mengupload ${files.length} file...`);

  const form = new FormData();
  for (const f of files) form.append("files", f);

  try {
    const res = await fetch(`/api/upload/${type}`, { method: "POST", body: form });
    if (!res.ok) {
      const j = await res.json().catch(() => ({}));
      throw new Error(j.detail || `HTTP ${res.status}`);
    }
    const d = await res.json();
    markUploadLoaded(type, d.filename, d.count, d.file_count);
    const label = d.file_count > 1
      ? `${d.file_count} files berhasil diupload (${d.count.toLocaleString("id-ID")} baris total)`
      : `${d.filename} berhasil diupload (${d.count.toLocaleString("id-ID")} baris)`;
    setStatus(label);

    // Reset results when new file uploaded
    hideResults();

    // Refresh status to update checkReady
    const status = await apiFetch("/api/db-status");
    checkReady(status);
  } catch (e) {
    setStatus("Upload gagal: " + e.message, false);
    alert("Upload gagal: " + e.message);
  } finally {
    card.style.opacity = "";
    card.style.pointerEvents = "";
  }
}

// ── Ready Check ───────────────────────────────────────────────────
function checkReady(d) {
  const runBtn  = document.getElementById("runBtn");
  const hintTxt = document.getElementById("runHintText");
  const ready   = d.loaded && (d.down_count > 0 || d.unmon_count > 0);
  if (runBtn) runBtn.disabled = !ready;

  if (!d.loaded) {
    if (hintTxt) hintTxt.textContent = "Pastikan database TT sudah termuat terlebih dahulu.";
  } else if (d.down_count === 0 && d.unmon_count === 0) {
    if (hintTxt) hintTxt.textContent = "Upload minimal satu file incident (Site Down atau Site Unmonitor).";
  } else {
    const parts = [];
    if (d.down_count > 0)  parts.push(`${d.down_count.toLocaleString("id-ID")} site down`);
    if (d.unmon_count > 0) parts.push(`${d.unmon_count.toLocaleString("id-ID")} site unmonitor`);
    if (hintTxt) hintTxt.textContent = `Siap dicek: ${parts.join(", ")}. Klik Jalankan untuk memulai audit.`;
  }
}

// ── Run Check ─────────────────────────────────────────────────────
async function runCheck() {
  const btn = document.getElementById("runBtn");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> Memproses...`;
  setStatus("Menjalankan pengecekan gap...");

  try {
    const d = await apiFetch("/api/run-check", { method: "POST" });
    updateKpiCards(d.summary);
    await fetchGaps("all", "", 0);
    showResults();
    setStatus(`Pengecekan selesai: ${d.gap_count} site gap ditemukan`);
  } catch (e) {
    setStatus("Pengecekan gagal: " + e.message, false);
    alert("Pengecekan gagal: " + e.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg> Jalankan Pengecekan`;
  }
}

function updateKpiCards(summary) {
  const s = summary || {};
  const set = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = (val ?? 0).toLocaleString("id-ID");
  };
  set("kpiTotal", s.total_checked);
  set("kpiDown",  s.down_gaps);
  set("kpiUnmon", s.unmon_gaps);
  set("kpiOk",    s.ok_in_db);
}

function showResults(d) {
  document.getElementById("kpiSection").classList.remove("hidden");
  document.getElementById("tableSection").classList.remove("hidden");
  document.getElementById("exportBtn").style.display = "";
  const csvBtn = document.getElementById("exportCsvBtn");
  if (csvBtn) csvBtn.style.display = "";
  // Re-apply filter tabs reset
  setFilter("all", false);
  // Scroll to results
  document.getElementById("kpiSection").scrollIntoView({ behavior: "smooth" });
}



// ── Filter ────────────────────────────────────────────────────────
function setFilter(f, doFetch = true) {
  _filter = f;
  _offset = 0;
  document.querySelectorAll(".filter-tab").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.filter === f);
  });
  if (doFetch) fetchGaps(f, _search, 0);
}

function onSearch(val) {
  clearTimeout(_searchTimer);
  _searchTimer = setTimeout(() => {
    _search = val.trim();
    _offset = 0;
    fetchGaps(_filter, _search, 0);
  }, 250);
}

// ── Fetch + Render Gaps ────────────────────────────────────────────
async function fetchGaps(type, search, offset) {
  _filter = type;
  _search = search;
  _offset = offset;

  const params = new URLSearchParams({
    type: type || "all",
    search: search || "",
    limit: LIMIT,
    offset: offset || 0,
  });

  try {
    const d = await apiFetch(`/api/gaps?${params}`);
    _totalGaps = d.total;
    renderGapTable(d.gaps, d.total, offset);
    renderPagination(d.total, offset);
    const countEl = document.getElementById("gapCount");
    if (countEl) countEl.textContent = `${d.total.toLocaleString("id-ID")} site gap`;
  } catch (e) {
    setStatus("Gagal memuat data gap: " + e.message, false);
  }
}

function renderGapTable(gaps, total, offset) {
  const tbody = document.getElementById("gapTbody");
  if (!tbody) return;

  _currentGaps = gaps || [];
  _gapPageIndices = gaps.map((_, i) => offset + i);

  if (!gaps || gaps.length === 0) {
    tbody.innerHTML = `<tr><td colspan="11">
      <div class="empty-state">
        <div class="empty-icon">✅</div>
        <div>Tidak ada gap ditemukan dengan filter saat ini.</div>
      </div>
    </td></tr>`;
    updateSelectionInfo();
    return;
  }

  tbody.innerHTML = gaps.map((g, i) => {
    const globalIdx = offset + i;
    const checked   = _selectedGapIndices.has(globalIdx) ? "checked" : "";
    const no   = offset + i + 1;
    const type = (g.type || "").toLowerCase();
    const typeBadge = type === "down"
      ? `<span class="badge badge-down">SITE DOWN</span>`
      : `<span class="badge badge-unmon">UNMONITOR</span>`;

    const dbSt = (g.dbStatus || "").toUpperCase();
    let stBadge;
    if (!g.dbStatus || g.dbStatus === "" || dbSt === "TIDAK ADA DI DB") {
      stBadge = `<span class="badge badge-notdb">Tidak ada di DB</span>`;
    } else if (dbSt === "CLOSE" || dbSt === "CLOSED") {
      stBadge = `<span class="badge badge-close">CLOSE</span>`;
    } else {
      stBadge = `<span class="badge badge-ok">${esc(g.dbStatus)}</span>`;
    }

    const siteId   = esc(g.siteId   || g.site_id   || "—");
    const siteName = esc(g.siteName || g.site_name || "—");
    const prov     = esc(g.province || g.provinsi  || "—");
    const kab      = esc(g.city     || g.kabkota   || g.kab_kota || "—");
    const durasi   = esc(g.duration || g.durasi    || "—");

    // Ticket ID: incident ticket or latest db ticket
    const incTicket = g.ticketId || g.ticket_id || "";
    const dbTicket  = g.dbTicket || (g.history && g.history[0] ? (g.history[0].ticketId || g.history[0]["Ticket ID"]) : "");
    let ticketDisplay;
    if (incTicket && incTicket !== "-" && incTicket !== "—") {
      ticketDisplay = esc(incTicket);
    } else if (dbTicket && dbTicket !== "-" && dbTicket !== "—") {
      ticketDisplay = `<span style="font-family:Consolas,monospace;font-size:12px;color:var(--signal);">${esc(dbTicket)}</span> <small style="color:var(--muted);font-size:10px;">(DB)</small>`;
    } else {
      ticketDisplay = `<span style="color:var(--muted);">—</span>`;
    }

    // Detail DB history button
    const hist = g.history || g._history || [];
    let histBtn;
    if (hist.length > 0) {
      histBtn = `<button class="btn btn-outline btn-sm" onclick="showHistory(${i})" style="padding:3px 9px;font-size:11px;font-weight:600;color:var(--accent);">
        📋 Riwayat (${hist.length})
      </button>`;
    } else {
      histBtn = `<span style="color:var(--muted);font-size:11px;">Tidak ada</span>`;
    }

    return `<tr>
      <td class="td-check"><input type="checkbox" data-gidx="${globalIdx}" ${checked} onchange="onGapCheckChange(this, ${globalIdx})" /></td>
      <td class="td-no">${no}</td>
      <td>${typeBadge}</td>
      <td class="td-siteid">${siteId}</td>
      <td>${siteName}</td>
      <td>${prov}</td>
      <td>${kab}</td>
      <td>${ticketDisplay}</td>
      <td>${stBadge}</td>
      <td>${durasi}</td>
      <td>${histBtn}</td>
    </tr>`;
  }).join("");

  // Sync "check all" header checkbox state
  const chkAll = document.getElementById("checkAllGaps");
  if (chkAll) {
    const allChecked = gaps.every((_, i) => _selectedGapIndices.has(offset + i));
    const anyChecked = gaps.some((_, i) => _selectedGapIndices.has(offset + i));
    chkAll.checked = allChecked;
    chkAll.indeterminate = !allChecked && anyChecked;
  }

  updateSelectionInfo();
}

function showHistory(index) {
  const g = _currentGaps[index];
  if (!g) return;

  const siteId   = g.siteId || g.site_id || "—";
  const siteName = g.siteName || g.site_name || "—";
  const hist     = g.history || g._history || [];

  const titleEl = document.getElementById("histModalTitle");
  const subEl   = document.getElementById("histModalSub");
  if (titleEl) titleEl.textContent = `📋 Riwayat Tiket Database: ${siteName} [${siteId}]`;
  if (subEl)   subEl.textContent   = `Ditemukan ${hist.length} tiket riwayat pada Google Sheets TT`;

  const tbody = document.getElementById("histTbody");
  if (!tbody) return;

  if (hist.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;padding:24px;color:var(--muted);">
      Belum pernah ada riwayat tiket untuk site ini di Spreadsheet.
    </td></tr>`;
  } else {
    tbody.innerHTML = hist.map(item => {
      const dq   = esc(item.dateQuery || item["Date Query"] || item["Date"] || "—");
      const tid  = esc(item.ticketId  || item["Ticket ID"]  || item["TicketID"] || "—");
      const st   = String(item.status || item["Status TT"]  || item["Status"] || "—").toUpperCase();
      const prob = esc(item.problem   || item["Problem"]    || item["Alarm Title"] || "—");
      const ct   = esc(item.closeTime || item["Close Time"] || item["Clear Time"] || "—");

      let stHtml;
      if (st === "OPEN") {
        stHtml = `<span class="badge" style="background:rgba(244,63,94,.15);color:var(--alert);">OPEN</span>`;
      } else if (st === "CLOSE" || st === "CLOSED") {
        stHtml = `<span class="badge" style="background:rgba(16,185,129,.15);color:var(--green);">CLOSE</span>`;
      } else {
        stHtml = `<span class="badge" style="background:rgba(244,185,78,.15);color:var(--signal);">${st}</span>`;
      }

      return `<tr>
        <td style="white-space:nowrap;">${dq}</td>
        <td style="font-family:Consolas,monospace;color:var(--accent);font-weight:600;">${tid}</td>
        <td>${stHtml}</td>
        <td>${prob}</td>
        <td style="white-space:nowrap;">${ct}</td>
      </tr>`;
    }).join("");
  }

  const modal = document.getElementById("historyModal");
  if (modal) modal.classList.add("show");
}

function closeHistoryModal() {
  const modal = document.getElementById("historyModal");
  if (modal) modal.classList.remove("show");
}

function esc(str) {
  return String(str)
    .replace(/&/g,"&amp;")
    .replace(/</g,"&lt;")
    .replace(/>/g,"&gt;")
    .replace(/"/g,"&quot;");
}

function renderPagination(total, offset) {
  const area = document.getElementById("paginationArea");
  if (!area) return;
  area.innerHTML = "";
  if (total <= LIMIT) return;

  const currentPage = Math.floor(offset / LIMIT);
  const totalPages  = Math.ceil(total / LIMIT);

  if (currentPage > 0) {
    const prev = document.createElement("button");
    prev.className = "btn btn-outline btn-sm";
    prev.textContent = "← Sebelumnya";
    prev.onclick = () => fetchGaps(_filter, _search, (currentPage - 1) * LIMIT);
    area.appendChild(prev);
  }

  const info = document.createElement("span");
  info.style.cssText = "font-size:12px;color:var(--muted);align-self:center;";
  info.textContent = `Hal ${currentPage + 1} / ${totalPages}`;
  area.appendChild(info);

  if (currentPage < totalPages - 1) {
    const next = document.createElement("button");
    next.className = "btn btn-outline btn-sm";
    next.textContent = "Berikutnya →";
    next.onclick = () => fetchGaps(_filter, _search, (currentPage + 1) * LIMIT);
    area.appendChild(next);
  }
}

// ── Export ────────────────────────────────────────────────────────
let _lastExportedPath = "";

async function exportGaps(format = "csv") {
  const isCsv = format === "csv";
  const ext = isCsv ? "csv" : "xlsx";
  setStatus(`Mengekspor data ke file ${ext.toUpperCase()}...`);

  try {
    const res = await fetch(`/api/export-save/${ext}`, { method: "POST" });
    if (!res.ok) {
      const j = await res.json().catch(() => ({}));
      throw new Error(j.detail || `HTTP ${res.status}`);
    }
    const d = await res.json();
    _lastExportedPath = d.path || "";
    setStatus(`Export berhasil disimpan: ${d.path}`);

    // Show custom modern Export Success modal
    showExportSuccessModal(d.filename, d.path);
  } catch (e) {
    setStatus("Export gagal: " + e.message, false);
    alert("Export gagal: " + e.message);
  }
}

function showExportSuccessModal(filename, path) {
  const box = document.getElementById("exportFilePathBox");
  if (box) box.textContent = path || filename;
  const modal = document.getElementById("exportSuccessModal");
  if (modal) modal.classList.add("show");
}

function closeExportSuccessModal() {
  const modal = document.getElementById("exportSuccessModal");
  if (modal) modal.classList.remove("show");
}

async function openExportedFileLocation() {
  try {
    const url = _lastExportedPath 
      ? `/api/open-downloads?path=${encodeURIComponent(_lastExportedPath)}`
      : `/api/open-downloads`;
    await fetch(url, { method: "POST" });
    closeExportSuccessModal();
  } catch (e) {
    alert("Gagal membuka folder: " + e.message);
  }
}

async function openDownloadsFolder() {
  try {
    await fetch("/api/open-downloads", { method: "POST" });
  } catch (e) {
    alert("Gagal membuka folder Downloads: " + e.message);
  }
}


// ── Clipboard Helper (WebView2 & Browser safe) ─────────────────────
async function copyTextToClipboard(text) {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (e) {
      // Fallback to execCommand below
    }
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.left = "-9999px";
  ta.style.top = "0";
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  const ok = document.execCommand("copy");
  document.body.removeChild(ta);
  if (!ok) throw new Error("Gagal menyalin teks ke clipboard");
  return true;
}

// ── Checkbox Selection ────────────────────────────────────────────
function toggleAllGaps(checked) {
  const rows = document.querySelectorAll("#gapTbody input[type='checkbox'][data-gidx]");
  rows.forEach(cb => {
    const idx = parseInt(cb.dataset.gidx, 10);
    cb.checked = checked;
    if (checked) {
      _selectedGapIndices.add(idx);
    } else {
      _selectedGapIndices.delete(idx);
    }
  });
  updateSelectionInfo();
}

function onGapCheckChange(cb, globalIdx) {
  if (cb.checked) {
    _selectedGapIndices.add(globalIdx);
  } else {
    _selectedGapIndices.delete(globalIdx);
  }
  // Sync header checkbox
  const chkAll = document.getElementById("checkAll") || document.getElementById("checkAllGaps");
  if (chkAll) {
    const rows = document.querySelectorAll("#gapTbody input[type='checkbox'][data-gidx]");
    const allChecked = rows.length > 0 && [...rows].every(r => r.checked);
    const anyChecked = [...rows].some(r => r.checked);
    chkAll.checked = allChecked;
    chkAll.indeterminate = !allChecked && anyChecked;
  }
  updateSelectionInfo();
}

function updateSelectionInfo() {
  const sel  = _selectedGapIndices.size;
  const info = document.getElementById("selectionInfo") || document.getElementById("selInfo");
  if (info) info.textContent = `${sel} dari ${_totalGaps} site dipilih`;

  const writeBtn = document.getElementById("btnWriteSheets") || document.getElementById("writeToSheetsBtn");
  const tsvBtn   = document.getElementById("btnCopyTsv") || document.getElementById("copyTsvBtn");
  if (writeBtn) writeBtn.disabled = sel === 0;
  if (tsvBtn)   tsvBtn.disabled   = sel === 0;
}

function getSelectedIndices() {
  return [..._selectedGapIndices].sort((a, b) => a - b);
}

// Aliases for compatibility
function openSheetsWriteModal() {
  writeToGoogleSheets();
}

function copySelectedTsv() {
  copyTsvForPaste();
}

// ── Write to Google Sheets ────────────────────────────────────────
async function writeToGoogleSheets() {
  const indices = getSelectedIndices();
  if (indices.length === 0) {
    alert("Pilih minimal satu baris yang ingin ditulis ke Google Sheets.");
    return;
  }

  const writeBtn = document.getElementById("btnWriteSheets") || document.getElementById("writeToSheetsBtn");
  if (writeBtn) {
    writeBtn.disabled = true;
    writeBtn.innerHTML = `<span class="spinner"></span> Menulis...`;
  }
  setStatus(`Menulis ${indices.length} baris ke Google Sheets...`);

  try {
    const res = await fetch("/api/write-to-sheets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ indices }),
    });
    const j = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(j.detail || `HTTP ${res.status}`);
    }
    setStatus(`✅ Berhasil menulis ${j.rows_written ?? indices.length} baris ke Google Sheets.`);
    alert(`✅ Berhasil!\n${j.rows_written ?? indices.length} baris berhasil ditulis ke sheet "Database TT" tepat di bawah sitelist terakhir.`);
  } catch (e) {
    const msg = e.message || "Unknown error";
    setStatus("Gagal tulis ke Sheets: " + msg, false);
    if (msg.includes("belum dikonfigurasi")) {
      openSheetsModal();
      showSheetsStatus("Apps Script URL belum dikonfigurasi. Anda bisa menggunakan tombol '📋 Salin Siap Paste' atau konfigurasikan URL Apps Script.", "error");
    } else {
      alert("Gagal menulis ke Google Sheets:\n" + msg + "\n\nTip: Anda juga bisa menggunakan tombol '📋 Salin Siap Paste' untuk menempel langsung ke Google Sheets.");
    }
  } finally {
    if (writeBtn) {
      writeBtn.disabled = false;
      writeBtn.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg> Tulis ke Google Sheets`;
    }
    updateSelectionInfo();
  }
}

// ── TSV Clipboard ─────────────────────────────────────────────────
async function copyTsvForPaste() {
  const indices = getSelectedIndices();
  if (indices.length === 0) {
    alert("Pilih minimal satu baris yang ingin disalin.");
    return;
  }
  await _doCopyTsv(indices);
}

async function copyTsvFromModal() {
  const indices = getSelectedIndices();
  if (indices.length === 0) {
    showSheetsStatus("Belum ada baris yang dipilih. Tutup modal dan centang baris yang ingin disalin.", "error");
    return;
  }
  await _doCopyTsv(indices, true);
}

async function _doCopyTsv(indices, fromModal = false) {
  try {
    const res = await fetch("/api/generate-tsv", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ indices }),
    });
    const j = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(j.detail || `HTTP ${res.status}`);

    await copyTextToClipboard(j.tsv || "");
    const msg = `✅ ${j.rows} baris berhasil disalin ke clipboard!\n\nCara menempel ke Google Sheets:\n1. Buka sheet "Database TT"\n2. Klik sel kosong di kolom C (Site ID) pada baris tepat di bawah sitelist terakhir\n3. Tekan Ctrl+V untuk Paste`;
    if (fromModal) {
      showSheetsStatus(`✅ ${j.rows} baris berhasil disalin ke clipboard. Paste ke Google Sheets sekarang.`, "success");
    } else {
      setStatus(`Disalin: ${j.rows} baris siap paste ke Google Sheets.`);
      alert(msg);
    }
  } catch (e) {
    const errMsg = "Gagal menyalin: " + (e.message || "Unknown error");
    if (fromModal) {
      showSheetsStatus(errMsg, "error");
    } else {
      setStatus(errMsg, false);
      alert(errMsg);
    }
  }
}

// ── Sheets Modal ──────────────────────────────────────────────────
async function openSheetsModal() {
  const modal = document.getElementById("sheetsSyncModal");
  if (modal) modal.classList.add("show");
  // Load saved URL
  try {
    const d = await apiFetch("/api/sheets-settings");
    const inp = document.getElementById("appsScriptUrlInput");
    if (inp && d.apps_script_url) inp.value = d.apps_script_url;
    const footerInfo = document.getElementById("sheetsModalFooterInfo");
    if (footerInfo) {
      footerInfo.textContent = d.apps_script_url
        ? `✅ Apps Script URL tersimpan`
        : `⚠ Apps Script URL belum dikonfigurasi`;
    }
    // Update write button state
    const writeBtn = document.getElementById("writeToSheetsBtn");
    if (writeBtn) {
      writeBtn.title = d.apps_script_url
        ? "Tulis langsung via Apps Script"
        : "Konfigurasi Apps Script URL terlebih dahulu";
    }
  } catch {}
  // Show current selection
  const sel = _selectedGapIndices.size;
  showSheetsStatus(
    sel > 0
      ? `${sel} baris terpilih. Gunakan Opsi A (otomatis) atau Opsi B (paste manual).`
      : `Belum ada baris terpilih. Tutup modal dan centang baris yang ingin ditulis.`,
    "info"
  );
}

function closeSheetsModal() {
  const modal = document.getElementById("sheetsSyncModal");
  if (modal) modal.classList.remove("show");
}

function showSheetsStatus(msg, type = "info") {
  const box = document.getElementById("sheetsStatusBox");
  if (!box) return;
  box.textContent = msg;
  box.className = `sheets-status-box ${type}`;
  box.style.display = "block";
}

async function saveAppsScriptUrl() {
  const inp = document.getElementById("appsScriptUrlInput");
  if (!inp) return;
  const url = inp.value.trim();
  try {
    const d = await apiFetch("/api/sheets-settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ apps_script_url: url }),
    });
    showSheetsStatus("✅ URL berhasil disimpan! Sekarang Anda dapat menggunakan tombol 'Tulis ke Google Sheets'.", "success");
    const footerInfo = document.getElementById("sheetsModalFooterInfo");
    if (footerInfo) footerInfo.textContent = url ? "✅ Apps Script URL tersimpan" : "URL dihapus";
  } catch (e) {
    showSheetsStatus("Gagal menyimpan URL: " + e.message, "error");
  }
}

function copyGasCode() {
  const snippet = document.getElementById("gasSnippet");
  if (!snippet) return;
  navigator.clipboard.writeText(snippet.textContent || "")
    .then(() => {
      showSheetsStatus("✅ Kode Google Apps Script berhasil disalin ke clipboard!", "success");
    })
    .catch(() => {
      showSheetsStatus("Gagal menyalin kode. Silakan salin secara manual.", "error");
    });
}

// ── Reset Selection when results hidden ───────────────────────────
function hideResults() {
  document.getElementById("kpiSection").classList.add("hidden");
  document.getElementById("tableSection").classList.add("hidden");
  document.getElementById("exportBtn").style.display = "none";
  const csvBtn = document.getElementById("exportCsvBtn");
  if (csvBtn) csvBtn.style.display = "none";
  // Reset selection
  _selectedGapIndices.clear();
  updateSelectionInfo();
}

// ── Init ──────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  // Theme
  const saved = localStorage.getItem("noc_theme") || "dark";
  applyTheme(saved);

  // Clock
  startClock();

  // Load DB status
  loadDbStatus();
});

