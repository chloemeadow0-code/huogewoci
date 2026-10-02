# Lingxi Island deployment extension. Apache-2.0; adapted MIT components in third_party.
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PORT=8080 \
    HOST=127.0.0.1 \
    DATA_DIR=/app/server/data
COPY systems/xiuxian/requirements-deploy.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY src /app/src
COPY systems/xiuxian /app/systems/xiuxian
COPY LICENSE /app/LICENSE
COPY NOTICE /app/NOTICE
COPY third_party /app/third_party
RUN useradd --create-home --uid 10001 xiuxian && mkdir -p /app/server/data && chown -R xiuxian:xiuxian /app/server/data
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/health')"
CMD ["python", "-m", "xiuxian.container"]
