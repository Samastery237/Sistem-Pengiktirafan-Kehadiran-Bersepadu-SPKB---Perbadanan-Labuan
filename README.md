<div align="center">
  
# Sistem Pengiktirafan Kehadiran Bersepadu (SPKB)
### Perbadanan Labuan

[![Python Compliance](https://img.shields.io/badge/Python-3.14+-blue.svg)](https://www.python.org)
[![Framework](https://img.shields.io/badge/Django-6.0+-092E20.svg)](https://www.djangoproject.com/)
[![Deployment](https://img.shields.io/badge/Docker-Enterprise_Ready-2496ED.svg)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-Proprietary-red.svg)](#)
[![Build Status](https://img.shields.io/badge/Build-Passing-brightgreen.svg)]()

*Enterprise-Grade Digital Attendance and Automated e-Certificate Issuance Platform*

</div>

---

## 1. Executive Summary

**Sistem Pengiktirafan Kehadiran Bersepadu (SPKB)** is a proprietary, enterprise-grade digital platform engineered for **Perbadanan Labuan**. The system modernizes the administration of official government events, corporate training, and mandatory operational programs by providing a secure, paperless attendance tracking infrastructure coupled with automated digital certificate (e-Sijil) provisioning.

Designed to meet strict data governance policies, SPKB eliminates manual documentation overhead while ensuring data integrity, providing real-time auditing capabilities, and enforcing strict Role-Based Access Control (RBAC) across departmental divisions.

## 2. Core Capabilities & Architecture

SPKB is architected for high availability, security, and precision.

- **Automated Digital Issuance**: Cryptographically secure, dynamic generation of PDF certificates utilizing PyHanko and SVGLib upon verified attendance submission.
- **Role-Based Access Control (RBAC)**: Multi-tiered administrative authorization architecture.
  - *Super Administrators*: Full oversight, cross-departmental configuration, and global analytics.
  - *Department Administrators*: Isolated authority restricted exclusively to intra-departmental events.
- **Real-Time Data Analytics**: Administrative dashboards featuring live participant metrics, robust CSV data exportation, and bulk processing capabilities for compliance reporting.
- **Security & Compliance**: Hardened API endpoints, enforced CSRF protection, secure HTTP-only session management, and comprehensive automated test validation.
- **Containerized Infrastructure**: Fully packaged within Docker for scalable, highly-available deployment across hybrid-cloud or on-premise government servers.

---

## 3. Deployment & Infrastructure Setup

This system supports containerized deployment for production environments and isolated local configurations for active development.

### 3.1. Production Deployment (Docker) - *Standard*
The mandated method for staging and production server environments to ensure parity and eliminate dependency conflicts.

```bash
# 1. Clone the repository to the designated deployment directory
git clone https://github.com/yourusername/Sistem-Pengiktirafan-Kehadiran-Bersepadu-SPKB---Perbadanan-Labuan.git
cd Sistem-Pengiktirafan-Kehadiran-Bersepadu-SPKB---Perbadanan-Labuan

# 2. Provision and initiate the isolated container infrastructure
docker compose up -d --build
```

**Service Interfaces:**
- Public Intake Portal: `http://<server-ip>:8000/`
- Secure Administrative Console: `http://<server-ip>:8000/admin.html`

### 3.2. Local Development & Engineering
For authorized software engineers executing structural modifications or running integration tests.

```bash
# 1. Initialize the Python virtual environment
cd backend
python -m venv venv_win
venv_win\Scripts\activate

# 2. Install required system dependencies
pip install -r ../requirements.txt

# 3. Execute database schema migrations
python manage.py migrate

# 4. Boot the localized development server
python manage.py runserver
```

---

## 4. Quality Assurance & Testing

To maintain software integrity, all code modifications must pass the centralized automated testing suites before deployment approval.

```bash
# Execute Backend Security, API, and RBAC Validation (Pytest)
pytest backend/attendance/tests.py

# Execute Frontend UI and End-to-End Workflow Validation (Playwright)
npx playwright test
```
*Note: A 100% pass rate is mandatory for code integration into the main branch.*

---

## 5. Support & Technical Documentation

For operational support, architectural documentation, or incident reporting:

- **Incident Management**: Submit bug reports and feature proposals via the [Issue Tracker](https://github.com/yourusername/Sistem-Pengiktirafan-Kehadiran-Bersepadu-SPKB---Perbadanan-Labuan/issues).
- **Technical Documentation**: Comprehensive API specifications and system architectures are maintained in the central IT documentation repository.
- **Escalation**: For critical system failures or deployment authorizations, contact the **Perbadanan Labuan Central IT Division**.

---

## 6. Governance & Contributions

This software is maintained by the **Perbadanan Labuan IT Engineering Team** (Lead: Samastery237). 

**Standard Operating Procedure for Contributions:**
1. Fork the repository to your secure workspace.
2. Checkout a designated feature branch utilizing standard nomenclature (`git checkout -b feature/PL-102-description`).
3. Ensure absolute compliance with the Pytest and Playwright automated testing suites.
4. Submit a formalized Pull Request detailing architectural changes, security implications, and testing validation.

---
<div align="center">
  <small><b>Hak Cipta Terpelihara © 2026 Perbadanan Labuan</b><br>
  Proprietary and Confidential. Unauthorized distribution or modification is strictly prohibited.</small>
</div>
