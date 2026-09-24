# 演示与验收

本指南用于复现流程和讲解作品。所有命令在项目根目录运行，需要 Python 3.12 或更高版本。下文目标目录需事先不存在；已有一次运行时，使用 `status`、`report` 或 `resume`，不要重新初始化覆盖。

## 演示前说明

可以这样介绍项目：

> 这是一个规格驱动研发流程的学习项目。它在一个固定待办 API 示例上，串联规划、人工确认、生成测试、实际运行测试、实现、验证和记录。离线演示使用固定角色替身；真实模型执行需要登录本机 Codex 后单独验收。

不要把离线 fixture 称为模型自主完成，也不要把固定示例推广成“支持任意仓库”。目前没有用于支撑效率提升百分比的实测数据。

## 场景一：正常完成

```powershell
python -m specflow demo --scenario success --destination work/demo-success
python -m specflow status work/demo-success
python -m specflow report work/demo-success
```

观察并展示：

- 执行方式标记为 `offline_scripted`。
- 阶段最终为 `completed`。
- 原始需求要求筛选状态、保留无参数行为、拒绝未知状态。
- 新功能测试先出现实际断言失败，再随着实现修改变为通过。
- 最终报告包含验证结果和代码变更；测试通过来自真实测试进程。

讲解重点是角色交接及门禁条件。脚本替身让流程证据可重复出现，它没有证明模型能生成同样的结果。

打开 `work/demo-success/report.html` 查看报告，`report.md` 是对应 Markdown 版本，`diff.patch` 显示候选实现相对原始项目的变更。原始项目保存在 `original/`，候选实现位于 `workspace/`，状态时间线位于 `state.json` 的 `history` 中。

## 场景二：失败阻止完成

```powershell
python -m specflow demo --scenario failure --destination work/demo-failure
python -m specflow status work/demo-failure
python -m specflow report work/demo-failure
```

第一条命令预期返回非零退出码。检查最终 `failed` 状态、失败验证结果和有限修复记录。报告应保留失败原因，不应把生成了代码、用尽重试次数或成功生成报告视为任务完成。

这是刻意制造的失败演示，不是需要不断重跑直至成功的安装故障。

## 场景三：保存检查点后恢复

```powershell
python -m specflow demo --scenario resume --destination work/demo-resume
python -m specflow status work/demo-resume
python -m specflow report work/demo-resume
```

查看记录中暂停与继续的阶段，确认恢复沿用此前已经接纳的规格、审批和测试产物。该场景由离线替身驱动，展示的是检查点恢复。它不等同于断电后恢复、任意损坏恢复或模型调用中间状态续传。

## 真实模型验收

2026-09-25 已完成一次真实模型验收，见[运行记录](validation/2026-09-25/README.md)。以下步骤可用于另建任务复验，需要账户已登录且拥有可用额度；每次结果应以实际执行证据为准。

```powershell
python -m specflow doctor
codex login
python -m specflow doctor
python -m specflow init work/live-todo
python -m specflow run work/live-todo
python -m specflow status work/live-todo
```

查看 `work/live-todo/artifacts/spec.json` 和 `work/live-todo/artifacts/plan.md`，确认需求和验收条件正确后再审批：

```powershell
python -m specflow approve work/live-todo
python -m specflow resume work/live-todo --stop-after red
python -m specflow status work/live-todo
```

此时检查测试日志：新功能应因未实现而出现断言失败，不能只看到导入错误或测试程序无法启动。继续执行：

```powershell
python -m specflow resume work/live-todo
python -m specflow report work/live-todo
```

一次真实成功运行至少应具备下列证据：

| 证据 | 需要证明的内容 |
| --- | --- |
| 运行模式与执行器记录 | 实际调用 Codex，而不是 fixture |
| 规格、计划与审批记录 | 实现依据可查看，确认对应当前产物 |
| 新增功能测试和红灯日志 | 先验证缺失行为，且测试真实执行 |
| 实现后的测试日志 | 原有行为、新增测试和独立验收通过 |
| 最终代码差异 | 变更对应状态筛选需求，测试未被实现角色篡改 |
| 状态与诊断记录 | 阶段完成有依据，失败或重试没有被隐藏 |

若角色超时、额度不足、认证失败或生成结果不合格，保留该次记录并报告失败。它们不应被改写为离线结果后仍称作一次真实成功运行。

## 常见处理

| 现象 | 下一步 |
| --- | --- |
| `doctor` 显示未安装 Codex | 先完成 CLI 安装，使可执行程序可发现，再检查 |
| 显示未登录或认证错误 | 自行运行 `codex login`，完成交互后再次检查 |
| 停在 `awaiting_approval` | 查看规格和计划，确认后执行 `approve`，再 `resume` |
| 手动修改后审批失效 | 查看当前状态与产物，创建新任务重新规划与审批 |
| 中断后留下未完成阶段 | 用 `status` 查看，再用 `resume` 从检查点继续 |
| 流程已经 `failed` | 查看报告与诊断；不要把重复执行当作无限自动修复 |
| 测试过程报导入错误 | 修复运行环境或产物问题；不能将其作为合格红灯 |

仅运行可信样例。测试子进程使用本机用户权限；本项目的目录副本和文件检查不提供恶意代码隔离。

## 代码测试

```powershell
python -m unittest discover -s tests -v
```

这条命令验证项目自身测试。它与上述完整模型运行互为补充：自身测试通过，不代表真实模型验收通过；一次模型成功，也不能替代工作流的回归测试。
