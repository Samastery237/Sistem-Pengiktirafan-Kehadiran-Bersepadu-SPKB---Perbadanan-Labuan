/* admin.js — Admin Panel Logic (Django Backend) */

const API_BASE = 'http://localhost:8000/api/attendance/';
const DEFAULT_PW = 'admin123';

let currentProgramId = null;
let cachedRecords = [];
let selectedParticipant = null;

// ═══════════════════════════════════════
//  AUTH
// ═══════════════════════════════════════

let initialSettings = null;

function doLogin() {
  const user = document.getElementById('admin-username')?.value.trim();
  const pw = document.getElementById('admin-password').value;
  const stored = localStorage.getItem('pl_admin_pw') || DEFAULT_PW;
  if (user === 'Administrator' && pw === stored) {
    localStorage.setItem('pl_admin_session', '1');
    showAdmin();
  } else {
    const err = document.getElementById('login-error');
    err.classList.add('show');
    err.textContent = user !== 'Administrator' ? 'Username salah.' : 'Kata laluan salah.';
    document.getElementById('admin-password').classList.add('error');
    document.getElementById('admin-username')?.classList.add('error');
  }
}

function performLogout() {
  localStorage.removeItem('pl_admin_session');
  location.reload();
}

function confirmLogout() {
  if (hasUnsavedChanges()) {
    openConfirmModal({
      title: 'Perubahan Belum Disimpan',
      message: 'Anda ada perubahan yang belum disimpan. Log keluar akan menyebabkan perubahan hilang. Anda pasti ingin log keluar?',
      confirmText: 'Log Keluar',
      confirmClass: 'btn-danger',
      icon: 'log-out',
      onConfirm: performLogout
    });
  } else {
    openConfirmModal({
      title: 'Log Keluar',
      message: 'Anda pasti ingin log keluar dari panel admin?',
      confirmText: 'Log Keluar',
      confirmClass: 'btn-danger',
      icon: 'log-out',
      onConfirm: performLogout
    });
  }
}

// Get current settings from UI (same as saveSettings but without saving)
function getCurrentSettingsFromUI() {
  const g = id => document.getElementById(id)?.value;
  const gn = id => parseInt(document.getElementById(id)?.value) || 0;
  const gc = id => document.getElementById(id)?.checked ?? false;
  return {
    nameX: gn('name-x'), nameY: gn('name-y'), nameFontSize: gn('name-size'),
    icX: gn('ic-x'), icY: gn('ic-y'), icFontSize: gn('ic-size'),
    showIC: gc('show-ic-on-cert'), textColor: g('text-color') || '#f0f4f8',
    fontFamily: g('font-family') || 'Palatino, serif',
    eventName: g('event-name') || '', eventDate: g('event-date-display') || '',
    organizer: g('event-organizer') || 'Perbadanan Labuan',
    certDelayHours: gn('cert-delay-hours'), certDelayMinutes: gn('cert-delay-minutes'),
  };
}

// Check if there are unsaved changes in the settings tab
function hasUnsavedChanges() {
  if (initialSettings === null) return false;
  const current = getCurrentSettingsFromUI();
  return JSON.stringify(current) !== JSON.stringify(initialSettings);
}

// Confirm navigation to home (index.html) if there are unsaved changes
function confirmNavigateHome() {
  if (hasUnsavedChanges()) {
    openConfirmModal({
      title: 'Perubahan Belum Disimpan',
      message: 'Anda ada perubahan yang belum disimpan. Pergi ke laman utama akan menyebabkan perubahan hilang. Anda pasti ingin pergi?',
      confirmText: 'Teruskan',
      confirmClass: 'btn-primary',
      icon: 'home',
      onConfirm: () => window.location.href = 'index.html'
    });
  } else {
    window.location.href = 'index.html';
  }
}

// TDD Demonstration: New validation function
window.isValidPassword = function(pwd) {
  if (!pwd || pwd.length < 6) return false;
  if (!/\d/.test(pwd)) return false; // must contain at least 1 number
  return true;
};

function changePassword() {
  const np = document.getElementById('new-password').value;
  const cp = document.getElementById('confirm-password').value;
  const el = document.getElementById('pw-status');
  if (!window.isValidPassword(np)) { el.style.display = 'block'; el.style.color = '#f87171'; el.textContent = 'Minimum 6 aksara & 1 nombor.'; return; }
  if (np !== cp) { el.style.display = 'block'; el.style.color = '#f87171'; el.textContent = 'Kata laluan tidak sepadan.'; return; }
  localStorage.setItem('pl_admin_pw', np);
  el.style.display = 'block'; el.style.color = '#4ade80'; el.textContent = '✅ Berjaya ditukar!';
  document.getElementById('new-password').value = '';
  document.getElementById('confirm-password').value = '';
}

function showAdmin() {
  document.getElementById('login-overlay').style.display = 'none';
  document.getElementById('admin-app').classList.add('visible');
  document.getElementById('logout-btn').style.display = 'flex';
  
  // Restore the active tab if it was saved (helps with Live Server auto-reloads)
  const savedTab = localStorage.getItem('active_admin_tab');
  if (savedTab) {
    switchTab(savedTab);
  }
  
  loadPrograms();
  loadSettings();
  refreshData();
}

// ═══════════════════════════════════════
//  API HELPERS
// ═══════════════════════════════════════

async function api(endpoint, opts = {}) {
  const url = API_BASE + endpoint;
  const config = { headers: { 'Content-Type': 'application/json' }, ...opts };
  if (opts.body && typeof opts.body === 'object') config.body = JSON.stringify(opts.body);
  const res = await fetch(url, config);
  if (endpoint.includes('export')) return res;
  return res.json();
}

// ═══════════════════════════════════════
//  PROGRAMS
// ═══════════════════════════════════════

async function loadPrograms() {
  try {
    const res = await api('programs/');
    const sel = document.getElementById('program-selector');
    if (!sel || !res.data) return;
    sel.innerHTML = '<option value="">Semua Program / All Programs</option>';
    res.data.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = `${p.name} (${p.count})`;
      if (String(p.id) === String(currentProgramId)) opt.selected = true;
      sel.appendChild(opt);
    });
  } catch (e) { console.error('loadPrograms:', e); }
}

function changeProgram(val) {
  currentProgramId = val || null;
  refreshData();
  loadSettings(); // Reload cert_delay from the selected program
  showToast('📁 Program ditukar.', 'success');
}

async function createNewProgram() {
  openPromptModal({
    title: 'Tambah Program Baru',
    placeholder: 'Nama program baru...',
    confirmText: 'Tambah',
    onConfirm: async (name) => {
      if (!name || !name.trim()) return;
      try {
        const res = await api('programs/', { method: 'POST', body: { name: name.trim() } });
        if (res.status === 'success') {
          showToast('✅ Program ditambah!', 'success');
          currentProgramId = res.id;
          await loadPrograms();
          refreshData();
        }
      } catch (e) {
        showToast('❌ Gagal menambah program.', 'error');
      }
    }
  });
}

function showShareableLink() {
  if (!currentProgramId) { 
    openConfirmModal({ isAlert: true, title: 'Perhatian', message: 'Sila pilih program tertentu.', confirmText: 'OK', icon: 'info' }); 
    return; 
  }
  const programName = document.querySelector('#program-selector option:checked').text.split(' (')[0];
  const baseUrl = window.location.origin + window.location.pathname.replace('admin.html', 'form.html');
  const shareableLink = `${baseUrl}?program=${encodeURIComponent(programName)}`;
  
  openPromptModal({
    title: `Link untuk program "${programName}"`,
    defaultValue: shareableLink,
    readOnly: true,
    onConfirm: (val) => {
      navigator.clipboard.writeText(val);
      showToast('✅ Link disalin!', 'success');
    }
  });
}

async function deleteCurrentProgram() {
  if (!currentProgramId) { 
    openConfirmModal({ isAlert: true, title: 'Perhatian', message: 'Sila pilih program tertentu.', confirmText: 'OK', icon: 'info' }); 
    return; 
  }
  
  openConfirmModal({
    title: 'Padam Program?',
    message: 'Adakah anda mahu memadam program ini dan SEMUA rekod kehadirannya?',
    subMessage: 'Tindakan ini tidak boleh dibatalkan.',
    confirmText: 'Padam Program',
    confirmClass: 'btn-danger',
    icon: 'trash-2',
    onConfirm: async () => {
      try {
        const res = await api(`programs/${currentProgramId}/`, { method: 'DELETE' });
        if (res.status === 'success') {
          showToast('✅ Program dipadam!', 'success');
          currentProgramId = '';
          loadPrograms();
          refreshData();
        }
      } catch (e) {
        showToast('❌ Ralat memadam program.', 'error');
      }
    }
  });
}

// ═══════════════════════════════════════
//  DATA REFRESH
// ═══════════════════════════════════════

async function refreshData() {
  await fetchRecords();
  renderAttendance();
  renderCertList();
  await updateStats();
}

async function fetchRecords(search) {
  try {
    let ep = 'records/';
    const params = [];
    if (currentProgramId) params.push(`program=${currentProgramId}`);
    if (search) params.push(`search=${encodeURIComponent(search)}`);
    if (params.length) ep += '?' + params.join('&');
    const res = await api(ep);
    cachedRecords = res.data || [];
  } catch (e) {
    console.error('fetchRecords:', e);
    cachedRecords = [];
  }
}

// ═══════════════════════════════════════
//  STATS
// ═══════════════════════════════════════

async function updateStats() {
  try {
    let ep = 'stats/';
    if (currentProgramId) ep += `?program=${currentProgramId}`;
    const s = await api(ep);
    document.getElementById('stat-total').textContent = s.total || 0;
    document.getElementById('stat-today').textContent = s.today || 0;
    document.getElementById('stat-certs').textContent = s.certs || 0;
  } catch (e) { console.error('updateStats:', e); }
}

// ═══════════════════════════════════════
//  ATTENDANCE TABLE
// ═══════════════════════════════════════

function renderAttendance() {
  const tbody = document.getElementById('attendance-tbody');
  const empty = document.getElementById('empty-state');
  if (!cachedRecords.length) { tbody.innerHTML = ''; empty.style.display = 'block'; return; }
  empty.style.display = 'none';
  tbody.innerHTML = cachedRecords.map((r, i) => `
    <tr>
      <td><input type="checkbox" class="row-check" data-id="${r.id}" onchange="updateBulkBar()" /></td>
      <td style="color:var(--text-muted);font-size:0.8rem;">${i + 1}</td>
      <td><strong>${esc(r.fullname)}</strong></td>
      <td style="font-family:monospace;font-size:0.82rem;">${esc(r.ic_number)}</td>
      <td style="font-size:0.85rem;">${esc(r.phone)}</td>
      <td style="font-size:0.82rem;color:var(--text-muted);">${esc(r.email) || '—'}</td>
      <td style="font-size:0.82rem;color:var(--text-muted);">${esc(r.organization) || '—'}</td>
      <td style="font-size:0.78rem;color:var(--text-muted);white-space:nowrap;">${esc(r.timestamp)}</td>
      <td>
        <div style="display:flex; gap:0.5rem; justify-content:center;">
          <button class="btn btn-sm" onclick="previewCertFor('${r.id}')" title="Papar Sijil" style="padding:0.4rem; background:transparent; border:none; color:#60a5fa;"><i data-lucide="award" style="stroke-width:2.5;"></i></button>
          <button class="btn btn-sm" onclick="openEditModal('${r.id}')" title="Kemaskini" style="padding:0.4rem; background:transparent; border:none; color:#fbbf24;"><i data-lucide="user-pen" style="stroke-width:2.5;"></i></button>
          <button class="btn btn-sm" onclick="deleteRecord('${r.id}')" title="Padam" style="padding:0.4rem; background:transparent; border:none; color:#f87171;"><i data-lucide="trash-2" style="stroke-width:2.5;"></i></button>
        </div>
      </td>
    </tr>
  `).join('');
  if (window.lucide) lucide.createIcons();
}

function esc(s) { if (!s) return ''; const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

async function filterTable() {
  const q = document.getElementById('search-input').value.trim().toLowerCase();
  await fetchRecords(q);
  renderAttendance();
}

function toggleAll(cb) { document.querySelectorAll('.row-check').forEach(c => c.checked = cb.checked); updateBulkBar(); }

function updateBulkBar() {
  const n = document.querySelectorAll('.row-check:checked').length;
  document.getElementById('bulk-count').textContent = `${n} dipilih`;
  document.getElementById('bulk-bar').classList.toggle('show', n > 0);
}

function deselectAll() {
  document.querySelectorAll('.row-check').forEach(c => c.checked = false);
  const ca = document.getElementById('check-all'); if (ca) ca.checked = false;
  updateBulkBar();
}

async function deleteRecord(id) {
  openConfirmModal({
    title: 'Padam Rekod?',
    message: 'Adakah anda mahu memadam rekod peserta ini?',
    subMessage: 'Tindakan ini tidak boleh dibatalkan.',
    confirmText: 'Padam Rekod',
    confirmClass: 'btn-danger',
    icon: 'trash-2',
    onConfirm: async () => {
      try {
        await api(`records/${id}/`, { method: 'DELETE' });
        await refreshData();
        showToast('🗑️ Rekod dipadam.', 'info');
      } catch (e) {
        showToast('❌ Ralat memadam rekod.', 'error');
      }
    }
  });
}

// ──────────────────────────────────────────────
// Participant Edit Modal
// ──────────────────────────────────────────────
function openEditModal(id) {
  const record = cachedRecords.find(r => r.id === id);
  if (!record) return;
  document.getElementById('edit-id').value = record.id;
  document.getElementById('edit-fullname').value = record.fullname;
  document.getElementById('edit-ic').value = record.ic_number;
  document.getElementById('edit-phone').value = record.phone || '';
  document.getElementById('edit-email').value = record.email || '';
  document.getElementById('edit-org').value = record.organization || '';
  document.getElementById('edit-modal').style.display = 'flex';
}

function closeEditModal() {
  document.getElementById('edit-modal').style.display = 'none';
}

async function saveParticipantEdit() {
  const id = document.getElementById('edit-id').value;
  const data = {
    fullname: document.getElementById('edit-fullname').value,
    ic_number: document.getElementById('edit-ic').value,
    phone: document.getElementById('edit-phone').value,
    email: document.getElementById('edit-email').value,
    organization: document.getElementById('edit-org').value
  };

  try {
    const res = await api(`records/${id}/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (res.status === 'success') {
      showToast('✅ Maklumat berjaya dikemaskini!', 'success');
      closeEditModal();
      await refreshData(); // refresh table and UI
    } else {
      showToast('Gagal mengemaskini maklumat.', 'error');
    }
  } catch (e) {
    showToast('Ralat pelayan.', 'error');
  }
}

// ═══════════════════════════════════════
//  CSV EXPORT
// ═══════════════════════════════════════

function exportCSV() {
  let url = API_BASE + 'export/';
  if (currentProgramId) url += `?program=${currentProgramId}`;
  window.open(url, '_blank');
  showToast('📥 CSV dimuat turun!', 'success');
}

// ═══════════════════════════════════════
//  TABS
// ═══════════════════════════════════════

function switchTab(tab) {
  localStorage.setItem('active_admin_tab', tab); // Persist tab state across reloads
  ['attendance', 'certificate', 'settings'].forEach(t => {
    document.getElementById(`tab-${t}`)?.classList.remove('active');
    document.getElementById(`tab-${t}-btn`)?.classList.remove('active');
  });
  document.getElementById(`tab-${tab}`)?.classList.add('active');
  document.getElementById(`tab-${tab}-btn`)?.classList.add('active');
  if (tab === 'certificate') renderCertList();

  // Capture initial settings when entering the settings tab
  if (tab === 'settings') {
    initialSettings = getCurrentSettingsFromUI();
  }
}

// ═══════════════════════════════════════
//  TOAST
// ═══════════════════════════════════════

function showToast(msg, type = 'info') {
  const toast = document.getElementById('toast');
  toast.textContent = msg;
  toast.className = `toast toast-${type} show`;
  setTimeout(() => toast.classList.remove('show'), 3500);
}

// ═══════════════════════════════════════
//  CERTIFICATE LIST & PREVIEW
// ═══════════════════════════════════════

function renderCertList(filter = '') {
  const filtered = filter
    ? cachedRecords.filter(r => r.fullname?.toLowerCase().includes(filter) || r.ic_number?.includes(filter))
    : cachedRecords;
  const list = document.getElementById('cert-participant-list');
  if (!list) return;
  if (!filtered.length) {
    list.innerHTML = '<div style="text-align:center;color:var(--text-muted);font-size:0.85rem;padding:1rem;">Tiada peserta.</div>';
    return;
  }
  list.innerHTML = filtered.map(r => `
    <button class="sidebar-item ${selectedParticipant?.id === r.id ? 'active' : ''}"
      onclick="selectParticipant('${r.id}')" style="font-size:0.82rem;">
      <span>👤</span>
      <div>
        <div style="font-weight:600;">${esc(r.fullname)}</div>
        <div style="font-size:0.72rem;color:var(--text-muted);">${esc(r.ic_number)}</div>
      </div>
    </button>
  `).join('');
}

function filterCertList() { renderCertList(document.getElementById('cert-search').value.trim().toLowerCase()); }

function selectParticipant(id) {
  selectedParticipant = cachedRecords.find(r => r.id === id);
  renderCertList(document.getElementById('cert-search')?.value.trim().toLowerCase() || '');
  drawCertificate(selectedParticipant);
}

function previewCertFor(id) { switchTab('certificate'); setTimeout(() => selectParticipant(id), 100); }

// ═══════════════════════════════════════
//  CERTIFICATE DRAWING (Canvas)
// ═══════════════════════════════════════

async function drawCertificate(p) {
  if (!p) return;
  const canvas = document.getElementById('cert-canvas');
  const ctx = canvas.getContext('2d');
  const s = getSettings();
  const tpl = localStorage.getItem('cert_template');

  document.getElementById('cert-empty').style.display = 'none';
  canvas.style.display = 'block';
  document.getElementById('cert-actions').style.display = 'block';

  if (tpl) {
    const bg = await loadImage(tpl);
    canvas.width = bg.naturalWidth || bg.width;
    canvas.height = bg.naturalHeight || bg.height;
    ctx.drawImage(bg, 0, 0, canvas.width, canvas.height);
  } else {
    canvas.width = 1000; canvas.height = 707;
    drawDefaultCertBg(ctx, 1000, 707);
  }
  overlayText(ctx, p, s, canvas.width, canvas.height);
}

function loadImage(src) {
  return new Promise((res, rej) => { const img = new Image(); img.onload = () => res(img); img.onerror = rej; img.src = src; });
}

function overlayText(ctx, p, s, w, h) {
  ctx.textAlign = 'center';
  ctx.fillStyle = s.textColor;
  ctx.font = `bold ${s.nameFontSize}px ${s.fontFamily}`;
  ctx.fillText(p.fullname, s.nameX, s.nameY);
  if (s.showIC && p.ic_number) {
    ctx.font = `bold ${s.icFontSize}px ${s.fontFamily}`;
    ctx.fillText(p.ic_number, s.icX, s.icY);
  }
}

function drawDefaultCertBg(ctx, w, h) {
  ctx.fillStyle = '#0d2238'; ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = '#c8963e'; ctx.lineWidth = 8; ctx.strokeRect(20, 20, w - 40, h - 40);
  ctx.lineWidth = 2; ctx.strokeRect(34, 34, w - 68, h - 68);
  ctx.fillStyle = '#e8b96a'; ctx.font = 'bold 28px Palatino, serif'; ctx.textAlign = 'center';
  ctx.fillText('PERBADANAN LABUAN', w / 2, 100);
  ctx.fillStyle = '#f0f4f8'; ctx.font = 'bold 38px Palatino, serif';
  ctx.fillText('SIJIL PENYERTAAN', w / 2, 160);
  ctx.fillStyle = '#94a3b8'; ctx.font = '22px Palatino, serif';
  ctx.fillText('CERTIFICATE OF PARTICIPATION', w / 2, 195);
  ctx.strokeStyle = '#c8963e'; ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.moveTo(100, 220); ctx.lineTo(w - 100, 220); ctx.stroke();
  ctx.fillStyle = '#94a3b8'; ctx.font = '20px Palatino, serif';
  ctx.fillText('Diberikan kepada / Awarded to', w / 2, 290);
  ctx.strokeStyle = '#c8963e55'; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(150, 410); ctx.lineTo(w - 150, 410); ctx.stroke();
  ctx.fillStyle = '#94a3b8'; ctx.font = '16px Palatino, serif';
  ctx.fillText('No. Kad Pengenalan / IC Number:', w / 2, 450);
  ctx.strokeStyle = '#c8963e'; ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.moveTo(100, h - 130); ctx.lineTo(w - 100, h - 130); ctx.stroke();
  ctx.fillStyle = '#94a3b8'; ctx.font = '16px Palatino, serif';
  ctx.fillText('_______________________________', w / 2, h - 90);
  ctx.fillText('Tandatangan / Signature', w / 2, h - 68);
  ctx.fillText('Perbadanan Labuan', w / 2, h - 48);
}

// ═══════════════════════════════════════
//  DOWNLOAD CERTIFICATES
// ═══════════════════════════════════════

function downloadCertPNG() {
  if (!selectedParticipant) return;
  const a = document.createElement('a');
  a.download = `sijil_${selectedParticipant.fullname.replace(/\s+/g, '_')}.png`;
  a.href = document.getElementById('cert-canvas').toDataURL('image/png');
  a.click();
}

async function downloadCertPDF() {
  if (!selectedParticipant) return;
  if (typeof window.jspdf === 'undefined') {
    showToast('⏳ Memuatkan jsPDF...', 'info');
    await loadScript('https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js');
  }
  const canvas = document.getElementById('cert-canvas');
  const { jsPDF } = window.jspdf;
  const w = canvas.width, h = canvas.height;
  const pdf = new jsPDF({ orientation: w > h ? 'landscape' : 'portrait', unit: 'px', format: [w, h] });
  pdf.addImage(canvas.toDataURL('image/png'), 'PNG', 0, 0, w, h);
  pdf.save(`sijil_${selectedParticipant.fullname.replace(/\s+/g, '_')}.pdf`);
}

async function generateAllCerts() {
  if (!cachedRecords.length) { showToast('⚠️ Tiada peserta.', 'error'); return; }
  await bulkGeneratePDF(cachedRecords, `sijil_semua_${new Date().toISOString().slice(0, 10)}.pdf`);
}

async function generateBulk() {
  const ids = [...document.querySelectorAll('.row-check:checked')].map(c => c.dataset.id);
  if (!ids.length) return;
  const records = cachedRecords.filter(r => ids.includes(r.id));
  await bulkGeneratePDF(records, `sijil_terpilih_${new Date().toISOString().slice(0, 10)}.pdf`);
  deselectAll();
}

let currentConfirmAction = null;
let currentPromptAction = null;

function openPromptModal(options) {
  document.querySelector('#prompt-modal-title span').textContent = options.title || 'Input';
  const inputEl = document.getElementById('prompt-modal-input');
  inputEl.value = options.defaultValue || '';
  inputEl.placeholder = options.placeholder || '';
  inputEl.readOnly = !!options.readOnly;
  
  const btn = document.getElementById('btn-prompt-action');
  btn.textContent = options.confirmText || 'OK';
  
  if (options.readOnly) {
    btn.textContent = 'Salin / Copy';
  }
  
  currentPromptAction = options.onConfirm;
  document.getElementById('generic-prompt-modal').style.display = 'flex';
  inputEl.focus();
  if (options.readOnly) {
    inputEl.select();
  }
}

function closePromptModal() {
  currentPromptAction = null;
  document.getElementById('generic-prompt-modal').style.display = 'none';
}

function executePromptAction() {
  const val = document.getElementById('prompt-modal-input').value;
  if (currentPromptAction) currentPromptAction(val);
  closePromptModal();
}

function openConfirmModal(options) {
  document.getElementById('confirm-modal-title').textContent = options.title || 'Adakah anda pasti?';
  document.getElementById('confirm-modal-msg').textContent = options.message || '';
  document.getElementById('confirm-modal-sub').textContent = options.subMessage || '';
  
  const btn = document.getElementById('btn-confirm-action');
  btn.textContent = options.confirmText || 'Teruskan';
  btn.className = `btn ${options.confirmClass || 'btn-primary'}`;
  
  const iconDiv = document.getElementById('confirm-modal-icon');
  iconDiv.innerHTML = `<i data-lucide="${options.icon || 'alert-circle'}" style="width:48px; height:48px;"></i>`;
  iconDiv.style.color = options.confirmClass === 'btn-danger' ? 'var(--danger)' : 'var(--primary)';
  
  const cancelBtn = document.getElementById('btn-confirm-cancel');
  if (options.isAlert) {
    cancelBtn.style.display = 'none';
  } else {
    cancelBtn.style.display = 'block';
  }
  
  const card = document.querySelector('#generic-confirm-modal .card');
  if (options.confirmClass === 'btn-danger') {
    card.style.borderTop = '4px solid var(--danger)';
  } else {
    card.style.borderTop = 'none';
  }
  
  lucide.createIcons();
  
  currentConfirmAction = options.onConfirm;
  document.getElementById('generic-confirm-modal').style.display = 'flex';
}

function closeConfirmModal() {
  currentConfirmAction = null;
  document.getElementById('generic-confirm-modal').style.display = 'none';
}

function executeConfirmAction() {
  if (currentConfirmAction) currentConfirmAction();
  closeConfirmModal();
}

async function bulkDelete() {
  const ids = [...document.querySelectorAll('.row-check:checked')].map(c => c.dataset.id);
  if (!ids.length) return;
  
  openConfirmModal({
    title: 'Adakah anda pasti?',
    message: `Adakah anda mahu memadam ${ids.length} rekod yang dipilih?`,
    subMessage: 'Tindakan ini tidak boleh dibatalkan.',
    confirmText: `Padam ${ids.length} item`,
    confirmClass: 'btn-danger',
    icon: 'triangle-alert',
    onConfirm: async () => {
      try {
        const res = await api('records/', { method: 'DELETE', body: { ids } });
        if (res.status === 'success') {
          showToast(`✅ ${res.deleted} rekod berjaya dipadam!`, 'success');
          deselectAll();
          await refreshData();
        } else {
          showToast('❌ Ralat memadam rekod.', 'error');
        }
      } catch (err) {
        console.error('Bulk delete error:', err);
        showToast('❌ Ralat rangkaian.', 'error');
      }
    }
  });
}

async function bulkGeneratePDF(records, filename) {
  showToast(`⏳ Jana ${records.length} sijil...`, 'info');
  if (typeof window.jspdf === 'undefined') await loadScript('https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js');
  const s = getSettings(); const tpl = localStorage.getItem('cert_template');
  const canvas = document.createElement('canvas'); const ctx = canvas.getContext('2d');
  const { jsPDF } = window.jspdf;
  let bg = null; if (tpl) bg = await loadImage(tpl);
  const W = bg ? (bg.naturalWidth || bg.width) : 1000;
  const H = bg ? (bg.naturalHeight || bg.height) : 707;
  const pdf = new jsPDF({ orientation: W > H ? 'landscape' : 'portrait', unit: 'px', format: [W, H] });
  for (let i = 0; i < records.length; i++) {
    canvas.width = W; canvas.height = H;
    if (bg) ctx.drawImage(bg, 0, 0, W, H); else drawDefaultCertBg(ctx, W, H);
    overlayText(ctx, records[i], s, W, H);
    if (i > 0) pdf.addPage([W, H], W > H ? 'landscape' : 'portrait');
    pdf.addImage(canvas.toDataURL('image/png'), 'PNG', 0, 0, W, H);
  }
  pdf.save(filename);
  showToast(`✅ ${records.length} sijil berjaya dijana!`, 'success');
}

function loadScript(src) { return new Promise((res, rej) => { const s = document.createElement('script'); s.src = src; s.onload = res; s.onerror = rej; document.head.appendChild(s); }); }

// ═══════════════════════════════════════
//  SETTINGS (localStorage for UI prefs)
// ═══════════════════════════════════════

function getSettings() {
  const s = JSON.parse(localStorage.getItem('cert_settings') || '{}');
  return {
    nameX: s.nameX ?? 500, nameY: s.nameY ?? 360, nameFontSize: s.nameFontSize ?? 42,
    icX: s.icX ?? 500, icY: s.icY ?? 470, icFontSize: s.icFontSize ?? 28,
    showIC: s.showIC ?? true, textColor: s.textColor ?? '#f0f4f8',
    fontFamily: s.fontFamily ?? 'Palatino, serif',
    eventName: s.eventName ?? '', eventDate: s.eventDate ?? '',
    organizer: s.organizer ?? 'Perbadanan Labuan',
    certDelayHours: s.certDelayHours ?? 0, certDelayMinutes: s.certDelayMinutes ?? 0,
  };
}

function saveSettings() {
  const g = id => document.getElementById(id)?.value;
  const gn = id => parseInt(document.getElementById(id)?.value) || 0;
  const gc = id => document.getElementById(id)?.checked ?? false;
  const settings = {
    nameX: gn('name-x'), nameY: gn('name-y'), nameFontSize: gn('name-size'),
    icX: gn('ic-x'), icY: gn('ic-y'), icFontSize: gn('ic-size'),
    showIC: gc('show-ic-on-cert'), textColor: g('text-color') || '#f0f4f8',
    fontFamily: g('font-family') || 'Palatino, serif',
    eventName: g('event-name') || '', eventDate: g('event-date-display') || '',
    organizer: g('event-organizer') || 'Perbadanan Labuan',
    certDelayHours: gn('cert-delay-hours'), certDelayMinutes: gn('cert-delay-minutes'),
  };
  localStorage.setItem('cert_settings', JSON.stringify(settings));

  // Sync cert_delay to Django (server-side) so ALL devices see the same timer
  const hours = gn('cert-delay-hours');
  const minutes = gn('cert-delay-minutes');
  const delayMs = (hours * 3600000) + (minutes * 60000);
  if (currentProgramId) {
    api(`programs/${currentProgramId}/`, {
      method: 'PATCH',
      body: { cert_delay: delayMs },
    }).then(() => {
      console.log('✅ cert_delay synced to server:', delayMs, 'ms');
    }).catch(e => console.error('cert_delay sync failed:', e));
  } else {
    // If "Semua Program" is selected, apply the timer update to all existing programs
    api('programs/').then(res => {
      if (res.data && res.data.length > 0) {
        res.data.forEach(p => {
          api(`programs/${p.id}/`, { method: 'PATCH', body: { cert_delay: delayMs } });
        });
        console.log('✅ cert_delay synced to all programs:', delayMs, 'ms');
      }
    }).catch(e => console.error('cert_delay bulk sync failed:', e));
  }

  if (selectedParticipant) drawCertificate(selectedParticipant);
}

async function loadSettings() {
  // Load UI settings from localStorage
  const s = getSettings();
  const set = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
  const chk = (id, v) => { const el = document.getElementById(id); if (el) el.checked = v; };
  set('name-x', s.nameX); set('name-y', s.nameY); set('name-size', s.nameFontSize);
  set('ic-x', s.icX); set('ic-y', s.icY); set('ic-size', s.icFontSize);
  chk('show-ic-on-cert', s.showIC); set('text-color', s.textColor); set('font-family', s.fontFamily);
  set('event-name', s.eventName); set('event-date-display', s.eventDate);
  set('event-organizer', s.organizer);

  // Load cert_delay from Django (server-side source of truth)
  try {
    let delayMs = undefined;
    if (currentProgramId) {
      const res = await api(`programs/${currentProgramId}/`);
      if (res.cert_delay !== undefined) delayMs = res.cert_delay;
    } else {
      // If "Semua Program", fetch list of programs and use the first one's delay as the representative UI value
      const res = await api('programs/');
      if (res.data && res.data.length > 0 && res.data[0].cert_delay !== undefined) {
        delayMs = res.data[0].cert_delay;
      }
    }

    if (delayMs !== undefined) {
      const h = Math.floor(delayMs / 3600000);
      const m = Math.round((delayMs % 3600000) / 60000);
      set('cert-delay-hours', h);
      set('cert-delay-minutes', m);
      return;
    }
  } catch (e) { console.warn('Could not load program cert_delay:', e); }

  // Fallback to localStorage defaults if server fetch fails completely
  set('cert-delay-hours', s.certDelayHours ?? 0);
  set('cert-delay-minutes', s.certDelayMinutes ?? 0);
}

// ═══════════════════════════════════════
//  TEMPLATE UPLOAD
// ═══════════════════════════════════════

function handleTemplateUpload(e) {
  const file = e.target.files[0]; if (!file) return;
  const reader = new FileReader();
  reader.onload = ev => {
    const img = new Image();
    img.onload = () => {
      const c = document.createElement('canvas'); const ctx = c.getContext('2d');
      let w = img.width, h = img.height;
      if (w > 1600) { h = Math.round(h * (1600 / w)); w = 1600; }
      c.width = w; c.height = h; ctx.drawImage(img, 0, 0, w, h);
      const data = c.toDataURL('image/jpeg', 0.6);
      try {
        localStorage.setItem('cert_template', data);
        const el = document.getElementById('template-preview-img');
        if (el) { el.src = data; el.style.display = 'block'; }
        showToast('✅ Templat dimuat naik!', 'success');
        if (selectedParticipant) drawCertificate(selectedParticipant);
      } catch { showToast('⚠️ Storan penuh!', 'error'); }
    };
    img.src = ev.target.result;
  };
  reader.readAsDataURL(file);
}

function clearTemplate() {
  localStorage.removeItem('cert_template');
  const img = document.getElementById('template-preview-img'); img.style.display = 'none';
  document.getElementById('template-upload').value = '';
  showToast('🗑️ Templat dipadam.', 'info');
  if (selectedParticipant) drawCertificate(selectedParticipant);
}

function useDefaultTemplate() { clearTemplate(); }

// ═══════════════════════════════════════
//  INIT
// ═══════════════════════════════════════

window.addEventListener('DOMContentLoaded', () => {
  if (localStorage.getItem('pl_admin_session')) showAdmin();

  const zone = document.getElementById('upload-zone');
  if (zone) {
    zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', e => {
      e.preventDefault(); zone.classList.remove('drag-over');
      const file = e.dataTransfer.files[0];
      if (file?.type.startsWith('image/')) {
        const input = document.getElementById('template-upload');
        const dt = new DataTransfer(); dt.items.add(file); input.files = dt.files;
        handleTemplateUpload({ target: input });
      }
    });
  }
  const saved = localStorage.getItem('cert_template');
  if (saved) { const img = document.getElementById('template-preview-img'); if (img) { img.src = saved; img.style.display = 'block'; } }
});

// ═══════════════════════════════════════
//  UI HELPERS
// ═══════════════════════════════════════

function togglePasswordVisibility(inputId) {
  const input = document.getElementById(inputId);
  const eye = document.getElementById(inputId + '-eye');
  const eyeOff = document.getElementById(inputId + '-eye-off');
  
  if (!input) return;
  
  if (input.type === 'password') {
    input.type = 'text';
    if (eye) eye.style.display = 'none';
    if (eyeOff) eyeOff.style.display = 'block';
  } else {
    input.type = 'password';
    if (eye) eye.style.display = 'block';
    if (eyeOff) eyeOff.style.display = 'none';
  }
}
