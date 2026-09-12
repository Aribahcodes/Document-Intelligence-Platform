FROM python:3.11-slim

# Tesseract is a system package (not pip-installable) - needed by ocr_service.py
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend ./backend
COPY frontend ./frontend

WORKDIR /app/backend
ENV PYTHONPATH=/app/backend
ENV PORT=8000
EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--worker-class", "gthread", "--workers", "1", "--threads", "4", "--timeout", "240", "app.main:app"]
