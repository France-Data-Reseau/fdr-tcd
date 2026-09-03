FROM python:3.11-slim

ARG GIT_SHA=dev

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    GIT_SHA=${GIT_SHA} \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Code applicatif (tests/docs/kit exclus par .dockerignore)
COPY app/ app/
COPY scripts/ scripts/
COPY templates/ templates/
COPY static/ static/

# Utilisateur non-root
RUN useradd --create-home --uid 1000 fdr2 && chown -R fdr2:fdr2 /app
USER fdr2

EXPOSE 8000

# Vivacité sans I/O externe ni curl (absent de slim) : /health ne touche pas Grist
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"]

# MONO-WORKER : invariant du projet (cache mémoire et rate limiting) —
# ne JAMAIS ajouter --workers (voir MAINTENANCE.md §A).
# --proxy-headers : l'IP réelle vient de Caddy (rate limiting par IP).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
