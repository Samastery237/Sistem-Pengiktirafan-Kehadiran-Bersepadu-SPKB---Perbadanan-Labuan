# Use Python 3.12 slim for a smaller footprint
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV DEBIAN_FRONTEND noninteractive

# Install system dependencies required for WeasyPrint and PyCairo
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpango-1.0-0 \
    libharfbuzz0b \
    libpangoft2-1.0-0 \
    libcairo2 \
    libcairo2-dev \
    pkg-config \
    libffi-dev \
    libjpeg-dev \
    libopenjp2-7-dev \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt /app/
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy the backend code
COPY backend /app/backend/

# Copy the frontend code (since Django serves it)
COPY frontend /app/frontend/

# Set working directory to the backend where manage.py is located
WORKDIR /app/backend

# Create media and static directories
RUN mkdir -p /app/backend/media /app/backend/staticfiles

# Expose port 8000
EXPOSE 8000

# Start Gunicorn server
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "backend.wsgi:application"]
