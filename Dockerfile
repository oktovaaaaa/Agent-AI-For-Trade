FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# Install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ensure playwright chromium is installed
RUN playwright install chromium

# Copy all source files
COPY . .

# Set timezone to Asia/Jakarta (WIB)
ENV TZ=Asia/Jakarta

# Run bot
CMD ["python", "bot_hunter.py"]
