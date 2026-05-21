/* form.js — Attendance Form Logic (Django Backend) */

// ─── Configuration ───
const API_BASE = 'http://127.0.0.1:8000/api/attendance/';

// Get program from URL parameter (e.g., ?program=Integrity%202026)
const urlParams = new URLSearchParams(window.location.search);
const urlProgram = urlParams.get('program');
const PROGRAM_NAME = decodeURIComponent(urlProgram) || 'Perbadanan Labuan';

// ─── Bilingual Labels ───
const LANG = {
  bm: {
    formTitle: 'Borang Kehadiran',
    formSubtitle: 'Sila isi maklumat anda dengan tepat dan lengkap.',
    infoNote: 'Maklumat anda akan digunakan untuk penjanaan sijil penyertaan secara automatik.',
    labelName: 'Nama Penuh',
    submitText: '✅ Hantar Kehadiran / Submit Attendance',
    errName: 'Sila masukkan nama penuh anda.',
    errIC: 'Sila masukkan nombor kad pengenalan yang sah (12 digit).',
    errPhone: 'Sila masukkan nombor telefon yang sah.',
    errEmail: 'Sila masukkan alamat e-mel yang sah.',
    errOrg: 'Sila pilih Jabatan/Jawatan anda.',
    errTerms: 'Sila tandakan kotak persetujuan untuk meneruskan.',
  },
  en: {
    formTitle: 'Attendance Form',
    formSubtitle: 'Please fill in your information accurately and completely.',
    infoNote: 'Your information will be used for automatic certificate generation.',
    labelName: 'Full Name',
    submitText: '✅ Submit Attendance / Hantar Kehadiran',
    errName: 'Please enter your full name.',
    errIC: 'Please enter a valid IC number (12 digits).',
    errPhone: 'Please enter a valid phone number.',
    errEmail: 'Please enter a valid email address.',
    errOrg: 'Please select your Department/Position.',
    errTerms: 'Please check the consent box to continue.',
  }
};

let currentLang = 'bm';

// ─── Language Toggle ───
function setLang(lang) {
  currentLang = lang;
  const t = LANG[lang];
  document.getElementById('form-title').textContent = t.formTitle;
  document.getElementById('form-subtitle').textContent = t.formSubtitle;
  document.getElementById('info-note-text').textContent = t.infoNote;
  document.getElementById('submit-text').textContent = t.submitText;
  document.getElementById('lang-bm').classList.toggle('active', lang === 'bm');
  document.getElementById('lang-en').classList.toggle('active', lang === 'en');
}

// ─── Progress Bar ───
function updateProgress() {
  const fields = ['fullname', 'ic', 'phone', 'email', 'organization'];
  let filled = 0;
  fields.forEach(id => { if (document.getElementById(id)?.value.trim()) filled++; });
  document.getElementById('progress-bar').style.width = Math.round((filled / fields.length) * 100) + '%';
}

// ─── Input Formatters ───
function formatIC(value) {
  const digits = value.replace(/\D/g, '').slice(0, 12);
  if (digits.length <= 6) return digits;
  if (digits.length <= 8) return `${digits.slice(0, 6)}-${digits.slice(6)}`;
  return `${digits.slice(0, 6)}-${digits.slice(6, 8)}-${digits.slice(8)}`;
}

function formatPhone(value) {
  return value.replace(/[^0-9+\-\s]/g, '').slice(0, 15);
}

// ─── Validators ───
function validateIC(value) { return value.replace(/\D/g, '').length === 12; }
function validatePhone(value) { const d = value.replace(/\D/g, ''); return d.length >= 9 && d.length <= 12; }
function validateEmail(value) { return !value || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value); }

function setError(fieldId, errorId, message) {
  const input = document.getElementById(fieldId);
  const error = document.getElementById(errorId);
  if (message) {
    input?.classList.add('error');
    if (error) { error.textContent = message; error.classList.add('show'); }
    return false;
  }
  input?.classList.remove('error');
  if (error) error.classList.remove('show');
  return true;
}

// ─── Toast ───
function showToast(msg, type = 'info') {
  let toast = document.getElementById('toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'toast';
    toast.setAttribute('role', 'alert');
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.className = `toast toast-${type} show`;
  setTimeout(() => toast.classList.remove('show'), 3500);
}

// ─── Reference Generator ───
function generateRef() {
  const now = new Date();
  const pad = n => String(n).padStart(2, '0');
  const d = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}`;
  const rand = Math.random().toString(36).substr(2, 5).toUpperCase();
  return `PL-${d}-${rand}`;
}

// ─── Form Submission ───
async function handleSubmit(e) {
  e.preventDefault();
  const t = LANG[currentLang];

  const fullname = document.getElementById('fullname').value.trim();
  const ic = document.getElementById('ic').value.trim();
  const phone = document.getElementById('phone').value.trim();
  const email = document.getElementById('email').value.trim();
  const organization = document.getElementById('organization').value.trim();
  const terms = document.getElementById('terms').checked;

  // Validate
  let valid = true;
  valid = setError('fullname', 'error-fullname', !fullname ? t.errName : '') && valid;
  valid = setError('ic', 'error-ic', !validateIC(ic) ? t.errIC : '') && valid;
  valid = setError('phone', 'error-phone', !validatePhone(phone) ? t.errPhone : '') && valid;
  valid = setError('email', 'error-email', !validateEmail(email) ? t.errEmail : '') && valid;
  valid = setError('organization', 'error-organization', !organization ? t.errOrg : '') && valid;

  const termsErr = document.getElementById('error-terms');
  if (!terms) {
    termsErr.textContent = t.errTerms;
    termsErr.classList.add('show');
    valid = false;
  } else {
    termsErr.classList.remove('show');
  }

  if (!valid) { showToast('⚠️ Sila semak semua medan.', 'error'); return; }

  // Show loading
  const btn = document.getElementById('submit-btn');
  const spinner = document.getElementById('submit-spinner');
  const submitText = document.getElementById('submit-text');
  btn.disabled = true;
  submitText.style.display = 'none';
  spinner.style.display = 'block';

  const ref = generateRef();
  const now = new Date();
  const timestamp = now.toLocaleString('ms-MY', {
    day: '2-digit', month: 'long', year: 'numeric',
    hour: '2-digit', minute: '2-digit', hour12: true,
  });

  // Build payload for Django API (cert_delay is set server-side from Program settings)
  const payload = {
    ref,
    fullname,
    ic_number: formatIC(ic),
    phone,
    email: email || '',
    organization: organization || '',
    program_name: PROGRAM_NAME,
  };

  try {
    const response = await fetch(API_BASE + 'submit/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    const result = await response.json();

    if (response.ok && result.status === 'success') {
      // Store submission summary for the success page
      sessionStorage.setItem('lastSubmission', JSON.stringify({
        ref,
        fullname,
        ic: formatIC(ic),
        phone,
        email: email || '—',
        organization: organization || '—',
        timestamp,
        record_id: result.record_id,
      }));
      window.location.href = 'success.html';
    } else {
      throw new Error(result.message || 'Submission failed');
    }
  } catch (err) {
    console.error('Submission error:', err);
    showToast('❌ Ralat semasa menghantar. Sila cuba lagi.', 'error');
    btn.disabled = false;
    submitText.style.display = 'inline';
    spinner.style.display = 'none';
  }
}

// ─── Init ───
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('attendance-form').addEventListener('submit', handleSubmit);

  // Auto-select program from URL if provided
  const programSelect = document.getElementById('organization');
  if (programSelect && urlProgram) {
    // Find and select the matching option
    Array.from(programSelect.options).forEach(option => {
      if (option.value === decodeURIComponent(urlProgram)) {
        option.selected = true;
      }
    });
    // Update progress bar after selection
    updateProgress();
  }

  document.getElementById('ic').addEventListener('input', function () {
    this.value = formatIC(this.value);
    updateProgress();
  });

  document.getElementById('phone').addEventListener('input', function () {
    this.value = formatPhone(this.value);
    updateProgress();
  });

  document.getElementById('fullname').addEventListener('input', function () {
    document.getElementById('name-count').textContent = this.value.length;
    updateProgress();
  });

  ['email', 'organization'].forEach(id => {
    document.getElementById(id)?.addEventListener('input', updateProgress);
  });

  ['fullname', 'ic', 'phone', 'email'].forEach(id => {
    document.getElementById(id)?.addEventListener('input', () => {
      document.getElementById(id)?.classList.remove('error');
      document.getElementById(`error-${id}`)?.classList.remove('show');
    });
  });
});