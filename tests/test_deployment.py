import io
import json
from pathlib import Path
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from decomposer import model
from decomposer.common import write_json
from decomposer.settings import load_config
from service.app import create_app


def image_bytes():
    out = io.BytesIO()
    Image.new('RGB', (32, 24), 'white').save(out, format='PNG')
    return out.getvalue()


@pytest.fixture
def provider():
    class Handler(BaseHTTPRequestHandler):
        request_body = None
        authorization = None
        content = {'ok': True}
        status_code = 200
        finish_reason = 'stop'

        def log_message(self, *args):
            pass

        def do_POST(self):
            type(self).request_body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            type(self).authorization = self.headers.get('Authorization')
            self.send_response(self.status_code)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'choices': [{'message': {'content': json.dumps(self.content)}, 'finish_reason': self.finish_reason}]}).encode())
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}/v1', Handler
    server.shutdown()
    thread.join()
    server.server_close()


def test_api_transport_schema_and_no_secret_on_disk(tmp_path, monkeypatch, provider):
    base_url, handler = provider
    monkeypatch.setenv('DECOMPOSER_API_KEY', 'test-secret-do-not-write')
    image = tmp_path / 'image.png'
    image.write_bytes(image_bytes())
    config = {'model': {'base_url': base_url, 'name': 'mock-vision', 'response_mode': 'json_schema'}}
    schema = {'type': 'object', 'properties': {'ok': {'type': 'boolean'}}, 'required': ['ok'], 'additionalProperties': False}
    args = ('recognition', 'Return JSON', {}, schema, image, config, tmp_path / 'call', None)
    assert model.fixture_or_model(*args)[0] == {'ok': True}
    assert handler.authorization == 'Bearer test-secret-do-not-write'
    assert handler.request_body['response_format']['type'] == 'json_schema'
    handler.status_code = 500
    # Exact local call reuse makes no additional network request.
    assert model.fixture_or_model(*args)[0] == {'ok': True}
    for p in tmp_path.rglob('*'):
        if p.is_file():
            assert b'test-secret-do-not-write' not in p.read_bytes()
    with pytest.raises(model.ModelRequestError, match='identity differs'):
        model.fixture_or_model('recognition', 'changed', {}, schema, image, config, tmp_path / 'call', None)


@pytest.mark.parametrize('status_code,content,finish_reason', [(401, {}, 'stop'), (200, {}, 'stop'), (200, {'ok': True}, 'length')])
def test_api_errors_fail_without_fallback(tmp_path, monkeypatch, provider, status_code, content, finish_reason):
    base_url, handler = provider
    handler.status_code, handler.content, handler.finish_reason = status_code, content, finish_reason
    monkeypatch.setenv('DECOMPOSER_API_KEY', 'secret')
    image = tmp_path / 'image.png'; image.write_bytes(image_bytes())
    schema = {'type': 'object', 'properties': {'ok': {'type': 'boolean'}}, 'required': ['ok']}
    with pytest.raises((model.ModelRequestError, model.ModelExecutionBlocked)):
        model.invoke_json('recognition', 'prompt', {}, schema, image, {'model': {'name': 'mock', 'base_url': base_url}}, tmp_path / 'call')
    md = json.loads((tmp_path / 'call/metadata.json').read_text())
    assert md['status'] == 'request_failed' and md['fallback_used'] is False


def test_upload_status_download_and_auth(tmp_path, monkeypatch):
    monkeypatch.setenv('DECOMPOSER_ACCESS_TOKEN', 'test-access')
    def runner(sample, path, config, seed):
        (path / 'output').mkdir(parents=True)
        (path / 'output/editable.pptx').write_bytes(b'PK-test-pptx')
        (path / 'output/preview.png').write_bytes(image_bytes())
        return {'status': 'complete', 'validation_passed': False, 'seconds': 0.1}
    app = create_app(jobs_root=tmp_path, runner=runner, config_loader=lambda: {})
    with TestClient(app) as client:
        assert client.get('/').status_code == 200
        assert client.get('/healthz').status_code == 200
        assert client.post('/api/jobs', files={'file': ('test.png', image_bytes(), 'image/png')}).status_code == 401
        headers = {'Authorization': 'Bearer test-access'}
        response = client.post('/api/jobs', files={'file': ('../../test.png', image_bytes(), 'image/png')}, headers=headers)
        assert response.status_code == 202
        jid = response.json()['id']
        for _ in range(100):
            record = client.get(f'/api/jobs/{jid}', headers=headers).json()
            if record['state'] == 'complete':
                break
            time.sleep(.01)
        assert record['state'] == 'complete' and record['warning']
        assert client.get(f'/api/jobs/{jid}/pptx', headers=headers).content == b'PK-test-pptx'
        assert client.get(f'/api/jobs/{jid}/preview', headers=headers).status_code == 200
        assert client.get(f'/api/jobs/{jid}/config.json', headers=headers).status_code == 404
        assert client.get('/api/jobs/not-a-job', headers=headers).status_code == 404
        invalid = client.post('/api/jobs', files={'file': ('bad.png', b'not an image', 'image/png')}, headers=headers)
        assert invalid.status_code == 400
    assert not (tmp_path / 'test.png').exists()


def test_restart_does_not_leave_jobs_running(tmp_path):
    p = tmp_path / 'jobs' / ('a' * 32)
    write_json(p / 'job.json', {'id': p.name, 'state': 'running'})
    with TestClient(create_app(jobs_root=tmp_path, config_loader=lambda: {})) as client:
        record = client.get('/api/jobs/' + p.name).json()
        assert record['state'] == 'failed' and 'restarted' in record['error']


def test_failed_job_does_not_offer_download(tmp_path):
    app = create_app(jobs_root=tmp_path, runner=lambda *a: {'status': 'failed', 'error': 'provider unavailable'}, config_loader=lambda: {})
    with TestClient(app) as client:
        jid = client.post('/api/jobs', files={'file': ('x.png', image_bytes(), 'image/png')}).json()['id']
        for _ in range(100):
            record = client.get('/api/jobs/' + jid).json()
            if record['state'] == 'failed': break
            time.sleep(.01)
        assert record['state'] == 'failed'
        assert client.get(f'/api/jobs/{jid}/pptx').status_code == 409
