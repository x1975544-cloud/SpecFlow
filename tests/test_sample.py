"""Exercise the bundled project and external verifier as actual processes."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "specflow" / "sample"
ACCEPTANCE = ROOT / "specflow" / "acceptance.py"


class SampleProjectTests(unittest.TestCase):
    def run_acceptance(self, workspace):
        return subprocess.run(
            [sys.executable, str(ACCEPTANCE), str(workspace)],
            text=True, capture_output=True, timeout=30,
        )

    def test_sample_baseline_passes(self):
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
            cwd=SAMPLE, text=True, capture_output=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Ran 3 tests", result.stderr)

    def test_external_acceptance_rejects_unimplemented_feature(self):
        result = self.run_acceptance(SAMPLE)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("AssertionError", result.stderr)
        self.assertNotIn("ERROR:", result.stderr)

    def test_external_acceptance_accepts_a_complete_implementation(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "project"
            shutil.copytree(SAMPLE, workspace, ignore=shutil.ignore_patterns("__pycache__"))
            source = workspace / "todo_api.py"
            source.write_text(
                source.read_text(encoding="utf-8").replace(
                    "    return json_response(start_response, '200 OK', TASKS)",
                    "    from urllib.parse import parse_qs\n"
                    "    query = parse_qs(environ.get('QUERY_STRING', ''), keep_blank_values=True)\n"
                    "    if 'status' in query:\n"
                    "        status = query['status'][0]\n"
                    "        if status not in ('pending', 'done'):\n"
                    "            return json_response(start_response, '400 Bad Request', {'error': 'invalid status'})\n"
                    "        return json_response(start_response, '200 OK', [task for task in TASKS if task['status'] == status])\n"
                    "    return json_response(start_response, '200 OK', TASKS)",
                ), encoding="utf-8",
            )
            result = self.run_acceptance(workspace)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Ran 5 tests", result.stderr)


if __name__ == "__main__":
    unittest.main()
