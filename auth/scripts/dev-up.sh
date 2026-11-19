#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 scripts/local-config.py init
mvn -q -DskipTests clean package
docker network inspect fourtax-development >/dev/null 2>&1 || docker network create fourtax-development >/dev/null
python3 scripts/local-config.py volumes
docker compose up -d --build
python3 scripts/local-config.py ready
printf 'Auth is running on its configured port (default http://localhost:9000).\n'
