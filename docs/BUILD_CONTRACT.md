# 首版约定与开发接口

用户已确认：学习与作品展示、个人本机使用、命令行、Python 待办示例、复用 Codex、真实 TDD、失败重试上限与中断恢复。

## 已约定的测试边界

- CLI：init / run / approve / resume / status / report，观察退出码、公开状态及产物。
- 示例 API：GET /tasks 的已有行为及新增 status 筛选，使用真实测试进程。
- 执行器：独立进程调用的输入输出、失败与超时；测试替身仅用于离线验证，必须明确标记。

测试按一个行为失败再实现的顺序增加。无需重复请求用户确认这些已经约定的边界。

## 内部协作契约

根包 specflow，Python 3.12 标准库，无运行依赖。所有路径使用 pathlib。

`specflow.adapter` 提供：

```python
class AdapterError(RuntimeError): ...
class CodexAdapter:
    def __init__(self, *, executable: str | None = None, model: str | None = None, timeout: int = 300): ...
    def check(self) -> dict: ...  # installed, authenticated, version, message；绝不输出凭据
    def run(self, *, role: str, prompt: str, workspace: Path, artifact_dir: Path) -> dict: ...
```

run：执行 `codex exec`，workspace-write，仅工作副本可写；--json 收集事件和用量，--output-schema 限定最终输出。角色 planner/test_writer/executor。最终字典的必需字段：summary(str)、acceptance_criteria(list[str])、tasks(list[str])。必须非零退出、缺少 turn.completed、明确失败事件或无效结果时抛 AdapterError；独立 run 保存诊断产物。Windows 不拼接 shell 命令：优先发现 .cmd 后定位 node 与其 JS 入口，或者直接二进制执行。check 不读取或返回认证文件。支持本机已配置的模型，不硬编码特定模型，不改变全局配置。

工作流由 root 编写：init 创建独立副本，规划 -> awaiting_approval -> 测试生成 -> red gate -> 实现 -> green gate -> completed/failed。每个阶段使用新的受控试运行副本，成功验证允许的文件变更后才拷回工作副本；控制文件和原始样例不在 Agent 的可写目录中。锁、原子状态、可恢复日志。审批绑定规范/计划及工作副本摘要。

样例由 example agent 编写：`specflow/sample/todo_api.py`，stdlib WSGI API。内置 TASKS 含 pending/done；GET /tasks 基线返回全部，尚未实现 status 参数筛选。入口可以用 `python todo_api.py` 启动仅本机 HTTP。基线测试 `specflow/sample/tests/test_baseline.py` 必须全部通过。目标需求 `specflow/sample/requirement.md`：pending/done 筛选、无 status 返回全部、未知值返回 400。独立验收脚本保存在 `specflow/acceptance.py`，不复制给 Agent。执行脚本接收 workspace 路径，使用该目录 todo_api.py（在子进程里导入），输出 unittest 风格结果和正确进程码。基线测试不可改；新增测试位于 tests/test_feature.py 等新文件，核心引擎至少检查实际 AssertionError 的测试失败、不能把导入错误视为红灯。实现阶段禁止改变测试。

离线演示明确标注 scripted fixture，不算真实模型验收。CLI `demo --scenario success|failure|resume --destination PATH` 生成确定性流程证据；真实入口 `init PATH`、`run PATH`、`approve PATH`、`resume PATH`。

## 模块所有权

- root：engine.py、store.py、cli.py、testing.py、fixtures.py、核心集成测试、最终验收。
- adapter agent：adapter.py 与 test_adapter.py。
- example agent：sample/ 与 acceptance.py 及 test_sample.py。
- docs agent：README.md、docs/ARCHITECTURE.md、docs/DEMO.md。

同一角色最大 300 秒；失败最多两轮修复；首版所有费用信息按实际返回用量显示，不宣称精确金额限额。原始仓库内容只读；不自动提交、推送或部署。
