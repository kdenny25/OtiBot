FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements-web.txt .
RUN pip install -r requirements-web.txt

COPY . .

# run as a normal user, and give it the folders the app writes to
RUN useradd --create-home --uid 1000 otibot \
    && mkdir -p agent_module/data dividend_module/data \
    && chown -R otibot:otibot agent_module/data dividend_module/data
USER otibot

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/healthz', timeout=4)"

# one worker: Flask-SocketIO and the agent loop keep their state in this process
CMD ["gunicorn", "--worker-class", "geventwebsocket.gunicorn.workers.GeventWebSocketWorker", \
     "--workers", "1", "--bind", "0.0.0.0:5000", "--timeout", "120", \
     "--access-logfile", "-", "app:app"]
