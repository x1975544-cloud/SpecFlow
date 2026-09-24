"""Runs actual tests and records independent, process-level evidence."""
import json
import os
import subprocess
import sys
from pathlib import Path


def _environment():
    # Keep normal OS runtime settings; don't pass common API secret variables to tests.
    return {k: v for k, v in os.environ.items()
            if not any(part in k.upper() for part in ("TOKEN", "SECRET", "PASSWORD", "API_KEY"))}


def suite(workspace: Path, files: list[str], artifacts: Path, label: str, timeout=60):
    artifacts.mkdir(parents=True, exist_ok=True)
    result_path = artifacts / f"{label}.json"
    command = [sys.executable, "-I", "-B", str(Path(__file__).with_name("test_runner.py")),
               str(workspace), str(result_path), *files]
    try:
        process = subprocess.run(command, cwd=workspace, env=_environment(), capture_output=True,
                                 encoding="utf-8", errors="replace", timeout=timeout)
        output = process.stdout + process.stderr
        result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {
            "tests": 0, "failures": 0, "errors": 1, "passed": False}
        result["exit_code"] = process.returncode
        if process.returncode not in (0, 1) or (process.returncode == 0) != result.get("passed", False):
            result.update(passed=False, errors=max(1, result.get("errors", 0)))
    except subprocess.TimeoutExpired:
        output = f"Test process exceeded {timeout} seconds."
        result = {"tests": 0, "failures": 0, "errors": 1, "passed": False, "timeout": True, "exit_code": 124}
    except (OSError, ValueError) as exc:
        output = str(exc)
        result = {"tests": 0, "failures": 0, "errors": 1, "passed": False, "exit_code": 1}
    (artifacts / f"{label}.log").write_text(output, encoding="utf-8")
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def acceptance(workspace: Path, artifacts: Path, timeout=60):
    artifacts.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-I", "-B", str(Path(__file__).with_name("acceptance.py")), str(workspace)]
    try:
        process = subprocess.run(command, cwd=workspace, env=_environment(), capture_output=True,
                                 encoding="utf-8", errors="replace", timeout=timeout)
        output = process.stdout + process.stderr
        result = {"passed": process.returncode == 0, "exit_code": process.returncode,
                  "profile": "todo-status-v1"}
    except subprocess.TimeoutExpired:
        output = f"Acceptance exceeded {timeout} seconds."
        result = {"passed": False, "exit_code": 124, "timeout": True, "profile": "todo-status-v1"}
    (artifacts / "acceptance.log").write_text(output, encoding="utf-8")
    (artifacts / "acceptance.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
