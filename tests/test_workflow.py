import tempfile
import unittest
from pathlib import Path

from specflow.engine import Workflow, WorkflowError


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "run"

    def test_init_creates_an_independent_workspace_with_passing_baseline(self):
        workflow = Workflow.create(self.path)
        status = workflow.status()
        self.assertEqual(status["stage"], "ready")
        self.assertGreater(status["baseline"]["tests"], 0)
        self.assertTrue(status["baseline"]["passed"])
        self.assertTrue((self.path / "workspace" / "todo_api.py").exists())
        self.assertTrue((self.path / "input" / "requirement.md").exists())
        with self.assertRaises(WorkflowError):
            Workflow.create(self.path)

    def test_planning_stops_for_explicit_approval_before_tests_are_written(self):
        from specflow.fixtures import ScriptedAdapter
        workflow = Workflow.create(self.path, mode="offline_scripted")
        workflow.run(adapter=ScriptedAdapter())
        self.assertEqual(workflow.status()["stage"], "awaiting_approval")
        self.assertFalse((self.path / "workspace/tests/test_feature.py").exists())
        workflow.approve()
        self.assertEqual(workflow.status()["stage"], "approved")
        self.assertTrue(workflow.status()["approval"]["digest"])

    def test_red_gate_can_pause_then_resume_to_verified_completion(self):
        from specflow.fixtures import ScriptedAdapter
        workflow = Workflow.create(self.path, mode="offline_scripted")
        original = (self.path / "original/todo_api.py").read_bytes()
        workflow.run(adapter=ScriptedAdapter())
        workflow.approve()
        workflow.run(adapter=ScriptedAdapter(), stop_after="red")
        status = workflow.status()
        self.assertEqual(status["stage"], "red")
        self.assertGreater(status["red"]["failures"], 0)
        self.assertEqual(status["red"]["errors"], 0)
        recovered = Workflow(self.path)
        recovered.run(adapter=ScriptedAdapter())
        self.assertEqual(recovered.status()["stage"], "completed")
        self.assertTrue(recovered.status()["acceptance"]["passed"])
        self.assertEqual((self.path / "original/todo_api.py").read_bytes(), original)

    def test_failure_stops_after_two_repairs_and_writes_report(self):
        from specflow.engine import run_demo
        workflow = run_demo(self.path, "failure")
        status = workflow.status()
        self.assertEqual(status["stage"], "failed")
        self.assertEqual(status["implementation_attempts"], 3)
        self.assertFalse(status["acceptance"]["passed"])
        self.assertIn("offline_scripted", (self.path / "report.html").read_text(encoding="utf-8"))

    def test_approval_rejects_changed_plan(self):
        from specflow.fixtures import ScriptedAdapter
        workflow = Workflow.create(self.path, mode="offline_scripted")
        workflow.run(adapter=ScriptedAdapter())
        workflow.approve()
        (self.path / "artifacts/plan.md").write_text("changed", encoding="utf-8")
        with self.assertRaises(WorkflowError):
            workflow.run(adapter=ScriptedAdapter())
        self.assertEqual(workflow.status()["agent_calls"], 1)

    def test_import_error_does_not_satisfy_red_gate(self):
        from specflow.fixtures import ScriptedAdapter
        class BrokenTests(ScriptedAdapter):
            def run(self, **kwargs):
                result = super().run(**kwargs)
                if kwargs["role"] == "test_writer":
                    (kwargs["workspace"] / "tests/test_feature.py").write_text("import nonexistent_specflow_module\n")
                return result
        workflow = Workflow.create(self.path, mode="offline_scripted")
        workflow.run(adapter=BrokenTests())
        workflow.approve()
        workflow.run(adapter=BrokenTests())
        self.assertEqual(workflow.status()["stage"], "failed")
        self.assertEqual(workflow.status()["implementation_attempts"], 0)

    def test_executor_cannot_modify_tests(self):
        from specflow.fixtures import ScriptedAdapter
        class CheatingExecutor(ScriptedAdapter):
            def run(self, **kwargs):
                result = super().run(**kwargs)
                if kwargs["role"] == "executor":
                    (kwargs["workspace"] / "tests/test_feature.py").write_text("# removed tests\n")
                return result
        workflow = Workflow.create(self.path, mode="offline_scripted")
        workflow.run(adapter=CheatingExecutor())
        workflow.approve()
        workflow.run(adapter=CheatingExecutor())
        self.assertEqual(workflow.status()["stage"], "failed")
        self.assertIn("Executor", workflow.status()["error"])
        self.assertIn("FeatureTests", (self.path / "workspace/tests/test_feature.py").read_text())

    def test_resume_demo_generates_diff_and_report(self):
        from specflow.engine import run_demo
        workflow = run_demo(self.path, "resume")
        self.assertEqual(workflow.status()["stage"], "completed")
        self.assertIn("parse_qs", (self.path / "diff.patch").read_text(encoding="utf-8"))
        self.assertTrue((self.path / "report.md").is_file())


if __name__ == "__main__":
    unittest.main()
