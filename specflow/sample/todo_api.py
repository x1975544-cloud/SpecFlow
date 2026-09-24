"""Small WSGI project used as the starting point for the SpecFlow demo."""
import json
from wsgiref.simple_server import make_server


TASKS = [
    {'id': 1, 'title': 'Read the specification', 'status': 'pending'},
    {'id': 2, 'title': 'Write the baseline test', 'status': 'done'},
    {'id': 3, 'title': 'Review the implementation', 'status': 'pending'},
]


def json_response(start_response, status, payload):
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    start_response(status, [
        ('Content-Type', 'application/json; charset=utf-8'),
        ('Content-Length', str(len(body))),
    ])
    return [body]


def application(environ, start_response):
    """Return tasks; query filtering is the feature the agent must implement."""
    if environ.get('PATH_INFO', '/') != '/tasks':
        return json_response(start_response, '404 Not Found', {'error': 'not found'})
    if environ.get('REQUEST_METHOD', 'GET') != 'GET':
        return json_response(start_response, '405 Method Not Allowed', {'error': 'method not allowed'})
    return json_response(start_response, '200 OK', TASKS)


if __name__ == '__main__':
    with make_server('127.0.0.1', 8000, application) as server:
        print('Todo API listening on http://127.0.0.1:8000/tasks', flush=True)
        server.serve_forever()
