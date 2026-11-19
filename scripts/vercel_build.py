"""Build the website; apply the approved USSD schema only in production."""
import os
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
# The approved USSD release uses Vercel's existing encrypted database configuration.
# This deliberately does not run a general migrate and never changes a preview database.
if os.environ.get('VERCEL') == '1' and os.environ.get('VERCEL_ENV') == 'production':
    subprocess.run([sys.executable, 'manage.py', 'apply_ussd_schema'], cwd=ROOT, check=True)
