#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 scripts/local-config.py init
mvn -q -DskipTests clean package
docker network inspect fourtax-development >/dev/null 2>&1 || docker network create fourtax-development >/dev/null
docker compose up -d --build
python3 scripts/local-config.py ready
printf 'Registration mock is running on its configured port (default http://localhost:8081).\n'
