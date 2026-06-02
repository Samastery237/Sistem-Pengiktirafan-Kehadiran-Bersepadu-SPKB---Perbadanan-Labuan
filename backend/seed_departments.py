import os
import sys
import django

# Setup Django environment
sys.path.append(r"c:\Users\Samuel\Downloads\Sistem-Pengiktirafan-Kehadiran-Bersepadu-SPKB---Perbadanan-Labuan\backend")
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from attendance.models import Department

departments = [
    "Pejabat Pengerusi",
    "Pejabat Ketua Pegawai Eksekutif",
    "Pejabat Timbalan Ketua Pegawai Eksekutif",
    "Pejabat Penasihat Undang-Undang",
    "Jabatan Audit Dalam",
    "Jabatan Hal Ehwal Korporat",
    "Unit Dasar dan Integriti",
    "Jabatan Khidmat Pengurusan",
    "Pusat Transformasi Bandar (UTC)",
    "Jabatan Pengurusan Sumber Manusia",
    "Unit Perkhidmatan JPSM",
    "Unit Latihan JPSM",
    "Jabatan Kewangan",
    "Jabatan Digital Dan Informasi",
    "Perpustakaan Awam Labuan",
    "Jabatan Pembangunan & Kejuruteraan",
    "Jabatan Perancangan & Kawalan Bangunan",
    "Jabatan Sosio Ekonomi",
    "Jabatan Pelancongan, Kebudayaan, dan Kesenian",
    "Majlis Sukan Labuan",
    "Unit Penyelarasan, Pemantauan dan Penilaian Impak",
    "Jabatan Penilaian dan pengurusan Harta",
    "Jabatan Perkhidmatan Perbandaran",
    "Jabatan Penguatkuasaan",
    "Jabatan Pelesenan",
    "Unit Pelaburan PL",
    "Lain-Lain"
]

for name in departments:
    dept, created = Department.objects.get_or_create(name=name)
    if created:
        print(f"Created department: {name}")
    else:
        print(f"Department already exists: {name}")

print("Seeding complete.")
