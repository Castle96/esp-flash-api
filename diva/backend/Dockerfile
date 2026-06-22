FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PIP_NO_CACHE_DIR=1
ENV PYTHONUNBUFFERED=1
ENV ENV=production

WORKDIR /app

RUN groupadd -r diva && useradd -r -g diva -d /app -s /sbin/nologin diva

COPY requirements.txt .
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        curl && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN mkdir -p /app/logs && chown -R diva:diva /app

USER diva

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
