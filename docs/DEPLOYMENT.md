# SPKB Deployment Guide

## Environment Setup

1. Copy `.env.example` to `.env` and fill in your production values:
   ```bash
   cp .env.example .env
   # Edit .env with your actual values
   ```

2. Generate a strong secret key:
   ```bash
   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   ```

## Database Setup

### Using SQLite (default, suitable for low-medium traffic):
   ```bash
   python manage.py migrate
   ```

### Using PostgreSQL/MySQL:
1. Install required drivers:
   ```bash
   # For PostgreSQL
   pip install psycopg2-binary
   
   # For MySQL
   pip install mysqlclient
   ```
   
2. Update `.env` with database credentials
3. Update `DATABASES` setting in `settings.py` to use environment variables
4. Run migrations:
   ```bash
   python manage.py migrate
   ```

## Static Files

```bash
python manage.py collectstatic
```

## Creating Superuser

```bash
python manage.py createsuperuser
```

## Running the Application

### Using Gunicorn (recommended for production):
```bash
# Install gunicorn
pip install gunicorn

# Run
gunicorn backend.wsgi:application --bind 0.0.0.0:8000 --workers 3
```

### Using Docker (example):
Create a `Dockerfile`:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1

RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "backend.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
```

## Nginx Configuration Example

```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    location /static/ {
        alias /path/to/your/project/staticfiles/;
    }

    location /media/ {
        alias /path/to/your/project/media/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## SSL/TLS Setup (Let's Encrypt)

```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

## Environment Variables Reference

- `DJANGO_SECRET_KEY`: Django secret key (required)
- `DJANGO_DEBUG`: Set to `False` for production
- `DJANGO_ALLOWED_HOSTS`: Comma-separated list of allowed domains
- `DJANGO_CORS_ALLOWED_ORIGINS`: Comma-separated list of allowed CORS origins
- Database variables (if not using SQLite):
  - `DJANGO_DB_NAME`
  - `DJANGO_DB_USER`
  - `DJANGO_DB_PASSWORD`
  - `DJANGO_DB_HOST`
  - `DJANGO_DB_PORT`

## Verification Steps After Deployment

1. Test the main page loads correctly
2. Submit a test attendance record
3. Verify it appears in the admin panel
4. Test certificate status checking
5. Test certificate download (both frontend and backend methods)
6. Test admin login and program management
7. Test CSV export functionality
8. Check that DEBUG is actually False (trigger an error to verify no stack traces are shown)

## Maintenance

- Regularly backup your database
- Keep dependencies updated: `pip list --outdated` and `pip install -U package`
- Monitor logs for errors
- Consider setting up health checks and monitoring