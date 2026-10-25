# Imagem de producao: o frontend construido + o backend Flask servindo os dois
# na mesma origem (routes/frontend.py). Dados persistentes ficam em /data.

# --- 1. Build do frontend --------------------------------------------------
FROM node:24-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Sem VITE_API_BASE_URL: o build de producao chama a API na mesma origem. O APK e
# todo nativo (sem WebView): a imagem nao leva mais uma tela para ele.
RUN npx vite build

# --- 2. Backend -------------------------------------------------------------
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=America/Sao_Paulo \
    DATABASE_PATH=/data/finance.db \
    DATABASE_BACKUP_DIR=/data/backups \
    ATTACHMENTS_DIR=/data/attachments \
    LOG_DIR=/data/logs \
    FRONTEND_DIST_DIR=/app/frontend/dist

# tzdata: local_today() usa datetime.now(), entao o fuso do container e o "hoje" do app.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt gunicorn==23.0.0

COPY backend/ backend/
COPY database/ database/
COPY --from=frontend /app/frontend/dist frontend/dist

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app app \
    && mkdir -p /data \
    && chown app:app /data
USER app

VOLUME ["/data"]
EXPOSE 5000
WORKDIR /app/backend

# Um processo so: o boot (migrations, backup) roda no import de app.py e os
# caches (cotacoes, proventos, pacing da StatusInvest) vivem em memoria. Concorrencia por threads.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "8", "--timeout", "120", "--access-logfile", "-", "app:app"]
