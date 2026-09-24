"""Existing behavior: these tests are immutable during feature development."""
import json
import unittest
from wsgiref.util import setup_testing_defaults

from todo_api import application


def request(path='/tasks', method='GET', query=''):
    environ = {}
    setup_testing_defaults(environ)
    environ.update(PATH_INFO=path, REQUEST_METHOD=method, QUERY_STRING=query)
    response = {}

    def start_response(status, headers, exc_info=None):
        response['status'] = int(status.split(' ', 1)[0])
        response['headers'] = dict(headers)

    iterable = application(environ, start_response)
    try:
        body = b''.join(iterable)
    finally:
        if hasattr(iterable, 'close'):
            iterable.close()
    response['body'] = json.loads(body)
    return response


class BaselineTests(unittest.TestCase):
    def test_get_tasks_returns_all_original_tasks(self):
        response = request()
        self.assertEqual(response['status'], 200)
        self.assertTrue(response['headers']['Content-Type'].startswith('application/json'))
        self.assertEqual(response['body'], [
            {'id': 1, 'title': 'Read the specification', 'status': 'pending'},
            {'id': 2, 'title': 'Write the baseline test', 'status': 'done'},
            {'id': 3, 'title': 'Review the implementation', 'status': 'pending'},
        ])

    def test_unknown_path_returns_404(self):
        self.assertEqual(request('/missing')['status'], 404)

    def test_post_is_not_supported(self):
        self.assertEqual(request(method='POST')['status'], 405)


if __name__ == '__main__':
    unittest.main()
