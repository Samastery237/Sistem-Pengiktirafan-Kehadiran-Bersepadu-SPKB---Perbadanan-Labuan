# SPKB Deployment Security Guide

## Overview

This guide covers secure deployment of the SPKB Attendance System to production. It covers HTTPS configuration, PostgreSQL setup, environment variable management, security log monitoring, and firewall rules.

## Prerequisites

- Linux server (Ubuntu 22.04+ recommended)
- Python 3.12+
- PostgreSQL 15+
- Nginx
- SSL certificate (Let's Encrypt or commercial)

## 1. HTTPS Setup (Nginx Reverse Proxy)

### Nginx Configuration

Create `/etc/nginx/sites-available/spkb`:

```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com www.your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Static files
    location /static/ {
        alias /var/www/spkb/backend/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Proxy to Gunicorn
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }
}
```

### SSL Certificate (Let's Encrypt)

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com -d www.your-domain.com
```

## 2. PostgreSQL Setup

### Install and Configure

```bash
sudo apt install postgresql postgresql-contrib
sudo -u postgres psql
```

```sql
CREATE DATABASE spkb_production;
CREATE USER spkb_user WITH PASSWORD 'replace-with-strong-password';
ALTER ROLE spkb_user SET client_encoding TO 'utf8';
ALTER ROLE spkb_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE spkb_user SET timezone TO 'Asia/Kuala_Lumpur';
GRANT ALL PRIVILEGES ON DATABASE spkb_production TO spkb_user;
```

### Secure PostgreSQL

Edit `/etc/postgresql/15/main/postgresql.conf`:

```ini
listen_addresses = 'localhost'  # Only listen on localhost
port = 5432
ssl = on
ssl_cert_file = '/etc/ssl/certs/server.crt'
ssl_key_file = '/etc/ssl/private/server.key'
```

Edit `/etc/postgresql/15/main/pg_hba.conf`:

```
# Only allow local connections with password
local   all             all                                     md5
host    all             all             127.0.0.1/32            md5
```

### Migrate from SQLite

```bash
cd /var/www/spkb/backend

# Update .env with PostgreSQL settings
DJANGO_DB_ENGINE=django.db.backends.postgresql
DJANGO_DB_NAME=spkb_production
DJANGO_DB_USER=spkb_user
DJANGO_DB_PASSWORD=replace-with-strong-password
DJANGO_DB_HOST=localhost
DJANGO_DB_PORT=5432
DJANGO_DB_SSLMODE=require

# Run migrations
python manage.py migrate

# Create cache table (if using DatabaseCache)
python manage.py createcachetable

# Collect static files
python manage.py collectstatic --noinput

# Create superuser
python manage.py createsuperuser
```

## 3. Environment Variable Checklist

Ensure these are set in `/var/www/spkb/backend/.env`:

```bash
# Required
DJANGO_SECRET_KEY=<generate: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())">
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=your-domain.com,www.your-domain.com
DJANGO_CORS_ALLOWED_ORIGINS=https://your-domain.com
SITE_URL=https://your-domain.com

# Database
DJANGO_DB_ENGINE=django.db.backends.postgresql
DJANGO_DB_NAME=spkb_production
DJANGO_DB_USER=spkb_user
DJANGO_DB_PASSWORD=<strong-password>
DJANGO_DB_HOST=localhost
DJANGO_DB_PORT=5432
DJANGO_DB_CONN_MAX_AGE=600
DJANGO_DB_SSLMODE=require

# Cache (recommended: Redis for production)
DJANGO_CACHE_BACKEND=django.core.cache.backends.redis.RedisCache
DJANGO_CACHE_LOCATION=redis://127.0.0.1:6379/1

# Email
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=noreply@your-domain.com

# Sentry (optional)
SENTRY_DSN=https://your-sentry-dsn
SENTRY_ENVIRONMENT=production
```

## 4. Django Security Check

```bash
cd /var/www/spkb/backend
python manage.py check --deploy
```

Address all warnings before going live. Common fixes:

- `SECURE_SSL_REDIRECT` — already set to `True` in production
- `SESSION_COOKIE_SECURE` — already set to `True`
- `CSRF_COOKIE_SECURE` — already set to `True`
- `SECURE_HSTS_SECONDS` — already set to 31536000

## 5. Gunicorn Systemd Service

Create `/etc/systemd/system/spkb.service`:

```ini
[Unit]
Description=SPKB Attendance System
After=network.target postgresql.service redis.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/spkb/backend
Environment="PATH=/var/www/spkb/venv/bin"
ExecStart=/var/www/spkb/venv/bin/gunicorn \
    --access-logfile /var/log/spkb/access.log \
    --error-logfile /var/log/spkb/error.log \
    --workers 3 \
    --bind 127.0.0.1:8000 \
    backend.wsgi:application

Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable spkb
sudo systemctl start spkb
```

## 6. Security Log Monitoring

### Log Files

| File | Purpose | Format |
|------|---------|--------|
| `security.log` | Human-readable security events | Text |
| `security.json.log` | Machine-parseable security events | JSON |
| `django.log` | General Django warnings/errors | Text |

### What to Monitor

**Critical (alert immediately):**
- `AUTH_FAILURE` — repeated failed logins (brute force)
- `SCANNING_DETECTED` — enumeration/scanning attempts
- `ATTACK_PATH` — requests to known attack paths
- `SERVER_ERROR` — 5xx errors (potential exploitation)

**Warning (review periodically):**
- `RATE_LIMITED` — throttled requests
- `ACCESS_DENIED` — 403 responses
- `BOT BLOCKED` — bot detection triggers

### SIEM Integration

The `security.json.log` file outputs structured JSON suitable for ingestion by:
- ELK Stack (Elasticsearch, Logstash, Kibana)
- Splunk
- Datadog
- Grafana Loki

Example Logstash filter:

```ruby
filter {
  if [type] == "spkb-security" {
    json {
      source => "message"
    }
  }
}
```

### Log Rotation

Logs are automatically rotated at 10MB with 5 backups (configured in `settings.py`). For system-level rotation, create `/etc/logrotate.d/spkb`:

```
/var/log/spkb/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0640 www-data www-data
}
```

## 7. Firewall Rules

```bash
# Allow only SSH, HTTP, HTTPS
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp      # SSH (restrict to your IP if possible)
sudo ufw allow 80/tcp      # HTTP (for Let's Encrypt)
sudo ufw allow 443/tcp     # HTTPS
sudo ufw enable

# Verify
sudo ufw status verbose
```

**Important:** Do NOT expose PostgreSQL (5432) or Redis (6379) to the public internet. They should only listen on localhost (127.0.0.1).

## 8. Backup Strategy

```bash
#!/bin/bash
# /var/www/spkb/backup.sh
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=/var/backups/spkb

# Database backup
pg_dump -U spkb_user spkb_production | gzip > $BACKUP_DIR/db_$DATE.sql.gz

# Media/uploads backup
tar -czf $BACKUP_DIR/media_$DATE.tar.gz /var/www/spkb/backend/media/

# Keep only last 30 days
find $BACKUP_DIR -type f -mtime +30 -delete
```

Add to crontab: `0 2 * * * /var/www/spkb/backup.sh`

## 9. Maintenance

### Regular Updates

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Update Python packages
cd /var/www/spkb
source venv/bin/activate
pip install --upgrade -r backend/requirements.txt
python backend/manage.py migrate
sudo systemctl restart spkb
```

### Health Check

Monitor the health endpoint:
```bash
curl -s https://your-domain.com/api/attendance/health/
```

Expected response: `{"status": "ok"}` with status 200.

## 10. Incident Response

If you detect suspicious activity:

1. **Check logs:** `tail -f /var/www/spkb/backend/security.json.log | grep SCANNING_DETECTED`
2. **Block IP:** `sudo ufw deny from <suspicious-ip>`
3. **Review access logs:** `grep <suspicious-ip> /var/log/spkb/access.log`
4. **Rotate secrets if compromised:** Change `DJANGO_SECRET_KEY` and restart
5. **Report:** Document and escalate per your organization's incident response policy
