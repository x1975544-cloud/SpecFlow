"""Executed in a fresh interpreter, never imported by generated tests."""
import importlib.util
import json
import sys
import unittest
from pathlib import Path


def main():
    root = Path(sys.argv[1]).resolve()
    result_path = Path(sys.argv[2]).resolve()
    sys.path.insert(0, str(root))
    suite = unittest.TestSuite()
    for index, relative in enumerate(sys.argv[3:]):
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise ValueError("test path outside workspace")
        try:
            spec = importlib.util.spec_from_file_location(f"workflow_test_{index}", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
        except Exception as exc:
            # Report import failures as errors, never as a valid red gate.
            message = f"{type(exc).__name__}: {exc}"
            print(message, file=sys.stderr)
            result_path.write_text(json.dumps({"tests": 0, "failures": 0, "errors": 1,
                                               "skipped": 0, "passed": False, "detail": message}), encoding="utf-8")
            return 1
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    data = {"tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
            "skipped": len(result.skipped), "expected_failures": len(result.expectedFailures),
            "unexpected_successes": len(result.unexpectedSuccesses),
            "passed": result.wasSuccessful() and result.testsRun > 0 and not result.skipped and not result.expectedFailures}
    result_path.write_text(json.dumps(data), encoding="utf-8")
    return 0 if data["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
