# Hogwarts deployment extension, 2026-10-02. Apache-2.0.
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PORT=8080 \
    HOST=127.0.0.1 \
    DATA_DIR=/app/server/data
COPY systems/hogwarts/requirements-deploy.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY src /app/src
COPY systems/hogwarts /app/systems/hogwarts
COPY LICENSE /app/LICENSE
COPY NOTICE /app/NOTICE
RUN useradd --create-home --uid 10001 hogwarts && mkdir -p /app/server/data && chown -R hogwarts:hogwarts /app/server/data
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/health')"
CMD ["python", "-m", "hogwarts.container"]
