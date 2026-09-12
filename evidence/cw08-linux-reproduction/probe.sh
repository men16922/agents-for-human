#!/bin/sh
set -eu
cp -a /input /workspace
cp -a /input-cache /tmp/npm-cache
cd /workspace
node -p 'JSON.stringify({node:process.version,os:process.platform,arch:process.arch})' > /output/runtime.json
npm ci --offline --no-audit --cache /tmp/npm-cache > /output/npm-ci.log 2>&1
npm run build:web > /output/web-build.log 2>&1
