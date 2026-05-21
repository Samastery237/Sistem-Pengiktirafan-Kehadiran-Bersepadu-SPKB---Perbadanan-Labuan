# Sistem Pengiktirafan Kehadiran Bersepadu (SPKB)
### Perbadanan Labuan

Platform digital inovatif Perbadanan Labuan yang menyelaraskan pengurusan kehadiran acara, latihan, dan program rasmi secara automatik. Sistem ini mengintegrasikan pemantauan masa nyata dengan penjanaan sijil digital (e-Sijil) bagi memperkasa tadbir urus modal insan yang lebih efisien, telus, dan tanpa kertas.

## Ciri-Ciri Utama / Key Features

- **Perekodan Kehadiran** — Borang digital pantas untuk pendaftaran kehadiran peserta.
- **Penjanaan Sijil Automatik** — e-Sijil dijana secara automatik selepas program tamat, dengan kawalan masa (countdown timer) yang boleh dikonfigurasikan oleh pentadbir.
- **Panel Pentadbiran** — Paparan dashboard untuk mengurus peserta, melihat statistik, dan menjana sijil secara pukal.
- **Pengurusan Program** — Pelbagai program boleh diurus secara berasingan, setiap satu dengan tetapan masa sijilnya sendiri.
- **Eksport CSV** — Muat turun senarai kehadiran dalam format CSV.

## Teknologi / Tech Stack

| Layer    | Technology                |
|----------|--------------------------|
| Backend  | Django + Django REST Framework |
| Database | SQLite (Development)     |
| Frontend | HTML, CSS, Vanilla JS    |
| PDF      | xhtml2pdf                |

## Cara Menjalankan / How to Run

```bash
# 1. Aktifkan virtual environment
cd backend
..\venv\Scripts\activate    # Windows

# 2. Jalankan migrasi
python manage.py migrate

# 3. Mulakan server
python manage.py runserver
```

Buka **http://127.0.0.1:8000/** di pelayar web.

## API Endpoints

| Method   | Endpoint                             | Fungsi                    |
|----------|--------------------------------------|---------------------------|
| `POST`   | `/api/attendance/submit/`            | Hantar kehadiran          |
| `GET`    | `/api/attendance/records/`           | Senarai rekod             |
| `DELETE` | `/api/attendance/records/<id>/`      | Padam rekod               |
| `GET`    | `/api/attendance/participant/<ic>/`  | Semak peserta (IC)        |
| `GET`    | `/api/attendance/stats/`             | Statistik kehadiran       |
| `GET`    | `/api/attendance/programs/`          | Senarai program           |
| `POST`   | `/api/attendance/programs/`          | Cipta program baharu      |
| `PATCH`  | `/api/attendance/programs/<id>/`     | Kemas kini tetapan        |
| `GET`    | `/api/attendance/export/`            | Muat turun CSV            |
| `GET`    | `/api/attendance/download-certificate/<id>/` | Muat turun sijil PDF |

## Admin Panel

Buka `admin.html` atau klik "Panel Admin" di footer laman utama.

- **Username:** `Administrator`
- **Password:** `admin123` (boleh ditukar dalam tetapan)

---

© 2026 Perbadanan Labuan
