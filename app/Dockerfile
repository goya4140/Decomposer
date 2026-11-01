FROM node:22-bookworm-slim AS node
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    DECOMPOSER_HOST=0.0.0.0 DECOMPOSER_DATA_DIR=/app/data HOME=/home/decomposer
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-impress poppler-utils tesseract-ocr tesseract-ocr-eng tesseract-ocr-chi-sim \
    fonts-liberation fonts-dejavu-core fonts-noto-cjk fontconfig \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 decomposer
WORKDIR /app
COPY requirements.lock package.json package-lock.json ./
RUN pip install -r requirements.lock && npm ci --omit=dev --no-audit --no-fund
COPY --chown=decomposer:decomposer . .
RUN mkdir -p /app/data && chown decomposer:decomposer /app/data
USER decomposer
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/healthz', timeout=3)" || exit 1
CMD ["python", "serve.py"]
