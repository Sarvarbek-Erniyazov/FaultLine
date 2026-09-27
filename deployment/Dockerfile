# The Lesson 11 API as a CPU image. Build from the repository root:
#   docker build -f deployment/Dockerfile -t faultline-l11 --build-arg GIT_SHA=$(git rev-parse HEAD) .
# The context is an allow-list (deployment/Dockerfile.dockerignore): the faultline package
# (src/), the three Lesson 11 packages, checkpoints/model.pt, the two tokenizer JSONs and the
# demo bundle. model.pt is gitignored, so it must exist locally (`python -m inference.export`).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first, so a code change does not reinstall them. torch from the CPU index.
COPY deployment/requirements.txt deployment/requirements.txt
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.14.0 \
    && pip install -r deployment/requirements.txt

# faultline is read from src/ on the path, not installed: pyproject.toml is not in the context.
COPY src/ src/
COPY inference/ inference/
COPY evaluation/ evaluation/
COPY deployment/ deployment/
COPY lesson11/demo/ lesson11/demo/
COPY data/tokenizers/quantile_bins_v2_9cd52b65.json data/tokenizers/text_bpe_v1_22c56e49.json data/tokenizers/
COPY checkpoints/model.pt checkpoints/model.pt

ARG GIT_SHA=unknown
ENV PYTHONPATH=/app/src:/app \
    FAULTLINE_GIT_SHA=${GIT_SHA} \
    PORT=8000

# A non-root user; the files stay root-owned and read-only to it.
RUN useradd --create-home --uid 10001 faultline
USER faultline

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT', '8000'), timeout=4)"

CMD ["sh", "-c", "exec uvicorn deployment.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
