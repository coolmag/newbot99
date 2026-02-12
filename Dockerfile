FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED 1

# Устанавливаем системные зависимости
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    dnsutils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

# Диагностика сети и запуск
CMD ["sh", "-c", "echo '--- Starting Network Diagnostics ---' && nslookup api.telegram.org && echo '--- Diagnostics Finished, Starting App ---' && uvicorn main:app --host 0.0.0.0 --port 7860"]
