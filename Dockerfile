FROM python:3.12-alpine AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apk add --no-cache \
    build-base \
    pango-dev \
    cairo-dev \
    libffi-dev \
    jpeg-dev \
    zlib-dev \
    freetype-dev \
    harfbuzz-dev \
    musl-dev

WORKDIR /app
COPY backend/requirements.txt /app/
RUN python -m venv /venv && \
    /venv/bin/pip install --upgrade pip==26.1.2 && \
    /venv/bin/pip install -r requirements.txt && \
    rm -rf /root/.cache/pip

FROM python:3.12-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/venv/bin:$PATH"

RUN apk add --no-cache \
    pango \
    cairo \
    harfbuzz \
    fontconfig \
    font-liberation \
    freetype \
    zlib

COPY --from=builder /venv /venv
RUN /usr/local/bin/pip install --upgrade pip==26.1.2 && rm -rf /root/.cache/pip

RUN addgroup --system --gid 1001 app && \
    adduser --system --uid 1001 --ingroup app --home /home/app app && \
    chmod 755 /home/app

WORKDIR /app
COPY --chown=app:app backend /app/backend/
COPY --chown=app:app frontend /app/frontend/

WORKDIR /app/backend
RUN mkdir -p /app/backend/media /app/backend/staticfiles && \
    chown -R app:app /app /venv

USER app

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-", "--error-logfile", "-", "backend.wsgi:application"]
