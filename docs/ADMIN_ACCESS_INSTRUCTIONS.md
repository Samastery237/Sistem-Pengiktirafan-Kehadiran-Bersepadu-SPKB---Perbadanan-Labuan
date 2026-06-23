# SPKB Admin Panel Access Instructions

## Problem Summary
The custom admin panel (`admin.html`) was unable to display information or create new programs because it was trying to connect to an incorrect API endpoint.

## Root Cause
In `js/admin.js`, line 3 had an incorrect API base URL:
```javascript
const API_BASE = 'https://xxxx-xxx.ngrok-free.app/api/attendance/';
```
This was pointing to a non-existent ngrok domain.

## Fix Applied
Updated the API base URL to point to the local Django backend:
```javascript
const API_BASE = 'http://localhost:8000/api/attendance/';
```

## How to Access the Admin Panel

### 1. Start the Django Server
Make sure the Django development server is running:
```bash
cd backend
venv\Scripts\python manage.py runserver 0.0.0.0:8000
```
You should see output indicating the server is running at http://127.0.0.1:8000/

### 2. Access the Admin Panel
Open your web browser and go to:
```
http://localhost:8000/admin.html
```

### 3. Login Credentials
The admin panel uses its own authentication system (separate from Django admin):

**Username:** `admin` (or whatever you set as DJANGO_SUPERUSER_USERNAME in `.env`)
**Password:** As configured in your `.env` file (`DJANGO_SUPERUSER_PASSWORD`). If you did not set this before running `reset_db.py`, the default password might have been set to something else, or superuser creation was skipped.

### 4. First-Time Setup
If this is your first time accessing the admin panel:
1. Login with the credentials above
2. You should see the admin dashboard with navigation tabs
3. The "Program" toolbar should show existing programs in the dropdown
4. You can now:
   - View attendance records
   - Add new programs using the "➕ Tambah Program" button
   - Manage certificate settings
   - Generate and download certificates

### 5. Troubleshooting

#### If you see "Cannot connect to server" errors:
- Ensure the Django server is running on port 8000
- Check that you're accessing `http://localhost:8000/admin.html`
- Verify the API_BASE in `js/admin.js` is set to `'http://localhost:8000/api/attendance/'`

#### If login fails:
- Username must match your `DJANGO_SUPERUSER_USERNAME` (default is `admin`)
- Password must match your `DJANGO_SUPERUSER_PASSWORD`
- Make sure caps lock is off

#### If you want to change the password:
1. Login to the admin panel
2. Go to the "Settings" tab (⚙️ Tetapan)
3. Scroll to the "Keselamatan / Security" section
4. Enter a new password (minimum 6 characters)
5. Confirm the new password
6. Click "💾 Simpan Kata Laluan"

## Django Admin vs Custom Admin Panel

This system has two admin interfaces:

1. **Django Admin** (standard Django interface):
   - URL: `http://localhost:8000/admin/`
   - Requires Django superuser credentials
   - Good for direct database management

2. **Custom SPKB Admin Panel** (the one we fixed):
   - URL: `http://localhost:8000/admin.html`
   - Uses username: `admin` (or your configured username), password: As configured in `.env`
   - Designed specifically for SPKB attendance management
   - Includes certificate generation, program management, and attendance tracking

## Verification Test

To verify the fix is working, you can test the API connection directly:
- Visit: `http://localhost:8000/api/attendance/programs/`
- You should see JSON data listing all programs

If you see the programs data, then the admin panel should be able to connect and display information properly.

---
*Instructions generated: $(date)*
