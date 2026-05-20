# syntax=docker/dockerfile:1.7
# Build with internet access; run in air-gapped environments.
#
# Build:
#   docker build -t garuda:airgap .
#
# Static scan (air-gapped, model pre-copied to host):
#   docker run --rm \
#     -v /host/models/mymodel:/models/mymodel:ro \
#     -v /host/scans:/scans \
#     garuda:airgap \
#     static --local-path /models/mymodel --out /scans/run1
#
# Dynamic scan (requires LiteLLM proxy reachable from container):
#   docker run --rm \
#     -v /host/scans/run1:/scans/run1 \
#     -v /host/policy.airgap.yaml:/etc/garuda/policy.yaml:ro \
#     -e LITELLM_BASE_URL=http://litellm.internal:4000 \
#     -e TARGET_MODEL_API_KEY=sk-... \
#     -e LITELLM_API_KEY=sk-... \
#     garuda:airgap \
#     dynamic /scans/run1 --model ollama/llama3.1:8b
#
# NOTE: set offline: true in policy.yaml to skip probes that fetch
# data from HuggingFace at runtime (realtoxicityprompts, trainingdata).

FROM python:3.11-slim

ARG SYFT_VERSION=1.9.0
ARG GRYPE_VERSION=0.79.0
ARG GITLEAKS_VERSION=8.21.2

# ── system packages ───────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates tar \
    && rm -rf /var/lib/apt/lists/*

# ── Node.js 22 (required for promptfoo) ───────────────────────────────────────
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g promptfoo \
    && npm cache clean --force

# ── security scanner binaries (arch-aware) ────────────────────────────────────
# syft + grype: amd64/arm64  |  gitleaks: x64/arm64
RUN set -ex; \
    ARCH=$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/'); \
    GL_ARCH=$(uname -m | sed 's/x86_64/x64/;s/aarch64/arm64/'); \
    curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh \
        | sh -s -- -b /usr/local/bin "v${SYFT_VERSION}"; \
    curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh \
        | sh -s -- -b /usr/local/bin "v${GRYPE_VERSION}"; \
    curl -fsSL "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_${GL_ARCH}.tar.gz" \
        | tar -xz -C /usr/local/bin gitleaks

# ── Python app (uv, frozen from uv.lock) ─────────────────────────────────────
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src/ src/

RUN uv sync --frozen --no-dev --extra dynamic

# ── prime garak probe + detector registry ────────────────────────────────────
RUN /app/.venv/bin/python -c \
    "import garak.probes; import garak.detectors; print('garak registry primed')" \
    2>&1 || true

# ── cache grype CVE database in image (no update needed at runtime) ───────────
RUN grype db update 2>&1 || true

# ── runtime environment ───────────────────────────────────────────────────────
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PROMPTFOO_DISABLE_TELEMETRY=1 \
    GRYPE_DB_AUTO_UPDATE=false

COPY policy.yaml /etc/garuda/policy.yaml

VOLUME ["/models", "/scans"]

ENTRYPOINT ["scan"]
CMD ["--help"]
