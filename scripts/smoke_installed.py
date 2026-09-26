"""Verify the installed distribution from a directory outside the checkout."""
import json
import os
from pathlib import Path
import subprocess
import sys
import sysconfig
import tempfile


def main():
    executable = Path(sysconfig.get_path("scripts")) / ("specflow.exe" if os.name == "nt" else "specflow")
    if not executable.is_file():
        raise RuntimeError(f"Installed CLI missing: {executable}")
    with tempfile.TemporaryDirectory(prefix="specflow-installed-") as directory:
        root = Path(directory)

        def run(*args, expected=0):
            result = subprocess.run([str(executable), *map(str, args)], cwd=root,
                                    capture_output=True, encoding="utf-8", timeout=60)
            if result.returncode != expected:
                raise RuntimeError(f"{args}: expected exit {expected}, got {result.returncode}\n"
                                   + result.stdout + result.stderr)
            return result.stdout

        run("--help")
        module = subprocess.run([sys.executable, "-I", "-m", "specflow", "--help"],
                                cwd=root, capture_output=True, encoding="utf-8", timeout=30)
        if module.returncode:
            raise RuntimeError(module.stderr)
        for scenario in ("success", "failure", "resume"):
            target = root / scenario
            expected = 2 if scenario == "failure" else 0
            status = json.loads(run("demo", "--scenario", scenario, "--destination", target, expected=expected))
            stage = "failed" if scenario == "failure" else "completed"
            if status["stage"] != stage or status["mode"] != "offline_scripted":
                raise RuntimeError(f"Unexpected demo state: {status['stage']}")
            observed = json.loads(run("status", target, expected=expected))
            if observed["stage"] != stage:
                raise RuntimeError("Persisted state differs from demo result")
            run("report", target, expected=expected)
            for name in ("report.md", "report.html", "diff.patch"):
                if not (target / name).is_file():
                    raise RuntimeError(f"Missing report artifact: {name}")
            if scenario != "failure" and not status["acceptance"]["passed"]:
                raise RuntimeError("Independent acceptance did not pass")
            print(f"Installed CLI: {scenario} -> {stage} (exit {expected})")


if __name__ == "__main__":
    main()
