# DEPARTMENT-SPECIFIC LINK SYSTEM FOR SPKB

## Overview
You can now create and share direct links that automatically enroll participants in specific department programs without requiring manual program selection. This is perfect for QR codes, email invitations, department websites, and printed materials.

## How It Works

### 1. **Create Your Department Program**
In the admin panel (`http://localhost:8000/admin.html`):
- Login as Administrator/admin123
- Go to any tab (attendance, certificate, or settings)
- Click "➕ Tambah Program" button in the toolbar
- Enter your department program name (e.g., "Integrity 2026", "Audit Lerma 2026", "Finance Training 2026")
- Click Save

### 2. **Configure Program Settings** (Optional but Recommended)
While viewing your newly created program:
- Go to Settings tab (⚙️ Tetapan)
- Configure certificate delay (hours/minutes for automatic certificate generation)
- Upload/customize certificate template if desired
- Set text positioning for names and IC numbers
- Configure event info (program name, date, organizer)
- Save all settings

### 3. **Create and Share Department Link**
The link format is:
```
http://localhost:8000/form.html?program=[URL-ENCODED-PROGRAM-NAME]
```

**Examples:**
- Integrity 2026: `http://localhost:8000/form.html?program=Integrity%202026`
- Audit Lerma 2026: `http://localhost:8000/form.html?program=Audit%20Lerma%202026`
- Finance Training: `http://localhost:8000/form.html?program=Finance%20Training%202026`
- IT Security Workshop: `http://localhost:8000/form.html?program=IT%20Security%20Workshop`

### 4. **Share the Link with Participants**
Distribute via:
- Email invitations
- QR codes on posters/flyers
- Department website or intranet
- WhatsApp/Telegram groups
- Printed materials with QR codes

### 5. **What Happens When Participants Use the Link**
When a participant opens your department link:
1. **Form auto-loads** with your program pre-selected in the organization dropdown
2. **All required fields** still need to be filled (name, IC, phone, etc.)
3. **Upon submission**, their attendance is automatically recorded under your department's program
4. **Certificate generation** uses your program's specific settings (delay, template, etc.)
5. **Data isolation** ensures their record only appears in your department's folder/view

## Benefits for Department Usage

### ✅ **Zero User Error**
- Participants cannot accidentally select the wrong program
- Eliminates confusion from dropdown selections
- Perfect for users unfamiliar with the system

### ✅ **Professional Experience**
- Clean, focused form without unnecessary choices
- Department branding through pre-context
- Streamlined registration process

### ✅ **Perfect Data Integrity**
- 100% guarantee submissions go to correct program folder
- No need for post-submission data correction
- Automatic synchronization with admin panel views

### ✅ **Marketing & Tracking Ready**
- Unique links per department/campaign
- Track link usage through program record counts
- Create different links for same program (different sessions)
- QR code analytics for physical materials

## Advanced Usage Examples

### Example 1: Multiple Sessions for Same Program
Same program, different dates/locations:
- Integrity 2026 - Session 1: `http://localhost:8000/form.html?program=Integrity%202026%20-%20Session%201`
- Integrity 2026 - Session 2: `http://localhost:8000/form.html?program=Integrity%202026%20-%20Session%202`

### Example 2: Different Certificate Templates per Department
Each department can have:
- Different certificate delay settings
- Different certificate templates (uploaded in Settings)
- Different text positioning/styles
- Different event info display

### Example 3: Department-Specific Workflows
- **Integrity Unit**: Uses links for integrity training workshops
- **Finance Department**: Uses links for quarterly compliance training  
- **HR Department**: Uses links for onboarding sessions
- **IT Department**: Uses links for security certification courses

## Verification Steps

To confirm your department link works correctly:

1. **Create link**: `http://localhost:8000/form.html?program=Your%20Dept%20Name`
2. **Open link in private/incognito window** (to avoid cached selections)
3. **Verify**: Your department name should be pre-selected in the organization dropdown
4. **Submit test record** with dummy data
5. **Check admin panel**: 
   - Select your department from dropdown → See the test record
   - Select other departments → Should NOT see your test record
   - Select "Semua Program" → Should see all records including yours

## Troubleshooting

### Link Not Working?
- Ensure program name in URL exactly matches program name in admin panel (case-sensitive)
- URL must be properly encoded (spaces as `%20`, special characters encoded)
- Verify Django server is running on port 8000
- Test the API directly: `http://localhost:8000/api/attendance/programs/`

### Participants Seeing Wrong Program?
- Check that URL parameter matches exactly what's in the organization dropdown
- Remember: The form uses the "organization" dropdown for program selection (this is by design in your SPKB system)
- Verify no cached selections by testing in private/incognito browser window

## Template for Department Communication

**Email/WhatsApp Template:**
```
Assalamualaikum dan Salam Sejahteria,

Anda dijemput untuk attended program [NAMA PROGRAM] yang diorganisir oleh [JABATAN/UNIT].

Sila daftar kehadiran menerusi pautan di bawah:
[URL PAUTAN DISINI]

Tarikh: [TARIKH PROGRAM]
Waktu: [WAKTU]
Tempat: [TEMPAT]

Sila pastikan anda daftar kehadiran sebelum memasuki venue.
Terima kasih.

[JABATAN/UNIT NAME]
[TAJUK]
[nombor telefon/email]
```

**QR Code Instructions:**
1. Generate QR code using any free online QR generator
2. Input your department link: `http://localhost:8000/form.html?program=[YOUR-PROGRAM]`
3. Download QR code and place on posters, flyers, tables, etc.
4. Test QR code with phone camera before printing large quantities

## Security Notes

- Links do not contain sensitive information - only program identification
- All form validations and protections still apply (IC format, required fields, etc.)
- Certificate generation still follows program-specific delays and settings
- Admin panel access remains protected by Administrator/admin123 login
- No way to access other departments' data through these links

---

**Ready to Use:** Your SPKB system now supports professional department-specific registration links out of the box! Simply create your program, configure its settings, generate the link, and share it with your participants.