import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CommandLineTests(unittest.TestCase):
    def test_help_exposes_the_workflow_commands_without_logging_in(self):
        result = subprocess.run([sys.executable, "-m", "specflow", "--help"], cwd=ROOT,
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        for command in ("init", "run", "approve", "resume", "status", "report", "demo", "doctor"):
            self.assertIn(command, result.stdout)


if __name__ == "__main__":
    unittest.main()
