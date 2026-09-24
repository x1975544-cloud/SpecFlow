"""Deterministic test-double for OFFLINE demos. This is not an AI model."""


class ScriptedAdapter:
    mode = "offline_scripted"

    def __init__(self, scenario="success"):
        self.scenario = scenario

    def run(self, *, role, prompt, workspace, artifact_dir):
        if role == "test_writer":
            (workspace / "tests/test_feature.py").write_text('''import json
import unittest
from todo_api import application

class FeatureTests(unittest.TestCase):
    def request(self, query):
        response = {}
        def start(status, headers):
            response['status'] = int(status.split()[0])
        body = b''.join(application({'PATH_INFO': '/tasks', 'REQUEST_METHOD': 'GET', 'QUERY_STRING': query}, start))
        return response['status'], json.loads(body)

    def test_filters(self):
        for value, ids in [('pending', [1, 3]), ('done', [2])]:
            with self.subTest(status=value):
                status, tasks = self.request('status=' + value)
                self.assertEqual(status, 200)
                self.assertEqual([task['id'] for task in tasks], ids)

    def test_invalid(self):
        for value in ['', 'archived']:
            with self.subTest(status=value):
                self.assertEqual(self.request('status=' + value)[0], 400)
''', encoding="utf-8")
        elif role == "executor" and self.scenario != "failure":
            source = workspace / "todo_api.py"
            original = "    return json_response(start_response, '200 OK', TASKS)"
            replacement = '''    from urllib.parse import parse_qs
    query = parse_qs(environ.get('QUERY_STRING', ''), keep_blank_values=True)
    if 'status' in query:
        status = query['status'][0]
        if status not in ('pending', 'done'):
            return json_response(start_response, '400 Bad Request', {'error': 'invalid status'})
        return json_response(start_response, '200 OK', [task for task in TASKS if task['status'] == status])
    return json_response(start_response, '200 OK', TASKS)'''
            source.write_text(source.read_text(encoding="utf-8").replace(original, replacement), encoding="utf-8")
        elif role not in {"planner", "executor"}:
            raise RuntimeError(f"unknown scripted role: {role}")
        return {"summary": "为 GET /tasks 增加状态筛选，并保留已有接口行为。",
                "acceptance_criteria": ["pending 只返回 1、3", "done 只返回 2", "无 status 返回全部", "未知或空 status 返回 400"],
                "tasks": ["新增独立功能测试并观察断言失败", "实现查询参数校验和筛选", "运行基线、功能测试和独立验收"],
                "usage": {}, "scripted": True}
