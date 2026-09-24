"""The public CLI. Run from the repository with python -m specflow."""
import argparse
import json
import sys
from pathlib import Path


def parser():
    result = argparse.ArgumentParser(prog="specflow", description="Spec-driven TDD workflow / Spec 驱动研发演示")
    commands = result.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="创建独立示例工作区")
    init.add_argument("path", type=Path)
    init.add_argument("--source", type=Path, help="兼容 todo-status-v1 的可信示例目录")
    for name, help_text in (("run", "运行至下一个人工门禁"), ("approve", "确认当前规格和计划"),
                            ("resume", "从已持久化的阶段继续"), ("status", "显示阶段与验证结果"),
                            ("report", "生成 Markdown 与 HTML 报告")):
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("path", type=Path)
        if name in ("run", "resume"):
            sub.add_argument("--model", default=None, help="可选：覆盖本次调用的模型")
            sub.add_argument("--timeout", type=int, default=300, help="单角色最长秒数，默认 300")
            sub.add_argument("--stop-after", choices=["red"], help="在红灯验证后暂停以演示恢复")
    commands.add_parser("doctor", help="检查 Python、Codex 与登录状态；不调用模型")
    demo = commands.add_parser("demo", help="明确标注 scripted 的离线流程演示")
    demo.add_argument("--scenario", choices=["success", "failure", "resume"], default="success")
    demo.add_argument("--destination", type=Path, required=True)
    return result


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = parser().parse_args(argv)
    try:
        from .engine import Workflow, WorkflowError, run_demo
        from .adapter import CodexAdapter
        if args.command == "doctor":
            print(json.dumps({"python": sys.version.split()[0], **CodexAdapter().check()}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "init":
            workflow = Workflow.create(args.path, source=args.source)
        elif args.command == "demo":
            workflow = run_demo(args.destination, args.scenario)
        else:
            workflow = Workflow(args.path)
            if args.command in ("run", "resume"):
                if args.timeout < 1:
                    raise WorkflowError("timeout 必须大于 0")
                workflow.run(adapter=CodexAdapter(model=args.model, timeout=args.timeout), stop_after=args.stop_after)
            elif args.command == "approve":
                workflow.approve()
            elif args.command == "report":
                workflow.report()
        print(json.dumps(workflow.status(), ensure_ascii=False, indent=2))
        return 2 if workflow.status()["stage"] == "failed" else 0
    except KeyboardInterrupt:
        print("已中断。状态已保存，可用 resume 继续。", file=sys.stderr)
        return 130
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"specflow: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
