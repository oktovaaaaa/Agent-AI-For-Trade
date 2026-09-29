FROM python:3.10-slim

WORKDIR /app

# Install dependensi
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy seluruh kode bot
COPY . .

# Jalankan bot
CMD ["python", "bot_hunter.py"]
