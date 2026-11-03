# FeedForward server (API + dashboard) for a container host such as Koyeb. See "Deploy on Koyeb" in the README.
# Build and run locally:  docker build -t feedforward .  &&  docker run -p 8000:8000 --env-file .env feedforward
FROM python:3.11-slim

# Small memory footprint on a 512 MB instance: one thread for the maths libraries, fewer malloc arenas.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MALLOC_ARENA_MAX=2 \
    PORT=8000

WORKDIR /app

# CPU only torch (about a fifth of the size of the default build, which bundles CUDA), then the rest.
RUN pip install --index-url https://download.pytorch.org/whl/cpu "torch>=2.3"
COPY requirements-deploy.txt .
RUN pip install -r requirements-deploy.txt

# Run as an ordinary user (UID 1000, which Hugging Face Spaces requires). It owns the app folder so the server
# can write reviews and Daily log entries to data_store/admin_logs.
RUN useradd --create-home --uid 1000 app
COPY --chown=app:app . .
USER app
ENV PYTHONPATH=/app/src:/app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import urllib.request, os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/api/health', timeout=4)"
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
