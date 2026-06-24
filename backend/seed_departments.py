import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from attendance.models import Department

DEPARTMENTS = [
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
    "Agensi Kerajaan Lain",
    "Sektor Swasta / NGO",
    "Orang Awam",
    "Lain-Lain"
]

def seed():
    print("Seeding departments...")
    created_count = 0
    for dept_name in DEPARTMENTS:
        obj, created = Department.objects.get_or_create(name=dept_name)
        if created:
            created_count += 1
            print(f"Created: {dept_name}")
        else:
            print(f"Already exists: {dept_name}")
            
    print(f"\nDone! Successfully created {created_count} new departments.")
    print(f"Total departments in database: {Department.objects.count()}")

if __name__ == '__main__':
    seed()
