FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# Konfigurasi environment agar log langsung muncul & ramah OpenShift
ENV PYTHONUNBUFFERED=1 \
    TZ=Asia/Jakarta \
    HOME=/app \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ensure playwright chromium is installed
RUN playwright install chromium

# Copy all source files
COPY . .

# Berikan izin penuh pada folder /app untuk user non-root OpenShift
RUN chgrp -R 0 /app && chmod -R g=u /app && chmod -R 777 /app

# Run bot
CMD ["python", "bot_hunter.py"]
