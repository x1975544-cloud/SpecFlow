"""Public process-boundary tests; fake CLI output is not model validation."""
from pathlib import Path
import json
import tempfile
import time
import unittest

from specflow.adapter import AdapterError, CodexAdapter


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace with spaces"
        self.workspace.mkdir()
        self.artifacts = self.root / "artifacts"
        self.fake = self.root / "fake_codex.py"

    def write_fake(self, body):
        self.fake.write_text("import sys, json, pathlib, time\nsys.stdin.reconfigure(encoding='utf-8')\nsys.stdout.reconfigure(encoding='utf-8')\n" + body, encoding="utf-8")
        return CodexAdapter(executable=str(self.fake), timeout=5)

    def test_structured_result_and_usage_arrive_from_real_process(self):
        adapter = self.write_fake('''
args = sys.argv[1:]
assert args[0] == "exec"
assert args[args.index("--sandbox") + 1] == "read-only"
assert "--json" in args
schema = json.loads(pathlib.Path(args[args.index("--output-schema") + 1]).read_text())
assert schema["required"] == ["summary", "acceptance_criteria", "tasks"]
assert "需求" in sys.stdin.read()
result = {"summary": "计划完成", "acceptance_criteria": ["过滤结果正确"], "tasks": ["增加筛选"]}
pathlib.Path(args[args.index("--output-last-message") + 1]).write_text(json.dumps(result), encoding="utf-8")
print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 42, "output_tokens": 9}}))
''')
        result = adapter.run(role="planner", prompt="需求: 添加筛选", workspace=self.workspace, artifact_dir=self.artifacts)
        self.assertEqual(result["summary"], "计划完成")
        self.assertEqual(result["acceptance_criteria"], ["过滤结果正确"])
        self.assertEqual(result["tasks"], ["增加筛选"])
        self.assertEqual(result["usage"]["input_tokens"], 42)
        self.assertTrue(list(self.artifacts.rglob("events.jsonl")))

    def test_incomplete_or_failed_turn_is_never_reported_as_success(self):
        for events, exit_code in [
            ([{"type": "turn.completed"}], 7),
            ([], 0),
            ([{"type": "turn.failed", "error": {"message": "Access denied"}}], 0),
            ([{"type": "error", "message": "Transport failed"}, {"type": "turn.completed"}], 0),
        ]:
            with self.subTest(events=events, exit_code=exit_code):
                adapter = self.write_fake('''
args = sys.argv[1:]
result = {"summary": "untrusted success", "acceptance_criteria": [], "tasks": []}
pathlib.Path(args[args.index("--output-last-message") + 1]).write_text(json.dumps(result), encoding="utf-8")
''' + f"\nfor event in {events!r}: print(json.dumps(event))\nsys.exit({exit_code})\n")
                with self.assertRaises(AdapterError) as caught:
                    adapter.run(role="executor", prompt="implement", workspace=self.workspace, artifact_dir=self.artifacts)
                self.assertIn("diagnostics", str(caught.exception).lower())
        diagnostics = list(self.artifacts.rglob("diagnostics.json"))
        self.assertEqual(len(diagnostics), 4)

    def test_invalid_structured_output_is_rejected(self):
        for payload in ["not JSON", "[]", '{"summary": 17, "acceptance_criteria": [], "tasks": []}', '{"summary": "done", "acceptance_criteria": [9], "tasks": []}', '{"summary": "done"}']:
            with self.subTest(payload=payload):
                adapter = self.write_fake('''
args = sys.argv[1:]
''' + f"\npathlib.Path(args[args.index('--output-last-message') + 1]).write_text({payload!r}, encoding='utf-8')\n" + '''
print(json.dumps({"type": "turn.completed"}))
''')
                with self.assertRaisesRegex(AdapterError, "structured output"):
                    adapter.run(role="executor", prompt="implement", workspace=self.workspace, artifact_dir=self.artifacts)

    def test_timeout_saves_partial_output_and_stops_child_processes(self):
        marker = self.root / "should-not-exist.txt"
        child_code = f"import time,pathlib; time.sleep(1.6); pathlib.Path({str(marker)!r}).write_text('escaped')"
        self.write_fake(f"import subprocess\nsubprocess.Popen([sys.executable, '-c', {child_code!r}])\nprint('partial output', flush=True)\ntime.sleep(30)\n")
        adapter = CodexAdapter(executable=str(self.fake), timeout=1)
        started = time.monotonic()
        with self.assertRaisesRegex(AdapterError, "timed out"):
            adapter.run(role="executor", prompt="implement", workspace=self.workspace, artifact_dir=self.artifacts)
        self.assertLess(time.monotonic() - started, 5)
        self.assertIn("partial output", next(self.artifacts.rglob("events.jsonl")).read_text())
        time.sleep(1)
        self.assertFalse(marker.exists(), "A timed-out descendant continued modifying files")

    def test_check_reports_only_installation_authentication_and_version(self):
        adapter = self.write_fake('''
if sys.argv[1:] == ["--version"]:
    print("codex-cli 1.2.3")
elif sys.argv[1:] == ["login", "status"]:
    print("Logged in using private-test-token-never-show", file=sys.stderr)
else:
    sys.exit(4)
''')
        status = adapter.check()
        self.assertEqual(set(status), {"installed", "authenticated", "version", "message"})
        self.assertTrue(status["installed"])
        self.assertTrue(status["authenticated"])
        self.assertEqual(status["version"], "codex-cli 1.2.3")
        self.assertNotIn("private-test-token", json.dumps(status))
        missing = CodexAdapter(executable=str(self.root / "missing-cli.exe")).check()
        self.assertFalse(missing["installed"])
        self.assertFalse(missing["authenticated"])


if __name__ == "__main__":
    unittest.main()
