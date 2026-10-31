"""Include real CAD/Three selection regressions in the standard test runner."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which('node')


def supported_node():
    if not NODE:
        return False
    try:
        return subprocess.run(
            [NODE, '-e', "process.exit(typeof require('node:module').register==='function' && typeof Response==='function' ? 0 : 1)"],
            capture_output=True, timeout=10,
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


@unittest.skipUnless(supported_node(), '3D selection tests require Node with module.register and Fetch (18.19+/20.6+)')
class Duck3DTests(unittest.TestCase):
    def test_physical_servo_selection(self):
        result = subprocess.run(
            [NODE, '--test', str(ROOT / 'tests/duck3d_unit.mjs')],
            cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
