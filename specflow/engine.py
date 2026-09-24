"""Workflow decisions belong to this state machine, not to model prose."""
import json
import hashlib
import shutil
import difflib
import html
from pathlib import Path

from .store import atomic_json, exclusive, now, snapshot
from .testing import suite, acceptance


class WorkflowError(RuntimeError):
    pass


def copy_workspace(source: Path, destination: Path):
    snapshot(source)  # Reject links before copying.
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))


class Workflow:
    def __init__(self, path):
        self.root = Path(path).resolve()
        self.workspace = self.root / "workspace"
        if not (self.root / "state.json").is_file():
            raise WorkflowError("找不到任务状态；请先运行 init")

    @classmethod
    def create(cls, path, *, source=None, mode="live"):
        root = Path(path).resolve()
        if root.exists():
            raise WorkflowError("目标路径已存在，请选择新的任务目录")
        sample = Path(source).resolve() if source else Path(__file__).with_name("sample")
        if root.is_relative_to(sample.resolve()) or sample.resolve().is_relative_to(root):
            raise WorkflowError("任务目录与源目录不能互相包含")
        if not (sample / "todo_api.py").is_file() or not (sample / "requirement.md").is_file():
            raise WorkflowError("首版只支持包含 todo_api.py / requirement.md 的 todo-status-v1 示例")
        snapshot(sample)
        root.mkdir(parents=True)
        (root / "input").mkdir()
        (root / "artifacts").mkdir()
        copy_workspace(sample, root / "original")
        copy_workspace(sample, root / "workspace")
        shutil.copyfile(sample / "requirement.md", root / "input" / "requirement.md")
        files = sorted(p.relative_to(root / "workspace").as_posix()
                       for p in (root / "workspace" / "tests").glob("test*.py"))
        baseline = suite(root / "workspace", files, root / "artifacts" / "baseline", "baseline")
        data = {"version": 1, "profile": "todo-status-v1", "mode": mode, "stage": "ready" if baseline["passed"] else "failed",
                "created_at": now(), "updated_at": now(), "baseline": baseline, "baseline_files": files,
                "source_snapshot": snapshot(root / "original"), "baseline_snapshot": snapshot(root / "workspace"),
                "generated_files": [], "implementation_attempts": 0, "max_repairs": 2, "agent_calls": 0,
                "history": [{"time": now(), "stage": "ready" if baseline["passed"] else "failed", "message": "基线测试完成"}],
                "error": None if baseline["passed"] else "基线测试未通过，停止工作流"}
        atomic_json(root / "state.json", data)
        return cls(root)

    def _load(self):
        return json.loads((self.root / "state.json").read_text(encoding="utf-8"))

    def _save(self, data, stage=None, message=None):
        if stage:
            data["stage"] = stage
        data["updated_at"] = now()
        if message:
            data["history"].append({"time": now(), "stage": data["stage"], "message": message})
        atomic_json(self.root / "state.json", data)

    def status(self):
        data = self._load()
        return {"path": str(self.root), **data}

    def _fingerprint(self, include_plan=True):
        paths = [self.root / "input/requirement.md"]
        if include_plan:
            paths += [self.root / "artifacts/spec.json", self.root / "artifacts/plan.md"]
        payload = {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def _invoke(self, data, adapter, role, prompt, source=None):
        if data["agent_calls"] >= 10:
            raise WorkflowError("任务已达到 10 次角色调用上限，请检查日志后创建新任务")
        data["agent_calls"] += 1
        self._save(data, message=f"开始 {role} 调用 {data['agent_calls']}")
        directory = self.root / "artifacts" / f"role-call-{data['agent_calls']:02d}-{role}"
        directory.mkdir()
        trial = directory / "trial"
        copy_workspace(source or self.workspace, trial)
        before = snapshot(trial)
        result = adapter.run(role=role, prompt=prompt, workspace=trial, artifact_dir=directory / "agent")
        after = snapshot(trial)
        changes = {name for name in before.keys() | after.keys() if before.get(name) != after.get(name)}
        if role == "planner" and changes:
            raise WorkflowError("Planner 修改了工作文件，已拒绝产物")
        if role == "test_writer" and (not changes or any(name in before or not name.startswith("tests/test")
                                                         or "/" in name[len("tests/"):] or not name.endswith(".py") for name in changes)):
            raise WorkflowError("Test Writer 只允许新增 tests/test*.py，不能修改已有文件")
        if role == "executor" and any(name != "todo_api.py" for name in changes):
            raise WorkflowError("Executor 只允许修改 todo_api.py；测试与规范不可改")
        for key in ("summary", "acceptance_criteria", "tasks"):
            if key not in result:
                raise WorkflowError(f"角色结果缺少 {key}")
        atomic_json(directory / "result.json", result)
        data.setdefault("usage", []).append({"role": role, "call": data["agent_calls"], "usage": result.get("usage", {})})
        return trial, result, changes

    def approve(self):
        with exclusive(self.root):
            data = self._load()
            if data["stage"] != "awaiting_approval":
                raise WorkflowError("仅 awaiting_approval 阶段可以审批")
            if data["input_digest"] != self._fingerprint(False):
                raise WorkflowError("规划后的原始需求已变更，请创建新任务重新规划")
            if snapshot(self.workspace) != data["baseline_snapshot"]:
                raise WorkflowError("审批前工作区已变化，请创建新任务")
            data["approval"] = {"time": now(), "digest": self._fingerprint()}
            self._save(data, "approved", "人工确认当前规格和计划版本")

    def run(self, *, adapter, stop_after=None):
        with exclusive(self.root):
            data = self._load()
            adapter_mode = getattr(adapter, "mode", "live")
            if adapter_mode != data["mode"]:
                raise WorkflowError("不能在 live 与 offline_scripted 模式间切换同一个任务")
            if data["stage"] in ("completed", "failed", "awaiting_approval"):
                return
            if data["stage"] in ("ready", "planning"):
                if snapshot(self.workspace) != data["baseline_snapshot"]:
                    raise WorkflowError("工作区已变化，请使用新的任务目录")
                data["input_digest"] = self._fingerprint(False)
                self._save(data, "planning", "准备生成规格和计划")
                prompt = ("Inspect this trusted Python WSGI todo repository. Do not edit any files. "
                          "Plan the requirement below. Return JSON with summary, acceptance_criteria, tasks. "
                          "Include pending/done filtering, unknown/empty status=400, existing baseline behavior.\n\n"
                          + (self.root / "input/requirement.md").read_text(encoding="utf-8"))
                _, result, _ = self._invoke(data, adapter, "planner", prompt)
                atomic_json(self.root / "artifacts/spec.json", result)
                plan = "# 技术方案与任务\n\n" + result["summary"] + "\n\n" + "\n".join(
                    f"{i}. {task}" for i, task in enumerate(result["tasks"], 1)) + "\n"
                (self.root / "artifacts/plan.md").write_text(plan, encoding="utf-8")
                self._save(data, "awaiting_approval", "规格和计划已生成，等待人工确认")
                return

            if data.get("approval", {}).get("digest") != self._fingerprint():
                raise WorkflowError("审批后的需求、规格或计划已变化，请创建新任务")
            expected = data.get("checkpoint_snapshot", data["baseline_snapshot"])
            if snapshot(self.workspace) != expected:
                raise WorkflowError("工作副本已变化，不能沿用当前审批或检查点")
            try:
                spec = (self.root / "artifacts/spec.json").read_text(encoding="utf-8")
                if data["stage"] == "approved":
                    trial, _, changes = self._invoke(data, adapter, "test_writer",
                        "Add unittest tests in new tests/test*.py files for this specification. "
                        "Do not edit existing files. Tests must fail with AssertionError on the current implementation.\n" + spec)
                    files = sorted(changes)
                    evidence = self.root / "artifacts" / f"red-{data['agent_calls']}"
                    baseline = suite(trial, data["baseline_files"], evidence, "baseline")
                    red = suite(trial, files, evidence, "red")
                    data["red"] = red
                    if not baseline["passed"] or not (red["tests"] > 0 and red["failures"] > 0
                            and red["errors"] == 0 and red["exit_code"] == 1
                            and not red.get("skipped") and not red.get("expected_failures")
                            and not red.get("unexpected_successes")):
                        raise WorkflowError("红灯门禁失败：必须有真实断言失败且基线通过，不能有导入错误或跳过测试")
                    for name in files:
                        shutil.copyfile(trial / name, self.workspace / name)
                    data["generated_files"] = files
                    data["checkpoint_snapshot"] = snapshot(self.workspace)
                    self._save(data, "red", "新增测试已产生真实断言失败")
                    if stop_after == "red":
                        return
                if data["stage"] not in ("red", "implementing"):
                    raise WorkflowError(f"不支持的阶段: {data['stage']}")
                while data["implementation_attempts"] < 1 + data["max_repairs"]:
                    data["implementation_attempts"] += 1
                    self._save(data, "implementing", f"实现尝试 {data['implementation_attempts']}")
                    trial, _, _ = self._invoke(data, adapter, "executor",
                        "Implement the specification by editing only todo_api.py. Never edit tests or requirement.md.\n"
                        + spec + "\nPrevious verification:\n" + data.get("feedback", "First attempt."))
                    evidence = self.root / "artifacts" / f"green-{data['implementation_attempts']}"
                    green = suite(trial, data["baseline_files"] + data["generated_files"], evidence, "green")
                    verified = acceptance(trial, evidence)
                    data.update(green=green, acceptance=verified)
                    if green["passed"] and verified["passed"]:
                        shutil.copyfile(trial / "todo_api.py", self.workspace / "todo_api.py")
                        data["checkpoint_snapshot"] = snapshot(self.workspace)
                        data["error"] = None
                        self._save(data, "completed", "回归测试与独立验收全部通过")
                        return
                    data["feedback"] = "\n".join((evidence / name).read_text(encoding="utf-8")
                                                   for name in ("green.log", "acceptance.log"))[-16000:]
                    self._save(data, message="验证失败，保存诊断")
                raise WorkflowError("实现验证失败，已用完两轮修复机会")
            except (RuntimeError, ValueError, OSError) as exc:
                data["error"] = str(exc)
                self._save(data, "failed", str(exc))

    def report(self):
        with exclusive(self.root):
            data = self._load()
            original = self.root / "original"
            names = sorted(snapshot(original).keys() | snapshot(self.workspace).keys())
            patches = []
            for name in names:
                before, after = original / name, self.workspace / name
                left = before.read_text(encoding="utf-8", errors="replace").splitlines(True) if before.exists() else []
                right = after.read_text(encoding="utf-8", errors="replace").splitlines(True) if after.exists() else []
                patches.extend(difflib.unified_diff(left, right, fromfile="a/" + name, tofile="b/" + name))
            diff = "".join(patches)
            (self.root / "diff.patch").write_text(diff, encoding="utf-8")
            report = (f"# SpecFlow 运行报告\n\n模式: {data['mode']}\n\n阶段: {data['stage']}\n\n"
                      + ("离线 scripted fixture，不代表真实模型验收。\n\n" if data["mode"] == "offline_scripted" else "真实 Codex 调用模式。\n\n")
                      + "## 状态与验证证据\n\n```json\n" + json.dumps(data, ensure_ascii=False, indent=2)
                      + "\n```\n\n## 代码差异\n\n```diff\n" + diff + "\n```\n")
            (self.root / "report.md").write_text(report, encoding="utf-8")
            (self.root / "report.html").write_text(
                '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>SpecFlow 运行报告</title>'
                '<style>body{max-width:1000px;margin:40px auto;padding:20px;font-family:system-ui}'
                'pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><pre>' + html.escape(report) + '</pre></html>',
                encoding="utf-8")
            return self.root / "report.html"


def run_demo(path, scenario):
    from .fixtures import ScriptedAdapter
    if scenario not in {"success", "failure", "resume"}:
        raise WorkflowError("未知演示场景")
    workflow = Workflow.create(path, mode="offline_scripted")
    adapter = ScriptedAdapter(scenario)
    workflow.run(adapter=adapter)
    workflow.approve()
    workflow.run(adapter=adapter, stop_after="red" if scenario == "resume" else None)
    if scenario == "resume":
        workflow = Workflow(path)
        workflow.run(adapter=adapter)
    workflow.report()
    return workflow
