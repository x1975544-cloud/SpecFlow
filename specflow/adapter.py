"""Codex CLI process boundary. Never changes account or global configuration."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import uuid


class AdapterError(RuntimeError):
    """Execution failed; diagnostic artifacts describe the attempted call."""


_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
        "tasks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "acceptance_criteria", "tasks"],
    "additionalProperties": False,
}


class _WindowsJob:
    """Own only this invocation's descendants; close the handle to stop them."""
    def __init__(self, process: subprocess.Popen):
        import ctypes
        from ctypes import wintypes

        class BasicLimits(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                        ("flags", wintypes.DWORD), ("min_working_set", ctypes.c_size_t),
                        ("max_working_set", ctypes.c_size_t), ("active_processes", wintypes.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                        ("scheduling", wintypes.DWORD)]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [("basic", BasicLimits), ("io_counters", ctypes.c_ulonglong * 6),
                        ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                        ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t)]

        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.kernel.SetInformationJobObject.restype = wintypes.BOOL
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)) or not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            error = ctypes.get_last_error()
            self.close()
            raise ctypes.WinError(error)

    def close(self) -> None:
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def _stop_process_tree(process: subprocess.Popen, job: _WindowsJob | None) -> None:
    if job is not None:
        job.close()
    elif os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()


class CodexAdapter:
    def __init__(self, *, executable: str | None = None, model: str | None = None, timeout: int = 300):
        self.executable = executable
        self.model = model
        self.timeout = timeout

    def check(self) -> dict:
        """Use CLI status only; never read authentication files or relay their contents."""
        status = {"installed": False, "authenticated": False, "version": None, "message": "Codex CLI is unavailable."}
        options = {"capture_output": True, "text": True, "encoding": "utf-8", "errors": "replace", "timeout": min(self.timeout, 10), "shell": False}
        if os.name == "nt":
            options["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            command = self._command()
            version = subprocess.run(command + ["--version"], **options)
            status["installed"] = True
            match = re.search(r"(?m)^codex-cli (\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.]+)?)\s*$", version.stdout)
            if match:
                status["version"] = "codex-cli " + match.group(1)
            if version.returncode:
                status["message"] = "Codex CLI was found but its version check failed."
                return status
            authentication = subprocess.run(command + ["login", "status"], **options)
            status["authenticated"] = authentication.returncode == 0
            status["message"] = "Codex CLI is ready." if status["authenticated"] else "Codex CLI is installed; run codex login in your terminal."
        except subprocess.TimeoutExpired:
            status["message"] = "Codex CLI status check timed out."
        except (AdapterError, OSError):
            pass
        return status

    def _command(self) -> list[str]:
        location = self.executable or shutil.which("codex.exe") or shutil.which("codex.cmd") or shutil.which("codex")
        if not location:
            raise AdapterError("Codex CLI is not installed or is absent from PATH.")
        candidate = Path(location)
        if candidate.suffix.lower() == ".py":
            return [sys.executable, str(candidate)]
        if candidate.suffix.lower() in {".cmd", ".bat", ".ps1"}:
            entry = candidate.parent / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
            node = candidate.parent / "node.exe"
            node_path = str(node) if node.is_file() else shutil.which("node")
            if not entry.is_file() or not node_path:
                raise AdapterError("Cannot resolve the Codex npm launcher to Node and codex.js; supply a direct executable.")
            return [node_path, str(entry)]
        if candidate.suffix.lower() == ".js":
            node_path = shutil.which("node")
            if not node_path:
                raise AdapterError("Node.js is required for this Codex entry point.")
            return [node_path, str(candidate)]
        return [str(candidate)]

    def run(self, *, role: str, prompt: str, workspace: Path, artifact_dir: Path) -> dict:
        if role not in {"planner", "test_writer", "executor"}:
            raise AdapterError(f"Unsupported role: {role}")
        workspace = Path(workspace).resolve()
        if not workspace.is_dir():
            raise AdapterError("The execution workspace does not exist.")
        directory = Path(artifact_dir).resolve() / f"{role}-{uuid.uuid4().hex[:12]}"
        directory.mkdir(parents=True)
        schema_path = directory / "schema.json"
        result_path = directory / "result.json"
        schema_path.write_text(json.dumps(_SCHEMA, ensure_ascii=False, indent=2), encoding="utf-8")
        (directory / "prompt.txt").write_text(prompt, encoding="utf-8")
        command = self._command() + [
            "exec", "--sandbox", "read-only" if role == "planner" else "workspace-write",
            "--cd", str(workspace), "--skip-git-repo-check", "--color", "never",
            "--json", "--output-schema", str(schema_path), "--output-last-message", str(result_path),
        ]
        if self.model:
            command += ["--model", self.model]
        command.append("-")
        process = None
        job = None
        execution_error = None
        interrupted = False
        stdout = stderr = ""
        try:
            process = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace", cwd=workspace, shell=False,
                start_new_session=os.name != "nt",
                creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW) if os.name == "nt" else 0,
            )
            if os.name == "nt":
                job = _WindowsJob(process)
            stdout, stderr = process.communicate(input=prompt, timeout=self.timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
            interrupted = isinstance(exc, KeyboardInterrupt)
            execution_error = "Codex execution interrupted." if interrupted else f"Codex timed out after {self.timeout} seconds."
            if process is not None:
                _stop_process_tree(process, job)
                try:
                    stdout, stderr = process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    execution_error += " Output pipes did not close after termination."
        except OSError as exc:
            execution_error = f"Cannot start Codex process ({type(exc).__name__})."
            if process is not None:
                _stop_process_tree(process, job)
                stdout, stderr = process.communicate(timeout=5)
        finally:
            if job is not None:
                job.close()
        returncode = process.returncode if process is not None else None
        (directory / "events.jsonl").write_text(stdout, encoding="utf-8")
        (directory / "stderr.log").write_text(stderr, encoding="utf-8")
        def fail(message: str) -> None:
            (directory / "diagnostics.json").write_text(json.dumps({"role": role, "returncode": returncode, "error": message}, indent=2), encoding="utf-8")
            if interrupted:
                raise KeyboardInterrupt
            raise AdapterError(f"{message} Diagnostics: {directory}")

        if execution_error:
            fail(execution_error)
        if returncode:
            fail(f"Codex exited with status {returncode}.")
        events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
        warnings = []
        for index, event in enumerate(events):
            event_type = event.get("type", "")
            # The CLI emits retry notifications as `error`, then may recover.
            # Only this known notification followed by completion is nonfatal.
            if (event_type == "error"
                    and re.fullmatch(r"Reconnecting\.\.\. \d+/\d+ \(.+\)", event.get("message", ""))
                    and any(later.get("type") == "turn.completed" for later in events[index + 1:])):
                warnings.append(event["message"])
                continue
            if event_type == "error" or event_type.endswith(".failed"):
                fail(f"Codex reported {event_type}.")
        if not any(event.get("type") == "turn.completed" for event in events):
            fail("Codex did not report turn.completed.")
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            fail("Codex returned missing or invalid structured output.")
        if not isinstance(result, dict) or set(result) != set(_SCHEMA["required"]):
            fail("Codex structured output must contain exactly summary, acceptance_criteria, and tasks.")
        if not isinstance(result["summary"], str) or any(
            not isinstance(result[key], list) or any(not isinstance(value, str) for value in result[key])
            for key in ("acceptance_criteria", "tasks")
        ):
            fail("Codex structured output has incorrect field types.")
        for event in events:
            if event.get("type") == "turn.completed":
                result["usage"] = event.get("usage", {})
        (directory / "diagnostics.json").write_text(json.dumps({"role": role, "returncode": returncode, "error": None,
                                                               "warnings": warnings}, indent=2), encoding="utf-8")
        return result
