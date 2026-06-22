# SPKB Website Sequence Flow

## Overview

This file shows the two separate flows for the SPKB system:
- public client flow
- admin flow

## Client QR Code Usage Steps

1. Scan the QR code for the specific program using a mobile device.
2. The QR code opens the SPKB registration page linked to that program.
3. Confirm the displayed program name and instructions.
4. Fill in the required personal information and attendance details.
5. Submit the form to register attendance for the program.
6. The system validates and saves the attendance record.
7. A confirmation or success page is displayed.

## Recommended QR Code Flow Chart

```mermaid
flowchart TD
    A[Scan Program QR Code] --> B[Open Program Registration Page]
    B --> C[Confirm Program Name & Instructions]
    C --> D[Fill in Personal & Attendance Details]
    D --> E[Submit Attendance Form]
    E --> F[Backend Validates Data]
    F --> G[Store Attendance Record]
    G --> H[Show Confirmation / Success Page]
```

## Public Client Flow

```mermaid
sequenceDiagram
    participant User
    participant Frontend as Frontend (HTML/JS)
    participant Backend as Backend (Django API)
    participant Database as Database (SQLite)

    User->>Frontend: Open landing page
    Frontend-->>User: Display index.html

    User->>Frontend: Go to registration
    Frontend-->>User: Display form.html

    User->>Frontend: Fill and submit form
    Frontend->>Backend: POST /api/attendance/submit/
    note right of Backend: Validate input\nSave attendance record
    Backend->>Database: Insert attendance record
    Database-->>Backend: Confirm saved
    Backend-->>Frontend: Return success
    Frontend-->>User: Redirect to success.html

    User->>Frontend: Check certificate by IC
    Frontend->>Backend: GET /api/attendance/participant/<ic>/
    note right of Backend: Lookup participant\nReturn status
    Backend->>Database: Query by IC number
    Database-->>Backend: Return record(s)
    Backend-->>Frontend: Send result
    Frontend-->>User: Show certificate status
```

## Admin Flow

```mermaid
sequenceDiagram
    participant Admin
    participant Frontend as Frontend (HTML/JS)
    participant Backend as Backend (Django API)
    participant Database as Database (SQLite)

    Admin->>Frontend: Open admin.html
    Frontend-->>Admin: Display login screen

    Admin->>Frontend: Submit credentials
    Frontend->>Backend: POST /api/attendance/auth/login/
    note right of Backend: Verify admin credentials
    Backend->>Database: Check credentials
    Database-->>Backend: Auth result
    Backend-->>Frontend: Return login response
    Frontend-->>Admin: Show admin dashboard

    Admin->>Frontend: Request records / stats
    Frontend->>Backend: GET /api/attendance/records/ or /api/attendance/stats/
    Backend->>Database: Fetch data
    Database-->>Backend: Return data
    Backend-->>Frontend: Display admin data
```