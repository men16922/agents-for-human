# Build only from scripts/dev/source_snapshot.py's source directory.
# Downloads public bootstrap tools, pinned runtimes and locked packages.
# This recipe is prepared; a complete Linux build has not yet been verified.
FROM node@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5
RUN apt-get update \
    && apt-get install -y --no-install-recommends make git python3 python3-venv ca-certificates \
    && python3 -m venv /opt/bootstrap \
    && /opt/bootstrap/bin/pip install --no-cache-dir uv==0.11.23 \
    && rm -rf /var/lib/apt/lists/*
ENV PATH="/workspace/.venv/bin:/opt/bootstrap/bin:${PATH}" \
    UV_CACHE_DIR=/workspace/.tooling/uv-cache \
    UV_PYTHON_INSTALL_DIR=/workspace/.tooling/python \
    UV_PYTHON_PREFERENCE=only-managed \
    MEDUSA_DISABLE_TELEMETRY=true \
    DO_NOT_TRACK=1
WORKDIR /workspace
COPY . .
RUN test ! -e .env && test ! -e .git && test ! -e .local && test ! -e node_modules \
    && uv python install 3.12.13 --no-bin \
    && uv run --no-project --python 3.12.13 python scripts/dev/tooling.py \
    && make setup-deps \
    && make setup-browser \
    && scripts/dev/with-env.sh npx --no-install playwright install-deps chromium
# Tests are intentionally a separate run with --network none, not a build-layer cache hit.
CMD ["sh", "scripts/dev/reproduction-check.sh"]
