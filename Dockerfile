# syntax=docker/dockerfile:1.7
# Build with internet access; run in air-gapped environments.
#
# Build (two flavours from one Dockerfile; they share every layer but the last):
#   docker build -t garuda:latest .                            # default: runs as root
#   docker build --target nonroot -t garuda:nonroot .          # runs as uid/gid 1000
#
# Non-root on Linux: the bind-mounted output dir must be writable by uid 1000
# (e.g. `mkdir out && chown 1000:1000 out`, or `chmod 777 out`).
#
# Static scan (air-gapped, model pre-copied to host):
#   docker run --rm \
#     -v /host/models/mymodel:/models/mymodel:ro \
#     -v /host/scans:/scans \
#     garuda:airgap \
#     all --local-path /models/mymodel --out /scans/run1

FROM python:3.14-slim AS base

ARG SYFT_VERSION=1.44.0
ARG GRYPE_VERSION=0.112.0
ARG GITLEAKS_VERSION=8.30.1

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

# ── semgrep (step 12, custom model code) + offline rule packs — before COPY src so
#    code changes don't reinstall it ─────────────────
# Isolated tool venv so semgrep's dependencies don't touch the app's lockfile.
ARG SEMGREP_VERSION=1.180.0
ENV UV_TOOL_DIR=/opt/uv-tools UV_TOOL_BIN_DIR=/usr/local/bin
RUN uv tool install "semgrep==${SEMGREP_VERSION}" \
    && mkdir -p /opt/semgrep-rules \
    && curl -fsSL https://semgrep.dev/c/p/python -o /opt/semgrep-rules/python.yml \
    && curl -fsSL https://semgrep.dev/c/p/security-audit -o /opt/semgrep-rules/security-audit.yml \
    && semgrep --version

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src/ src/

RUN uv sync --frozen --no-dev

# ── cache grype CVE database in image (no update needed at runtime) ───────────
# Fail the build if the DB can't be fetched: an image without a usable DB makes
# step 09 silently useless.
# Outside /root so the non-root image can read it too.
ENV GRYPE_DB_CACHE_DIR=/opt/grype/db
RUN grype db update && grype db status && chmod -R a+rX /opt/grype

# ── runtime environment ───────────────────────────────────────────────────────
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    GRYPE_DB_AUTO_UPDATE=false \
    GRYPE_DB_VALIDATE_AGE=false \
    GARUDA_SEMGREP_CONFIGS=/opt/semgrep-rules/python.yml,/opt/semgrep-rules/security-audit.yml

# Unprivileged user for the nonroot target; dirs created before VOLUME so ownership sticks.
RUN groupadd -g 1000 garuda && useradd -u 1000 -g 1000 -m -s /usr/sbin/nologin garuda \
    && mkdir -p /models /scans && chown garuda:garuda /models /scans

VOLUME ["/models", "/scans"]

ENTRYPOINT ["scan"]
CMD ["--help"]

# ── non-root image: docker build --target nonroot ─────────────────────────────
FROM base AS nonroot
USER garuda:garuda

# ── default image (last stage = what plain `docker build` produces): root ─────
FROM base AS root
