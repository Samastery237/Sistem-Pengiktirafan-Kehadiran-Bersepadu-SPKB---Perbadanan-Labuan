/* admin.js — Admin Panel Logic (Django Backend) */

const API_BASE = `http://${window.location.hostname}:8000/api/attendance/`;
const DEFAULT_PW = 'admin123';

let currentDepartmentId = null;
let currentFolderId = null;
let departmentsData = [];
let currentFolderData = null;
let cachedRecords = [];
let selectedParticipant = null;
let currentUserRole = { is_super: false, department_id: null };

// ═══════════════════════════════════════
//  AUTH
// ═══════════════════════════════════════

let initialSettings = null;

// Helper to get CSRF token from cookies
function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

async function doLogin() {
  const btn = document.getElementById('login-btn');
  if (btn && btn.disabled) return; // Prevent submission during countdown

  const user = document.getElementById('admin-username')?.value.trim() || 'admin';
  const pw = document.getElementById('admin-password').value;
  
  try {
    const res = await fetch(API_BASE + 'auth/login/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ username: user, password: pw })
    });

    if (res.status === 429) {
      const retryAfter = parseInt(res.headers.get('Retry-After') || '60', 10);
      startLoginCountdown(retryAfter);
      return;
    }

    const data = await res.json();
    
    if (res.ok && data.status === 'success') {
      if (data.csrfToken) localStorage.setItem('pl_csrf', data.csrfToken);
      currentUserRole.is_super = data.is_super;
      currentUserRole.department_id = data.department_id;
      showAdmin();
    } else {
      throw new Error(data.message || 'Log masuk gagal.');
    }
  } catch (e) {
    const err = document.getElementById('login-error');
    err.classList.add('show');
    err.textContent = e.message || 'Kata laluan atau ID pengguna salah.';
    document.getElementById('admin-password').classList.add('error');
    document.getElementById('admin-username')?.classList.add('error');
  }
}

function startLoginCountdown(seconds) {
  const btn = document.getElementById('login-btn');
  const err = document.getElementById('login-error');
  const initialText = btn.innerHTML;
  
  btn.disabled = true;
  btn.style.opacity = '0.5';
  btn.style.cursor = 'not-allowed';
  err.classList.add('show');
  document.getElementById('admin-password').classList.add('error');
  document.getElementById('admin-username')?.classList.add('error');
  
  let remaining = seconds;
  const updateUI = () => {
    err.textContent = `Terlalu banyak cubaan. Sila tunggu ${remaining} saat.`;
    btn.innerHTML = `<i data-lucide="lock"></i> Tunggu ${remaining}s`;
    if (window.lucide) lucide.createIcons();
  };
  updateUI();

  const interval = setInterval(() => {
    remaining--;
    if (remaining <= 0) {
      clearInterval(interval);
      btn.disabled = false;
      btn.style.opacity = '1';
      btn.style.cursor = 'pointer';
      btn.innerHTML = initialText;
      err.classList.remove('show');
      err.textContent = '';
      document.getElementById('admin-password').classList.remove('error');
      document.getElementById('admin-username')?.classList.remove('error');
      if (window.lucide) lucide.createIcons();
    } else {
      updateUI();
    }
  }, 1000);
}

async function performLogout(callApi = true) {
  if (callApi) {
    try { await api('auth/logout/', { method: 'POST' }); } catch(e) {}
  }
  localStorage.removeItem('pl_csrf');
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
    showIC: true, textColor: g('text-color') || '#f0f4f8',
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

function openChangePasswordModal() {
  document.getElementById('modal-new-password').value = '';
  document.getElementById('modal-confirm-password').value = '';
  document.getElementById('modal-pw-status').style.display = 'none';
  document.getElementById('change-password-modal').style.display = 'flex';
}

function closeChangePasswordModal() {
  document.getElementById('change-password-modal').style.display = 'none';
}

async function submitChangePassword() {
  const np = document.getElementById('modal-new-password').value;
  const cp = document.getElementById('modal-confirm-password').value;
  const el = document.getElementById('modal-pw-status');
  
  if (!window.isValidPassword(np)) { 
    el.style.display = 'block'; el.style.color = '#f87171'; 
    el.textContent = 'Minimum 6 aksara & 1 nombor.'; 
    return; 
  }
  if (np !== cp) { 
    el.style.display = 'block'; el.style.color = '#f87171'; 
    el.textContent = 'Kata laluan tidak sepadan.'; 
    return; 
  }
  
  try {
    const res = await api('auth/change-password/', { method: 'POST', body: { new_password: np } });
    if (res.status === 'success') {
      showToast('<i class="fa-solid fa-circle-check"></i> Kata laluan berjaya ditukar!', 'success');
      closeChangePasswordModal();
    } else {
      el.style.display = 'block'; el.style.color = '#f87171'; 
      el.textContent = res.message || 'Ralat menukar kata laluan.';
    }
  } catch(e) {
    el.style.display = 'block'; el.style.color = '#f87171'; 
    el.textContent = 'Ralat rangkaian.';
  }
}

function showAdmin() {
  document.getElementById('login-overlay').style.display = 'none';
  document.getElementById('admin-app').classList.add('visible');
  document.getElementById('logout-btn').style.display = 'flex';
  const cpBtn = document.getElementById('btn-open-cp');
  if (cpBtn) {
    cpBtn.style.display = currentUserRole.is_super ? 'flex' : 'none';
  }
  
  if (currentUserRole.is_super) {
    document.getElementById('tab-users-btn').style.display = 'inline-block';
    loadUsers();
  } else {
    document.getElementById('tab-users-btn').style.display = 'none';
  }
  
  // Restore the active tab if it was saved (helps with Live Server auto-reloads)
  const savedTab = localStorage.getItem('active_admin_tab');
  if (savedTab && (savedTab !== 'users' || currentUserRole.is_super)) {
    switchTab(savedTab);
  } else {
    switchTab('attendance');
  }
  
  loadHierarchy();
  loadSettings();
  refreshData();
}

// ═══════════════════════════════════════
//  API HELPERS
// ═══════════════════════════════════════

async function api(endpoint, opts = {}) {
  const url = API_BASE + endpoint;
  const config = { headers: { 'Content-Type': 'application/json' }, credentials: 'include', ...opts };
  
  // Attach CSRF token for mutating requests
  const csrf = getCookie('csrftoken') || localStorage.getItem('pl_csrf');
  if (csrf && (!opts.method || !['GET', 'HEAD', 'OPTIONS'].includes(opts.method.toUpperCase()))) {
    config.headers['X-CSRFToken'] = csrf;
  }
  
  if (opts.body && typeof opts.body === 'object') config.body = JSON.stringify(opts.body);
  const res = await fetch(url, config);
  
  if (res.status === 401 || res.status === 403) {
    // Session expired or unauthorized
    if (!endpoint.includes('auth/check')) {
      performLogout(false);
    }
    return Promise.reject('Unauthorized');
  }
  
  if (endpoint.includes('export')) return res;
  return res.json();
}

// ═══════════════════════════════════════
//  DEPARTMENTS & FOLDERS
// ═══════════════════════════════════════

async function loadHierarchy() {
  try {
    const res = await api('folders/');
    if (!res.data) return;
    departmentsData = res.data;
    
    const deptSel = document.getElementById('department-selector');
    if (!deptSel) return;
    
    deptSel.innerHTML = '<option value="">Semua Jabatan</option>';
    departmentsData.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d.id;
      opt.textContent = d.name;
      if (String(d.id) === String(currentDepartmentId)) opt.selected = true;
      deptSel.appendChild(opt);
    });
    
    populateFolders();
  } catch (e) { console.error('loadHierarchy:', e); }
}

function populateFolders() {
  const folderSel = document.getElementById('folder-selector');
  const btnAdd = document.getElementById('btn-add-folder');
  const btnLink = document.getElementById('btn-link-folder');
  const btnDel = document.getElementById('btn-del-folder');
  
  if (!currentDepartmentId) {
    folderSel.innerHTML = '<option value="">-- Pilih Jabatan Dahulu --</option>';
    folderSel.disabled = true;
    btnAdd.disabled = true;
    btnLink.disabled = true;
    btnDel.disabled = true;
    currentFolderId = null;
    currentFolderData = null;
    return;
  }
  
  folderSel.disabled = false;
  btnAdd.disabled = false;
  btnLink.disabled = !currentFolderId;
  btnDel.disabled = !currentFolderId;
  
  const dept = departmentsData.find(d => String(d.id) === String(currentDepartmentId));
  folderSel.innerHTML = '<option value="">-- Pilih Folder --</option>';
  
  if (dept && dept.folders) {
    dept.folders.forEach(f => {
      const opt = document.createElement('option');
      opt.value = f.id;
      opt.textContent = `${f.name} (${f.count})`;
      if (String(f.id) === String(currentFolderId)) {
          opt.selected = true;
          currentFolderData = f;
      }
      folderSel.appendChild(opt);
    });
  }
}

function clearCertificateView() {
  selectedParticipant = null;
  const canvas = document.getElementById('cert-canvas');
  if (canvas) canvas.style.display = 'none';
  const actions = document.getElementById('cert-actions');
  if (actions) actions.style.display = 'none';
  const empty = document.getElementById('cert-empty');
  if (empty) empty.style.display = 'flex';
}

function changeDepartment(val) {
  currentDepartmentId = val || null;
  currentFolderId = null;
  currentFolderData = null;
  populateFolders();
  clearCertificateView();
  refreshData();
  loadSettings();
}

function changeFolder(val) {
  currentFolderId = val || null;
  const dept = departmentsData.find(d => String(d.id) === String(currentDepartmentId));
  if (dept) {
      currentFolderData = dept.folders.find(f => String(f.id) === String(currentFolderId));
  } else {
      currentFolderData = null;
  }
  
  const btnLink = document.getElementById('btn-link-folder');
  const btnDel = document.getElementById('btn-del-folder');
  if (btnLink) btnLink.disabled = !currentFolderId;
  if (btnDel) btnDel.disabled = !currentFolderId;
  
  clearCertificateView();
  refreshData();
  loadSettings();
  showToast('<i class="fa-solid fa-folder"></i> Folder ditukar.', 'success');
}


async function createNewFolder() {
  if (!currentDepartmentId) return;
  const dept = departmentsData.find(d => String(d.id) === String(currentDepartmentId));
  openPromptModal({
    title: `Tambah Folder untuk ${dept.name}`,
    placeholder: 'Nama program/folder baru...',
    confirmText: 'Tambah',
    onConfirm: async (name) => {
      if (!name || !name.trim()) return;
      try {
        const res = await api('folders/', { method: 'POST', body: { department: dept.name, folder: name.trim() } });
        if (res.status === 'success') {
          showToast('<i class="fa-solid fa-circle-check"></i> Folder ditambah!', 'success');
          await loadHierarchy();
          document.getElementById('folder-selector').value = res.folder_id;
          changeFolder(res.folder_id);
        }
      } catch (e) { showToast('<i class="fa-solid fa-circle-xmark"></i> Gagal menambah folder.', 'error'); }
    }
  });
}


function showShareableLink() {
  if (!currentFolderId) { 
    openConfirmModal({ isAlert: true, title: 'Perhatian', message: 'Sila pilih folder tertentu.', confirmText: 'OK', icon: 'info' }); 
    return; 
  }
  const deptName = departmentsData.find(d => String(d.id) === String(currentDepartmentId))?.name;
  const folderName = currentFolderData?.name;
  
  const baseUrl = window.location.origin + window.location.pathname.replace('admin.html', 'form.html');
  const shareableLink = `${baseUrl}?dept=${encodeURIComponent(deptName)}&folder=${encodeURIComponent(folderName)}`;
  
  openPromptModal({
    title: `Link untuk "${folderName}"`,
    defaultValue: shareableLink,
    readOnly: true,
    onConfirm: (val) => {
      navigator.clipboard.writeText(val);
      showToast('<i class="fa-solid fa-circle-check"></i> Link disalin!', 'success');
    }
  });
}

async function deleteCurrentFolder() {
  if (!currentFolderId) { 
    openConfirmModal({ isAlert: true, title: 'Perhatian', message: 'Sila pilih folder.', confirmText: 'OK', icon: 'info' }); 
    return; 
  }
  
  openConfirmModal({
    title: 'Padam Folder?',
    message: 'Adakah anda mahu memadam folder ini dan SEMUA rekod kehadirannya?',
    subMessage: 'Tindakan ini tidak boleh dibatalkan.',
    confirmText: 'Padam Folder',
    confirmClass: 'btn-danger',
    icon: 'trash-2',
    onConfirm: async () => {
      try {
        const res = await api(`folders/${currentFolderId}/`, { method: 'DELETE' });
        if (res.status === 'success') {
          showToast('<i class="fa-solid fa-circle-check"></i> Folder dipadam!', 'success');
          currentFolderId = null;
          currentFolderData = null; // Explicitly clear local memory!
          loadHierarchy();
          clearCertificateView();
          refreshData();
          loadSettings(); // Reset the UI forms
        }
      } catch (e) {
        showToast('<i class="fa-solid fa-circle-xmark"></i> Ralat memadam folder.', 'error');
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
    if (currentFolderId) params.push(`folder=${currentFolderId}`);
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
    if (currentFolderId) ep += `?folder=${currentFolderId}`;
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
  tbody.innerHTML = cachedRecords.map((r, i) => {
    const localDate = new Date(r.raw_date);
    const formattedDate = isNaN(localDate) ? esc(r.timestamp) : localDate.toLocaleString('en-GB', {
      day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit', hour12: true
    }).replace(',', '');

    return `
    <tr>
      <td><input type="checkbox" class="row-check" data-id="${r.id}" onchange="updateBulkBar()" /></td>
      <td style="color:var(--text-muted);font-size:0.8rem;">${i + 1}</td>
      <td><strong>${esc(r.fullname)}</strong></td>
      <td style="font-family:monospace;font-size:0.82rem;">${esc(r.ic_number)}</td>
      <td style="font-size:0.85rem;">${esc(r.phone)}</td>
      <td style="font-size:0.82rem;color:var(--text-muted);">${esc(r.email) || '—'}</td>
      <td style="font-size:0.82rem;color:var(--text-muted);">${esc(r.organization) || '—'}</td>
      <td style="font-size:0.82rem;color:var(--text-muted);">${esc(r.folder_name) || '—'}</td>
      <td style="font-size:0.78rem;color:var(--text-muted);">${formattedDate}</td>
      <td>
        <div style="display:flex; gap:0.5rem; justify-content:center;">
          <button class="btn btn-sm" onclick="previewCertFor('${r.id}')" title="Papar Sijil" style="padding:0.4rem; background:transparent; border:none; color:#60a5fa;"><i data-lucide="award" style="stroke-width:2.5;"></i></button>
          <button class="btn btn-sm" onclick="openEditModal('${r.id}')" title="Kemaskini" style="padding:0.4rem; background:transparent; border:none; color:#fbbf24;"><i data-lucide="user-pen" style="stroke-width:2.5;"></i></button>
          <button class="btn btn-sm" onclick="deleteRecord('${r.id}')" title="Padam" style="padding:0.4rem; background:transparent; border:none; color:#f87171;"><i data-lucide="trash-2" style="stroke-width:2.5;"></i></button>
        </div>
      </td>
    </tr>
    `;
  }).join('');
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
        showToast('<i class="fa-solid fa-trash"></i>️ Rekod dipadam.', 'info');
      } catch (e) {
        showToast('<i class="fa-solid fa-circle-xmark"></i> Ralat memadam rekod.', 'error');
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
      showToast('<i class="fa-solid fa-circle-check"></i> Maklumat berjaya dikemaskini!', 'success');
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
  if (currentFolderId) url += `?folder=${currentFolderId}`;
  window.open(url, '_blank');
  showToast('<i class="fa-solid fa-download"></i> CSV dimuat turun!', 'success');
}

// ═══════════════════════════════════════
//  TABS
// ═══════════════════════════════════════

function switchTab(tab) {
  localStorage.setItem('active_admin_tab', tab); // Persist tab state across reloads
  ['attendance', 'certificate', 'settings', 'users'].forEach(t => {
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
  toast.innerHTML = msg;
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
      <span><i class="fa-solid fa-user"></i></span>
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
  const s = {
    nameX: p.name_x ?? 500, nameY: p.name_y ?? 360, nameFontSize: p.name_size ?? 42,
    icX: p.ic_x ?? 500, icY: p.ic_y ?? 470, icFontSize: p.ic_size ?? 28,
    showIC: p.show_ic ?? true, textColor: p.text_color ?? '#000000',
    fontFamily: p.font_family ?? 'Arial, sans-serif'
  };
  const tpl = p.cert_template || null;

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
    showToast('<i class="fa-solid fa-hourglass-half"></i> Memuatkan jsPDF...', 'info');
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
  if (!cachedRecords.length) { showToast('<i class="fa-solid fa-triangle-exclamation"></i>️ Tiada peserta.', 'error'); return; }
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
  document.querySelector('#prompt-modal-title span').innerHTML = options.title || 'Input';
  const inputEl = document.getElementById('prompt-modal-input');
  inputEl.value = options.defaultValue || '';
  inputEl.placeholder = options.placeholder || '';
  inputEl.readOnly = !!options.readOnly;
  
  const btn = document.getElementById('btn-prompt-action');
  btn.innerHTML = options.confirmText || 'OK';
  
  if (options.readOnly) {
    btn.innerHTML = 'Salin / Copy';
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
  document.getElementById('confirm-modal-title').innerHTML = options.title || 'Adakah anda pasti?';
  document.getElementById('confirm-modal-msg').innerHTML = options.message || '';
  document.getElementById('confirm-modal-sub').innerHTML = options.subMessage || '';
  
  const btn = document.getElementById('btn-confirm-action');
  btn.innerHTML = options.confirmText || 'Teruskan';
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
          showToast(`<i class="fa-solid fa-circle-check"></i> ${res.deleted} rekod berjaya dipadam!`, 'success');
          deselectAll();
          await refreshData();
        } else {
          showToast('<i class="fa-solid fa-circle-xmark"></i> Ralat memadam rekod.', 'error');
        }
      } catch (err) {
        console.error('Bulk delete error:', err);
        showToast('<i class="fa-solid fa-circle-xmark"></i> Ralat rangkaian.', 'error');
      }
    }
  });
}

async function bulkGeneratePDF(records, filename) {
  showToast(`<i class="fa-solid fa-hourglass-half"></i> Jana ${records.length} sijil...`, 'info');
  if (typeof window.jspdf === 'undefined') await loadScript('https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js');
  const s = getSettings(); 
  const tpl = currentFolderData ? currentFolderData.cert_template : null;
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
  showToast(`<i class="fa-solid fa-circle-check"></i> ${records.length} sijil berjaya dijana!`, 'success');
}

function loadScript(src) { return new Promise((res, rej) => { const s = document.createElement('script'); s.src = src; s.onload = res; s.onerror = rej; document.head.appendChild(s); }); }

// ═══════════════════════════════════════
//  SETTINGS (localStorage for UI prefs)
// ═══════════════════════════════════════

function getSettings() {
  if (currentFolderData) {
    return {
      nameX: currentFolderData.name_x ?? 500, nameY: currentFolderData.name_y ?? 360, nameFontSize: currentFolderData.name_size ?? 42,
      icX: currentFolderData.ic_x ?? 500, icY: currentFolderData.ic_y ?? 470, icFontSize: currentFolderData.ic_size ?? 28,
      showIC: currentFolderData.show_ic ?? true, textColor: currentFolderData.text_color ?? '#000000',
      fontFamily: currentFolderData.font_family ?? 'Arial, sans-serif',
      eventName: currentFolderData.event_name ?? '', eventDate: currentFolderData.event_date ?? '',
      organizer: currentFolderData.organizer ?? 'Perbadanan Labuan',
      certDelayHours: Math.floor((currentFolderData.cert_delay || 0) / 3600000), 
      certDelayMinutes: Math.round(((currentFolderData.cert_delay || 0) % 3600000) / 60000),
    };
  }
  
  // Fallback if no folder selected
  return {
    nameX: 500, nameY: 360, nameFontSize: 42,
    icX: 500, icY: 470, icFontSize: 28,
    showIC: true, textColor: '#000000',
    fontFamily: 'Arial, sans-serif',
    eventName: '', eventDate: '',
    organizer: 'Perbadanan Labuan',
    certDelayHours: 0, certDelayMinutes: 0,
  };
}

async function saveSettings() {
  const g = id => document.getElementById(id)?.value;
  const gn = id => parseInt(document.getElementById(id)?.value) || 0;
  const gc = id => document.getElementById(id)?.checked ?? false;
  
  if (!currentFolderId) {
    showToast('<i class="fa-solid fa-triangle-exclamation"></i>️ Sila pilih folder terlebih dahulu.', 'error');
    return;
  }
  
  const delayMs = (gn('cert-delay-hours') * 3600000) + (gn('cert-delay-minutes') * 60000);
  
  const payload = {
    name_x: gn('name-x'), name_y: gn('name-y'), name_size: gn('name-size'),
    ic_x: gn('ic-x'), ic_y: gn('ic-y'), ic_size: gn('ic-size'),
    show_ic: true, text_color: g('text-color') || '#000000',
    font_family: g('font-family') || 'Arial, sans-serif',
    event_name: g('event-name') || '', event_date: g('event-date-display') || '',
    organizer: g('event-organizer') || 'Perbadanan Labuan',
    cert_delay: delayMs
  };
  
  try {
    const res = await api(`folders/${currentFolderId}/`, { method: 'PATCH', body: payload });
    if (res.status === 'success') {
      showToast('<i class="fa-solid fa-circle-check"></i> Tetapan disimpan ke folder!', 'success');
      currentFolderData = { ...currentFolderData, ...payload };
      const cid = parseInt(currentFolderId);
      cachedRecords.forEach(r => {
        if (r.folder_id === cid) {
          Object.assign(r, payload);
        }
      });
      if (selectedParticipant) drawCertificate(selectedParticipant);
    }
  } catch(e) {
    showToast('<i class="fa-solid fa-circle-xmark"></i> Ralat menyimpan tetapan.', 'error');
  }
}

async function loadSettings() {
  const s = getSettings();
  const set = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
  const chk = (id, v) => { const el = document.getElementById(id); if (el) el.checked = v; };
  set('name-x', s.nameX); set('name-y', s.nameY); set('name-size', s.nameFontSize);
  set('ic-x', s.icX); set('ic-y', s.icY); set('ic-size', s.icFontSize);
  set('text-color', s.textColor); set('font-family', s.fontFamily);
  set('event-name', s.eventName); set('event-date-display', s.eventDate);
  set('event-organizer', s.organizer);
  set('cert-delay-hours', s.certDelayHours);
  set('cert-delay-minutes', s.certDelayMinutes);
  
  // Also load the template image specific to the folder
  if (currentFolderData && currentFolderData.cert_template) {
    const img = document.getElementById('template-preview-img'); 
    if (img) { img.src = currentFolderData.cert_template; img.style.display = 'block'; }
  } else {
    const img = document.getElementById('template-preview-img'); 
    if (img) img.style.display = 'none';
  }
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
      if (!currentFolderId) {
        showToast('<i class="fa-solid fa-triangle-exclamation"></i>️ Sila pilih folder dahulu sebelum muat naik templat.', 'error');
        return;
      }
      api(`folders/${currentFolderId}/`, { method: 'PATCH', body: { cert_template: data } }).then(() => {
        if (currentFolderData) currentFolderData.cert_template = data;
        cachedRecords.forEach(r => { if (r.folder_id === parseInt(currentFolderId)) r.cert_template = data; });
        const el = document.getElementById('template-preview-img');
        if (el) { el.src = data; el.style.display = 'block'; }
        showToast('<i class="fa-solid fa-circle-check"></i> Templat dimuat naik ke folder!', 'success');
        if (selectedParticipant) drawCertificate(selectedParticipant);
      }).catch(() => showToast('<i class="fa-solid fa-circle-xmark"></i> Gagal memuat naik.', 'error'));
    };
    img.src = ev.target.result;
  };
  reader.readAsDataURL(file);
}

function clearTemplate() {
  if (!currentFolderId) return;
  api(`folders/${currentFolderId}/`, { method: 'PATCH', body: { cert_template: null } }).then(() => {
    if (currentFolderData) currentFolderData.cert_template = null;
    cachedRecords.forEach(r => { if (r.folder_id === parseInt(currentFolderId)) r.cert_template = null; });
    const img = document.getElementById('template-preview-img'); if (img) img.style.display = 'none';
    document.getElementById('template-upload').value = '';
    showToast('<i class="fa-solid fa-trash"></i>️ Templat dipadam dari folder.', 'info');
    if (selectedParticipant) drawCertificate(selectedParticipant);
  });
}

function useDefaultTemplate() { clearTemplate(); }

// ═══════════════════════════════════════
//  INIT
// ═══════════════════════════════════════

window.addEventListener('DOMContentLoaded', async () => {
  // Check if session is already active
  try {
    const res = await api('auth/check/', { method: 'GET' });
    if (res && res.status === 'success') {
      currentUserRole.is_super = res.is_super;
      currentUserRole.department_id = res.department_id;
      showAdmin();
    }
  } catch (e) {
    // Not logged in or session expired, stay on login screen
    localStorage.removeItem('pl_csrf');
    document.getElementById('login-overlay').style.display = 'flex';
  }

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
  // cert_template initialization is now handled in loadSettings() when a folder is selected
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

// ═══════════════════════════════════════
//  USER MANAGEMENT (SUPER ADMIN ONLY)
// ═══════════════════════════════════════

async function loadUsers() {
  if (!currentUserRole.is_super) return;
  try {
    const res = await api('users/', { method: 'GET' });
    const tbody = document.getElementById('users-tbody');
    if (res && res.status === 'success') {
      tbody.innerHTML = '';
      res.data.forEach(u => {
        const role = u.is_super ? '<span style="color:var(--accent);">Super Admin</span>' : 'Admin Jabatan';
        const dept = u.department_name || '—';
        const deleteBtn = u.username !== 'admin' ? 
          `<button class="btn btn-danger btn-sm" onclick="deleteUser(${u.id}, '${u.username}')"><i data-lucide="trash-2"></i></button>` : 
          '';
          
        tbody.innerHTML += `
          <tr>
            <td><strong>${u.username}</strong></td>
            <td>${role}</td>
            <td>${dept}</td>
            <td>${deleteBtn}</td>
          </tr>
        `;
      });
      if (window.lucide) lucide.createIcons();
    }
  } catch (e) {
    console.error('Failed to load users', e);
  }
}

function deleteUser(id, username) {
  openConfirmModal({
    title: 'Padam Pengguna',
    message: `Anda pasti ingin memadam pengguna "${username}"?`,
    confirmText: 'Padam',
    confirmClass: 'btn-danger',
    icon: 'trash-2',
    onConfirm: async () => {
      try {
        const res = await api(`users/${id}/`, { method: 'DELETE' });
        if (res && res.status === 'success') {
          showToast('<i class="fa-solid fa-check"></i> Pengguna dipadam.', 'success');
          loadUsers();
        } else {
          showToast('<i class="fa-solid fa-xmark"></i> Ralat memadam pengguna: ' + res.message, 'error');
        }
      } catch (e) {
        showToast('<i class="fa-solid fa-xmark"></i> Ralat rangkaian.', 'error');
      }
    }
  });
}

function openAddUserModal() {
  document.getElementById('new-user-username').value = '';
  document.getElementById('new-user-password').value = '';
  document.getElementById('new-user-role').value = 'false';
  
  // Populate departments
  const deptSelect = document.getElementById('new-user-dept');
  deptSelect.innerHTML = '<option value="">-- Pilih Jabatan --</option>';
  departmentsData.forEach(d => {
    deptSelect.innerHTML += `<option value="${d.id}">${d.name}</option>`;
  });
  
  toggleDeptSelect();
  document.getElementById('add-user-modal').style.display = 'flex';
}

function closeAddUserModal() {
  document.getElementById('add-user-modal').style.display = 'none';
}

function toggleDeptSelect() {
  const isSuper = document.getElementById('new-user-role').value === 'true';
  const deptGroup = document.getElementById('new-user-dept-group');
  if (isSuper) {
    deptGroup.style.display = 'none';
    document.getElementById('new-user-dept').required = false;
  } else {
    deptGroup.style.display = 'block';
    document.getElementById('new-user-dept').required = true;
  }
}

async function submitAddUser() {
  const username = document.getElementById('new-user-username').value;
  const password = document.getElementById('new-user-password').value;
  const is_super = document.getElementById('new-user-role').value;
  const department_id = document.getElementById('new-user-dept').value;
  
  try {
    const res = await api('users/', {
      method: 'POST',
      body: { username, password, is_super, department_id }
    });
    
    if (res && res.status === 'success') {
      showToast('<i class="fa-solid fa-check"></i> Pengguna ditambah.', 'success');
      closeAddUserModal();
      loadUsers();
    } else {
      showToast('<i class="fa-solid fa-xmark"></i> Ralat: ' + res.message, 'error');
    }
  } catch (e) {
    showToast('<i class="fa-solid fa-xmark"></i> Ralat rangkaian.', 'error');
  }
}
