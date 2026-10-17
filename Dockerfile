# Imagem de producao: o frontend construido + o backend Flask servindo os dois
# na mesma origem (routes/frontend.py). Dados persistentes ficam em /data.

# --- 1. Build do frontend --------------------------------------------------
FROM node:24-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Sem VITE_API_BASE_URL: o build de producao chama a API na mesma origem.
RUN npx vite build
# A tela do APK, que o celular baixa para se atualizar (services/app_bundle.py):
# o mesmo codigo, com a API do servidor compilada, e o bundle.json com a versao.
# Mesmo endereco que mobile/build-apk.ps1 usa por padrao.
ARG APP_API_BASE=https://guilhermeserver.tail5084ff.ts.net
RUN VITE_API_BASE_URL="$APP_API_BASE" npx vite build --outDir dist-android --emptyOutDir \
    && node scripts/bundle-manifest.mjs dist-android "$APP_API_BASE"

# --- 2. Backend -------------------------------------------------------------
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=America/Sao_Paulo \
    DATABASE_PATH=/data/finance.db \
    DATABASE_BACKUP_DIR=/data/backups \
    ATTACHMENTS_DIR=/data/attachments \
    LOG_DIR=/data/logs \
    FRONTEND_DIST_DIR=/app/frontend/dist \
    APP_BUNDLE_DIR=/app/frontend/dist-android

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
COPY --from=frontend /app/frontend/dist-android frontend/dist-android

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
