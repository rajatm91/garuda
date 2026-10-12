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
#     all --local-path /models/mymodel --out /scans/run1

FROM python:3.14-slim

ARG SYFT_VERSION=1.9.0
ARG GRYPE_VERSION=0.79.0
ARG GITLEAKS_VERSION=8.21.2

# ── system packages ───────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates tar \
    && rm -rf /var/lib/apt/lists/*

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

RUN uv sync --frozen --no-dev

# ── cache grype CVE database in image (no update needed at runtime) ───────────
RUN grype db update 2>&1 || true

# ── runtime environment ───────────────────────────────────────────────────────
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    GRYPE_DB_AUTO_UPDATE=false

VOLUME ["/models", "/scans"]

ENTRYPOINT ["scan"]
CMD ["--help"]
