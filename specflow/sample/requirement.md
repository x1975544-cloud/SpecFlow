# 待办 API：按状态筛选

为已有 Python 标准库 WSGI API 的 `GET /tasks` 增加可选的 `status` 查询参数。

验收要求：

1. `GET /tasks` 不带 `status` 参数时，HTTP 200，返回全部三个待办；保持原顺序、字段和数据。
2. `GET /tasks?status=pending` 返回 HTTP 200，仅包含 pending 待办，ID 顺序为 `[1, 3]`。
3. `GET /tasks?status=done` 返回 HTTP 200，仅包含 done 待办，ID 为 `[2]`。
4. `status` 仅接受 `pending` 和 `done`。其他值（包括空值）返回 HTTP 400 和含 `error` 字段的 JSON 对象。
5. 返回体使用 JSON。筛选后不修改原始 `TASKS`，后续无参数请求仍返回全部待办。
6. 已有路径和 HTTP 方法处理保持原有行为，全部既有测试继续通过。

接口为 `todo_api.application(environ, start_response)`；成功响应为任务对象组成的 JSON 数组，每项包含 `id`、`title`、`status`。

先在 `tests/test_feature.py` 等新增文件中编写特性测试，运行并确认出现 AssertionError；通过红灯后才修改 `todo_api.py`。不修改已有 `tests/test_baseline.py`，实现阶段不修改任何测试。

命令：`python -m unittest discover -s tests -v`。

可手动启动：`python todo_api.py`，仅监听 `127.0.0.1:8000`。
