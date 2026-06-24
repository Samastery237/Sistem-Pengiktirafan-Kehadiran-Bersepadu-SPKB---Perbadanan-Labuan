<div align="center">
  <img src="https://upload.wikimedia.org/wikipedia/commons/e/e0/Coat_of_arms_of_Labuan.svg" alt="Perbadanan Labuan Logo" width="120" />
  <h1>Sistem Pengiktirafan Kehadiran Bersepadu (SPKB)</h1>
  <p><strong>Enterprise Digital Attendance & Automated e-Certificate Platform</strong></p>

  <p>
    <img src="https://img.shields.io/badge/Backend-Django_6.0.5-092E20?style=flat-square&logo=django" alt="Django" />
    <img src="https://img.shields.io/badge/Frontend-Vanilla_JS-F7DF1E?style=flat-square&logo=javascript&logoColor=black" alt="JavaScript" />
    <img src="https://img.shields.io/badge/Database-SQLite-003B57?style=flat-square&logo=sqlite" alt="Database" />
    <img src="https://img.shields.io/badge/Security-Enterprise-blue?style=flat-square&logo=security" alt="Security" />
    <img src="https://img.shields.io/badge/Deployment-Docker-2496ED?style=flat-square&logo=docker" alt="Docker" />
    <img src="https://img.shields.io/badge/License-Proprietary-red?style=flat-square" alt="License" />
  </p>
  <p>
    <a href="#what-the-project-does">Overview</a> •
    <a href="#why-the-project-is-useful">Core Features</a> •
    <a href="#system-workflow">How It Works</a> •
    <a href="#how-to-get-started">Installation</a> •
    <a href="#maintainers-and-contributing">Contributing</a>
  </p>
</div>

---

## 📖 What the Project Does

**Sistem Pengiktirafan Kehadiran Bersepadu (SPKB)** is a complete, end-to-end web platform developed for **Perbadanan Labuan**. It modernizes the entire lifecycle of government programs, training sessions, and corporate events.

Instead of relying on paper sign-in sheets and manually printing certificates, SPKB digitizes the entire workflow. The system features a powerful **Admin Dashboard** for organizing events and tracking attendees, paired with a beautiful, responsive **Public Portal** where participants can mark their attendance (via digital links/QR codes) and securely download their digitally signed e-Certificates.

The project is a full-stack solution encompassing a highly secure Django backend and a blazing-fast, lightweight Vanilla JavaScript/HTML5 frontend.

---

## ✨ Why the Project is Useful (Core Features)

SPKB is built to handle the full scope of event management across multiple government departments.

### 🎨 The Frontend Ecosystem
- **Responsive Public Portal:** A mobile-first landing page designed for attendees to easily verify their attendance or retrieve their certificates from any device.
- **Dynamic Admin Dashboard:** A comprehensive management interface built with Vanilla JavaScript, featuring dynamic data tables, real-time search, and intuitive modals for creating and managing events.
- **Client-Side Certificate Previews:** Administrators can design and preview certificates dynamically in the browser using HTML5 Canvas before finalizing the designs.
- **No Heavy Frameworks:** Built entirely without React/Angular to ensure lightning-fast load times, exceptional SEO, and minimal dependency overhead.

### ⚙️ The Backend Engine
- **Robust REST API:** Powered by Django REST Framework, handling thousands of concurrent requests efficiently.
- **Automated e-Certificates:** A secure backend PDF rendering engine (`xhtml2pdf`) that generates pixel-perfect, tamper-proof certificates on demand.
- **Department-Level Data Isolation (RBAC):** Admin users are strictly bound to specific departments (e.g., HR, Finance). The backend rigidly isolates data so departments cannot view or modify each other's attendance records.

### 🛡️ Enterprise Security
- **Identity Verification Gates:** Public certificate retrieval requires participants to verify their identity (e.g., matching the last 4 digits of their IC Number).
- **Advanced Cryptography:** Passwords are hashed using the memory-hard **Argon2** algorithm.
- **Anti-Abuse Protections:** Built-in rate limiting (e.g., 5 logins/min), automated account lockouts after 5 failed attempts, and robust CSRF token rotation.
- **100% IDOR Prevention:** Absolute prevention of Insecure Direct Object Reference vulnerabilities across all endpoints.

---

## 🔄 System Workflow (How It Works)

1. **Event Creation:** A Department Administrator logs into the Admin Console and creates a new "Program Folder" (e.g., *Cybersecurity Workshop 2026*).
2. **Attendance Tracking:** The system generates a unique attendance link. Participants click the link (or scan a QR code at the physical venue) and submit their Name and IC Number.
3. **Admin Verification:** The Administrator monitors the real-time attendance table on the dashboard and closes the attendance window when the event concludes.
4. **Certificate Generation:** The Administrator clicks "Generate Certificates". The backend processes the attendee list and generates individualized PDFs.
5. **Participant Retrieval:** Participants visit the Public Portal, search for their IC Number, verify their identity, and download their official e-Certificate.

---

## 🚀 How to Get Started

### Prerequisites
- **Docker** and **Docker Compose** *(Recommended for Production)*
- **Python 3.12+** *(For local backend development)*
- **Node.js** *(Optional, for frontend tooling/tests)*

### Installation (Docker - Production Ready)

```bash
# 1. Clone the repository
git clone https://github.com/your-org/SPKB.git
cd SPKB

# 2. Configure environment variables
cp backend/.env.example backend/.env
# NOTE: Update backend/.env with your production secrets (SMTP, Secret Key)

# 3. Build and start the containers
docker compose up -d --build

# 4. Initialize the database and create the master administrator
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

### Installation (Local Full-Stack Development)

```bash
# Terminal 1: Backend Setup
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver

# Terminal 2: Frontend (Live Server)
# Use a local server like VSCode Live Server or Python's http.server 
# to serve the root directory containing index.html and admin.html
python -m http.server 3000
```

### Accessing the Platforms
- **Public Portal:** `http://localhost:8000/` (or `http://localhost:3000/` if running locally via HTTP server)
- **Admin Dashboard:** `http://localhost:8000/admin.html`

---

## 🆘 Where to Get Help

- **Codebase Navigation:**
  - `frontend/`: Contains all HTML, CSS, and Vanilla JS logic for both the portal and dashboard.
  - `backend/attendance/`: Contains the Django API views, models, and PDF generation logic.
- **Issue Tracker:** File bugs or feature requests via the GitHub issues page. Please include replication steps and whether the issue is frontend-UI or backend-API related.
- **Internal IT Operations:** For deployment, SSL, or domain routing queries, contact the Perbadanan Labuan Infrastructure team.

---

## 🤝 Maintainers and Contributing

**Primary Maintainer:** Perbadanan Labuan IT Department

We welcome full-stack contributions! To ensure system stability across both the frontend and backend, please follow our workflow:

1. **Fork and Branch:** Create a descriptive feature branch (`git checkout -b feature/new-dashboard-chart`).
2. **Full-Stack Standards:** 
   - Backend: Adhere to PEP-8 standards.
   - Frontend: Use modern ES6+ Vanilla JavaScript. Do not introduce heavy frontend frameworks.
3. **Backend Testing [CRITICAL]:** We strictly maintain **100% backend test coverage**. Run the test suite before submitting any API changes.
   ```bash
   cd backend
   python manage.py test -v 2
   ```
4. **Pull Request:** Open a PR against the `main` branch with a clear description of the UI/UX changes or API modifications.

---

<div align="center">
  <p>Hak Cipta Terpelihara © 2026 <strong>Perbadanan Labuan</strong></p>
  <p><i>Proprietary and Confidential</i></p>
</div>
