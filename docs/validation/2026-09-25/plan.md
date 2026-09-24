# 技术方案与任务

已只读检查 todo_api.py 和 tests/test_baseline.py；现有 3 项测试全部通过，未修改文件。当前 GET /tasks 忽略查询参数。计划通过标准库解析 status，在保留现有行为的基础上增加筛选与校验。

1. 在 tests/test_feature.py 新增通过 application(environ, start_response) 调用的特性测试，覆盖 pending、done、未知值、空值、裸 status、JSON 响应、原始字段与顺序，以及连续筛选后再无参数请求的数据完整性。
2. 在新增测试文件中覆盖携带非法 status 时的 404、405 和路径检查优先级；保留现有基线测试不动。
3. 修改实现前运行 python -m unittest discover -s tests -v，确认筛选及非法值测试出现 AssertionError，且既有测试通过；排除导入或测试配置错误。此后冻结全部测试。
4. 仅修改 todo_api.py：在现有路径与方法检查之后，用 urllib.parse.parse_qs 并设置 keep_blank_values=True 解析 QUERY_STRING，区分参数缺失与空值，校验允许值。
5. 无 status 时继续返回 TASKS；合法 status 时通过列表推导生成筛选结果，不原地修改 TASKS；非法值通过现有 json_response 返回 400 和 error 对象，复用原有 JSON 编码及响应头。
6. 再次运行 python -m unittest discover -s tests -v，确认全部测试通过；检查变更范围，确保基线测试、实现阶段的全部测试以及本地监听配置均未被修改。
