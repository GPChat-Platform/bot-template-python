# docker build -t mon-bot .  &&  docker run --env-file .env -v mon-bot-data:/data mon-bot
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/data PORT=8080 OPS_HOST=0.0.0.0
COPY bot_template ./bot_template
RUN useradd --system --uid 10001 bot && mkdir -p /data && chown bot /data
VOLUME /data
EXPOSE 8080
USER bot
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import os,urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('OPS_PORT','9100')+'/readyz',timeout=4).status==200 else 1)"
CMD ["python", "-m", "bot_template"]
