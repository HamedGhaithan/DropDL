# DropDL Web. Build from the repository root:
#   docker build -f web/Dockerfile -t dropdl-web .
#   docker run --rm -p 7860:7860 dropdl-web
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

# ffmpeg merges and converts; tini reaps the helper processes yt-dlp starts
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg ca-certificates tini \
 && rm -rf /var/lib/apt/lists/*

# uid 1000 also satisfies hosts (such as Hugging Face Spaces) that run containers as that user
RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin app \
 && mkdir -p /data && chown app:app /data

# Node.js runs YouTube's checks. Only needed with YOUTUBE=on (plus cookies or a proxy), copied from the official image.
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node

WORKDIR /app
COPY web/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt
COPY web/server ./server
COPY web/static ./static

USER app
ENV PORT=7860 DATA_DIR=/data
EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT','7860'), timeout=4)"

ENTRYPOINT ["tini", "--"]
# The app reads X-Forwarded-For itself (see TRUSTED_PROXY_HOPS), so uvicorn's own proxy handling is off.
CMD ["sh", "-c", "exec python -m uvicorn server.app:app --host 0.0.0.0 --port ${PORT} --no-access-log --no-proxy-headers"]
