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

# Digest-pinned; Dependabot (docker ecosystem) proposes updates.
FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170 AS base

ARG SYFT_VERSION=1.44.0
ARG GRYPE_VERSION=0.112.0
ARG GITLEAKS_VERSION=8.30.1

# ── system packages ───────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates tar \
    && rm -rf /var/lib/apt/lists/*

# ── security scanner binaries: release tarballs, verified against pinned SHA-256 ─
# Bumping a version means updating its two checksums (from the release's
# *_checksums.txt). No install scripts piped to sh.
ARG SYFT_SHA256_AMD64=0e91737aee2b5baf1d255b959630194a302335d848ff97bb07921eb6205b5f5a
ARG SYFT_SHA256_ARM64=6f6cdcdc695721d91ce756e3b5bc3e3416599c464101f5e32e9c3f33054ee6d9
ARG GRYPE_SHA256_AMD64=acb14a030010fe9bdb9594b4ae108d9d14ef2f926d936aa0916dc62c89c058ea
ARG GRYPE_SHA256_ARM64=7fdeccf065965cc59386c656e5fcc1eb1bdf820e2433000bca7f010b8e6da155
ARG GITLEAKS_SHA256_AMD64=551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb
ARG GITLEAKS_SHA256_ARM64=e4a487ee7ccd7d3a7f7ec08657610aa3606637dab924210b3aee62570fb4b080
RUN set -eux; \
    case "$(uname -m)" in \
      x86_64)  A=amd64; GL=x64;   S_SYFT=$SYFT_SHA256_AMD64; S_GRYPE=$GRYPE_SHA256_AMD64; S_GL=$GITLEAKS_SHA256_AMD64 ;; \
      aarch64) A=arm64; GL=arm64; S_SYFT=$SYFT_SHA256_ARM64; S_GRYPE=$GRYPE_SHA256_ARM64; S_GL=$GITLEAKS_SHA256_ARM64 ;; \
      *) echo "unsupported arch $(uname -m)"; exit 1 ;; \
    esac; \
    fetch() { curl -fsSL -o /tmp/t.tgz "$1" && echo "$2  /tmp/t.tgz" | sha256sum -c - \
              && tar -xzf /tmp/t.tgz -C /usr/local/bin "$3" && rm /tmp/t.tgz; }; \
    fetch "https://github.com/anchore/syft/releases/download/v${SYFT_VERSION}/syft_${SYFT_VERSION}_linux_${A}.tar.gz" "$S_SYFT" syft; \
    fetch "https://github.com/anchore/grype/releases/download/v${GRYPE_VERSION}/grype_${GRYPE_VERSION}_linux_${A}.tar.gz" "$S_GRYPE" grype; \
    fetch "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_${GL}.tar.gz" "$S_GL" gitleaks; \
    syft version >/dev/null && grype version >/dev/null && gitleaks version

# ── Python app (uv, frozen from uv.lock) ─────────────────────────────────────
COPY --from=ghcr.io/astral-sh/uv:0.13.0@sha256:cdc6093146eb3ff6a40107b38f008b789e050e77ad87865e381d9917da55a168 /uv /usr/local/bin/uv

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
