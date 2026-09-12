#!/bin/sh
# Run inside the prepared reproduction image with Docker --network none.
set -eu
cd /workspace
make check
make check-browser
make b2-smoke
make b3-smoke
make frozen-evaluation-smoke
make evaluation-batch-smoke
# Config validation also runs during compilation. These values are build-only;
# port 1 has no service, and the container has no network or host credentials.
env DATABASE_URL=postgres://build-only:build-only@127.0.0.1:1/build_only \
    REDIS_URL=redis://127.0.0.1:1 \
    JWT_SECRET=build-only-not-a-service-secret \
    COOKIE_SECRET=build-only-not-a-service-secret \
    scripts/dev/with-env.sh npm run medusa:build
