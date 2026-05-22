# SPKB Program/Folder System Explained

## Overview
The SPKB Attendance System already implements a program-based 📁 system that automatically separates data by program/department. Each program acts like its own isolated 📁 containing only attendance records relevant to that specific program.

## How It Works

### 1. **Program Creation = Folder Creation**
When you create a new program (e.g., "Integrity 2026"), the system:
- Creates a new program entry in the Django database
- Automatically associates all new attendance records with the selected program
- Provides program-specific views in both the admin panel and Django admin

### 2. **Data Separation (The Folder Concept)**
Each program maintains completely separate data:
- **Integrity 2026 📁**: Contains ONLY records for Integrity 2026 participants
- **Perbadanan Labuan 📁**: Contains ONLY records for Perbadanan Labuan participants
- **Audit Lerma 2026 📁**: Contains ONLY records for Audit Lerma 2026 participants
- etc.

### 3. **Admin Panel Program Selection**
In the custom admin panel (`admin.html`):
- **Program Dropdown** (top toolbar): Lets you select which 📁 to view
- **"Semua Program"**: Shows combined view of ALL programs (like seeing all 📁 at once)
- **Specific Program**: Shows ONLY records for that selected 📁 (like opening one 📁)

### 4. **Automatic Synchronization**
The system automatically keeps both interfaces in sync:
- **Admin Panel ↔ Django Server**: Both use the same API endpoints
- **Program Selection**: When you pick a program in admin panel, it filters API calls by program ID
- **Real-time Updates**: Adding records to a program immediately shows in that program's view

## Demonstration: Integrity 2026 Example

### Step 1: Create the Program/Folder
In admin panel:
1. Click "➕ Tambah Program" button
2. Enter program name: "Integrity 2026"
3. Click Save

### Step 2: Add Data to the Folder
In admin panel:
1. Ensure "Integrity 2026" is selected in the program dropdown
2. Fill out attendance form with participant data
3. Submit form

### Step 3: Verify Folder Isolation
In admin panel:
1. Select "Integrity 2026" from dropdown → See ONLY Integrity 2026 records
2. Select "Perbadanan Labuan" from dropdown → See ONLY Perbadanan Labuan records  
3. Select "Semua Program" → See ALL records from all programs combined

## Technical Implementation

### Backend (Django)
- `AttendanceRecord` model has `program` ForeignKey field
- API endpoints automatically filter by `program_id` when provided
- Certificate generation uses program-specific `cert_delay` settings

### Frontend (Admin Panel)
- `currentProgramId` variable tracks selected program
- All API calls include `?program={currentProgramId}` when a specific program is selected
- `loadPrograms()` populates the dropdown with all available programs
- `refreshData()` refreshes records based on current program selection

## Benefits for Multi-Department Usage

### 1. **Data Privacy**
- Department A cannot see Department B's attendance records unless viewing "Semua Program"
- Each department manages only their own participant data

### 2. **Independent Certificate Settings**
- Each program can have different certificate generation delays
- Each program can have different certificate templates/settings
- Certificate generation is program-specific

### 3. **Clean Reporting**
- Export CSV for specific program only
- Statistics show only selected program's data
- Easy to generate department-specific reports

### 4. **Scalability**
- Add unlimited programs (folders) as needed
- No performance degradation with more programs
- Each program's data is properly indexed in database

## Usage Instructions for Department Users

### For Department Administrators:
1. **Login** to admin panel at `http://localhost:8000/admin.html`
2. **Select** your department's program from the dropdown
3. **Manage** only your department's data:
   - Add new participants via attendance form
   - View your department's participant list
   - Generate certificates for your department only
   - Export your department's data

### For Super Administrators:
1. Can view all programs by selecting "Semua Program"
2. Can create new programs for new departments
3. Can manage system-wide settings that affect all programs
4. Can cross-reference data between departments when needed

## Verification That It's Working

Test the separation yourself:
1. Create two programs: "Dept A Training" and "Dept B Workshop"
2. Add 2 participants to "Dept A Training"
3. Add 3 participants to "Dept B Workshop"
4. Select "Dept A Training" → Should show exactly 2 records
5. Select "Dept B Workshop" → Should show exactly 3 records  
6. Select "Semua Program" → Should show exactly 5 records total
7. Select each department again → Confirm correct isolation

## Files That Implement This System

### Backend:
- `backend/attendance/models.py`: `AttendanceRecord.program` ForeignKey
- `backend/attendance/views.py`: All API views filter by program when specified
- `backend/attendance/urls.py`: API routing

### Frontend:
- `js/admin.js`: 
  - `currentProgramId` variable (line 6)
  - `loadPrograms()` function (lines 73-87) 
  - `changeProgram()` function (lines 89-94)
  - `fetchRecords()` function (lines 133-146) - adds program filter
  - `loadSettings()` function (lines 494-531) - loads program-specific cert_delay
- `admin.html`: Program selector dropdown (lines 74-77)

## Conclusion
The program/folder system is already fully implemented and working correctly. Departments can use different programs as isolated folders for their data, with automatic synchronization between the admin panel and Django server. Each program maintains its own attendance records, certificate settings, and data views while still allowing administrators to view combined data when needed.

No additional development is required - simply use the existing program selection feature in the admin panel to isolate data by department/program.