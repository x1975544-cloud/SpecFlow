# SpecFlow（规流）

用一个可运行的 Python 示例，学习规格驱动的 Agent 研发流程：**需求 → 规格与计划 → 人工确认 → 写测试 → 验证红灯 → 修改代码 → 验证绿灯 → 留存证据**。

首版面向个人学习和作品展示，提供命令行、可恢复状态和运行报告。验收范围是内置的 `todo-status-v1`：为待办 API 增加按 `pending` / `done` 状态筛选，保持无参数查询行为，并对未知状态返回 `400`。它尚不是通用仓库开发平台。

## 先运行离线演示

需要 Python 3.12 或更高版本。在本目录运行，无需安装第三方 Python 运行依赖：

```powershell
python -m specflow --help
python -m specflow demo --scenario success --destination work/demo-success
python -m specflow status work/demo-success
python -m specflow report work/demo-success
```

每次演示使用一个新的目标目录。`demo` 使用明确标注的 **scripted fixture**：固定脚本模拟各角色产生的文件，测试由真实 Python 子进程执行。它用于验证编排、门禁和报告，**不代表模型已经完成开发任务**。

另外两个演示场景：

```powershell
python -m specflow demo --scenario failure --destination work/demo-failure
python -m specflow demo --scenario resume --destination work/demo-resume
```

失败演示用于验证测试失败会阻止完成，预期命令以非零状态结束。恢复演示用于展示已保存的阶段如何继续；它仍然属于离线脚本演示。

## 使用真实 Codex 执行

本机需要可用的 Codex CLI，以及你自行完成的账户登录。平台复用已有配置，不读取或展示登录凭据，也不修改全局模型配置。

```powershell
python -m specflow doctor
codex login
python -m specflow doctor
```

确认检查结果显示已安装、已登录后，建立一次真实运行：

```powershell
python -m specflow init work/live-todo
python -m specflow run work/live-todo
python -m specflow status work/live-todo
```

`run` 调用规划角色，生成规格与计划，然后停在 `awaiting_approval`。查看运行目录中的 `artifacts/spec.json` 和 `artifacts/plan.md` 后，再执行：

```powershell
python -m specflow approve work/live-todo
python -m specflow resume work/live-todo
python -m specflow report work/live-todo
```

`approve` 记录对当前规格、计划及工作副本的确认；变更后的内容不能沿用旧审批。规划、测试、实现是分开的角色调用，复用同一 Codex 执行适配器。测试验证由程序实际执行。

`report` 在运行目录根部生成 `report.md`、`report.html` 和 `diff.patch`。例如上面的真实运行报告位于 `work/live-todo/report.html`。常规阶段运行不会自动刷新报告；需要查看最新报告时重新执行 `report`。报告中的模式为 `live` 或 `offline_scripted`。

默认每次角色调用最长 300 秒，失败最多自动修复两轮。`run` 和 `resume` 支持 `--model` 与 `--timeout`；模型选择需要符合你的账户权限。调用会使用账户额度，记录的用量以执行器实际返回为准，本项目不提供精确金额预算控制。

**真实模型验收状态：本交付尚未验证。** 当前验证覆盖离线流程和执行器测试替身；只有实际获得角色调用记录、红灯与绿灯测试证据、最终代码差异后，才能把相应任务称为真实模型完成。登录状态检查通过也不能替代一次完整运行。

## 中断与继续

需要演示一个可控暂停时，在审批后运行：

```powershell
python -m specflow resume work/live-todo --stop-after red
python -m specflow status work/live-todo
python -m specflow resume work/live-todo
```

也可以在运行时按 `Ctrl+C`，之后使用 `resume`。恢复以最后持久化的阶段为准；未提交的阶段可能重新调用模型。恢复不是对模型调用中间推理的续传，也不保证重复调用免费或产生相同结果。

## 本地验证与阅读

```powershell
python -m unittest discover -s tests -v
```

测试覆盖的实际情况应以本次执行输出为准。离线测试使用执行器替身，不要求账户登录。

- [演示步骤与验收证据](docs/DEMO.md)：三个离线场景、真实运行，以及如何说明作品的验证范围。
- [架构与设计取舍](docs/ARCHITECTURE.md)：角色职责、状态、执行门禁、持久化和扩展位置。
- [首版构建契约](docs/BUILD_CONTRACT.md)：本次约定的范围与模块接口。

## 首版边界

只运行可信的内置示例或兼容 `todo-status-v1` 的可信副本。工作副本、阶段试运行副本和文件差异检查用于避免正常执行中的误改；**测试子进程拥有本机用户权限，这不是操作系统级隔离，也不用于运行恶意仓库或恶意测试代码**。Codex 工具调用另受其自身沙盒规则约束。

规格、状态、审计和独立验收逻辑放在角色的阶段工作目录之外。平台不自动提交、推送或部署。首版未接入企业 SSO、文档平台、CI/CD 或 Staging RPC；也不声称具备任意外部操作回滚、完全可复现执行或已经量化的效率收益。
