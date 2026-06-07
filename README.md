# TicketHub – Django QR Code Ticketing System

A secure, role-based ticketing platform with QR code generation and real-time validation.

## Quick Start

```bash
# Install dependencies
pip install django qrcode pillow

# Run migrations
python manage.py migrate

# Start server
python manage.py runserver
```

Open http://127.0.0.1:8000

## Demo Accounts

| Username  | Password   | Role       |
|-----------|------------|------------|
| admin     | admin123   | Super Admin|
| seller1   | seller123  | Seller     |
| scanner1  | scanner123 | Scanner    |

## Features

- 🎫 Ticket creation with unique ID + QR code generation
- 📷 Camera-based QR scanning (html5-qrcode) + manual entry
- ✅ Real-time ticket validation with duplicate prevention
- 👥 Role-based access: Seller / Scanner / Admin
- 📊 Admin dashboard with stats, reports, audit logs
- 🔒 Tamper-resistant QR codes (signed token, not raw ID)
- 🗂 Full scan history per ticket

## Project Structure

```
ticketing_system/
├── manage.py
├── db.sqlite3
├── media/qrcodes/          ← Generated QR images
├── static/css/style.css
├── templates/tickets/
│   ├── base.html
│   ├── login.html
│   ├── dashboard.html
│   ├── create_ticket.html
│   ├── ticket_detail.html
│   ├── my_tickets.html
│   ├── scan_ticket.html
│   ├── ticket_management.html
│   ├── user_management.html
│   ├── create_user.html
│   ├── edit_user.html
│   └── reports.html
└── tickets/
    ├── models.py       ← Ticket, ScanLog, UserProfile
    ├── views.py        ← All view logic
    ├── forms.py
    ├── urls.py
    ├── utils.py        ← QR code generation
    └── decorators.py   ← Role-based access control
```

## Security Notes

- QR codes encode a 64-character random hex token (not the ticket ID)
- All scans are logged with timestamp and operator
- Duplicate scan detection is instant and recorded
- Role-based decorators protect every view
- Change SECRET_KEY in settings.py before deploying to production
