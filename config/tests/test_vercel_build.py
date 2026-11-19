import os
import runpy
import subprocess
from pathlib import Path
from unittest.mock import patch
from django.core.management import call_command, CommandError
from django.test import SimpleTestCase


class VercelBuildTests(SimpleTestCase):
    def build(self, environment):
        path = Path(__file__).resolve().parents[2] / 'scripts/vercel_build.py'
        with patch.dict(os.environ, environment, clear=True), patch('subprocess.run') as run:
            runpy.run_path(str(path))
            return [call.args[0] for call in run.call_args_list]

    def test_only_production_builds_apply_the_release_schema_after_checks(self):
        for environment in ['preview', 'development', 'staging', '']:
            commands = self.build({'VERCEL': '1', 'VERCEL_ENV': environment})
            self.assertFalse(any('apply_ussd_schema' in c for c in commands))
        commands = self.build({'VERCEL': '1', 'VERCEL_ENV': 'production'})
        self.assertIn('check', commands[-2]); self.assertIn('apply_ussd_schema', commands[-1])
        self.assertFalse(any(command[-1:] == ['migrate'] for command in commands))

    def test_build_stops_before_migration_when_checks_fail(self):
        path = Path(__file__).resolve().parents[2] / 'scripts/vercel_build.py'
        with patch.dict(os.environ, {'VERCEL': '1', 'VERCEL_ENV': 'production'}, clear=True), patch('subprocess.run') as run:
            run.side_effect = [None, None, subprocess.CalledProcessError(1, 'check')]
            with self.assertRaises(subprocess.CalledProcessError): runpy.run_path(str(path))
            self.assertFalse(any('apply_ussd_schema' in call.args[0] for call in run.call_args_list))

    def test_command_rejects_nonproduction_before_any_database_access(self):
        with patch.dict(os.environ, {'VERCEL': '1', 'VERCEL_ENV': 'preview'}, clear=True):
            with self.assertRaisesMessage(CommandError, 'production Vercel build'): call_command('apply_ussd_schema')
