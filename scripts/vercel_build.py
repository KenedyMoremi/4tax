"""Compile assets and check deployment settings without touching the database."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for command in [
    ['npm', 'ci', '--ignore-scripts', '--include=dev'],
    ['npm', 'run', 'build:css'],
    [sys.executable, 'manage.py', 'check', '--deploy', '--fail-level', 'WARNING'],
]:
    subprocess.run(command, cwd=ROOT, check=True)
# Vercel's Django builder collects STATIC_ROOT and publishes it to its CDN.
# Migrations are a separate, deliberate operation, never part of a preview build.
