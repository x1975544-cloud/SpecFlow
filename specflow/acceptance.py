"""Independent feature acceptance, kept outside the agent's writable project.

Usage: python /absolute/path/to/acceptance.py /path/to/workspace
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from wsgiref.util import setup_testing_defaults


EXPECTED_TASKS = [
    {'id': 1, 'title': 'Read the specification', 'status': 'pending'},
    {'id': 2, 'title': 'Write the baseline test', 'status': 'done'},
    {'id': 3, 'title': 'Review the implementation', 'status': 'pending'},
]


class FeatureAcceptance(unittest.TestCase):
    workspace = None

    @classmethod
    def setUpClass(cls):
        sys.dont_write_bytecode = True
        source = cls.workspace / 'todo_api.py'
        sys.path.insert(0, str(cls.workspace))
        spec = importlib.util.spec_from_file_location('specflow_target_todo_api', source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.api = module

    def request(self, query=''):
        environ = {}
        setup_testing_defaults(environ)
        environ.update(PATH_INFO='/tasks', REQUEST_METHOD='GET', QUERY_STRING=query)
        response = {}

        def start_response(status, headers, exc_info=None):
            response['status'] = int(status.split(' ', 1)[0])
            response['headers'] = dict(headers)

        iterable = self.api.application(environ, start_response)
        try:
            body = b''.join(iterable)
        finally:
            if hasattr(iterable, 'close'):
                iterable.close()
        self.assertTrue(response['headers'].get('Content-Type', '').startswith('application/json'))
        return response['status'], json.loads(body)

    def test_no_status_returns_all_tasks(self):
        status, tasks = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(tasks, EXPECTED_TASKS)

    def test_pending_returns_only_pending_tasks(self):
        status, tasks = self.request('status=pending')
        self.assertEqual(status, 200)
        self.assertEqual(tasks, [EXPECTED_TASKS[0], EXPECTED_TASKS[2]])
        self.assertEqual(self.request(), (200, EXPECTED_TASKS))

    def test_done_returns_only_done_tasks(self):
        status, tasks = self.request('status=done')
        self.assertEqual(status, 200)
        self.assertEqual(tasks, [EXPECTED_TASKS[1]])
        self.assertEqual(self.request(), (200, EXPECTED_TASKS))

    def test_unknown_status_returns_400(self):
        status, error = self.request('status=archived')
        self.assertEqual(status, 400)
        self.assertIsInstance(error, dict)
        self.assertIn('error', error)

    def test_empty_status_returns_400(self):
        status, error = self.request('status=')
        self.assertEqual(status, 400)
        self.assertIsInstance(error, dict)
        self.assertIn('error', error)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workspace', type=Path)
    args = parser.parse_args(argv)
    FeatureAcceptance.workspace = args.workspace.resolve()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(FeatureAcceptance)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
