"""Real OCR, optimized pipeline, Node compiler and LibreOffice; mock vision API."""
import base64
import io
import json
import os
from pathlib import Path
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont
import pytest

from decomposer.pptx import inspect_pptx
from decomposer.settings import load_config
from service.app import create_app


def wire(schema, value):
    """Fill logical optionals with null, matching the structured-output wire contract."""
    if value is None:
        return None
    if 'anyOf' in schema:
        candidates = [s for s in schema['anyOf'] if s.get('type') != 'null']
        if isinstance(value, dict):
            candidates = [s for s in candidates if all(value[k] in v['enum'] for k, v in s.get('properties', {}).items() if k in value and 'enum' in v)]
        return wire(candidates[0], value)
    if schema.get('type') == 'object':
        return {k: wire(v, value.get(k)) for k, v in schema['properties'].items()}
    if schema.get('type') == 'array':
        return [wire(schema['items'], v) for v in value]
    return value


@pytest.mark.skipif(any(shutil.which(x) is None for x in ['node', 'soffice', 'pdftoppm', 'tesseract']), reason='Full rendering runtime required')
def test_upload_through_real_conversion_and_download(tmp_path, monkeypatch):
    image = Image.new('RGB', (320, 160), 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((30, 40, 110, 120), fill='#DBEAFE', outline='#2563EB', width=2)
    draw.ellipse((210, 40, 290, 120), fill='#DCFCE7', outline='#16A34A', width=2)
    draw.text((130, 65), 'Hello', font=ImageFont.load_default(size=24), fill='#111111')
    source = io.BytesIO(); image.save(source, format='PNG')
    rows = [('box', 'rect', [30, 40, 80, 80], '#DBEAFE', '#2563EB'), ('circle', 'ellipse', [210, 40, 80, 80], '#DCFCE7', '#16A34A')]
    stages = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            schema = body['response_format']['json_schema']['schema']
            stage = body['response_format']['json_schema']['name'].removeprefix('decomposer_')
            stages.append(stage)
            if stage == 'recognition':
                value = {'background': '#FFFFFF', 'objects': [
                    {'id': owner, 'category': 'shape', 'bbox': bbox, 'text': '', 'geometry_hint': kind, 'style_hint': {'fill': fill, 'stroke': stroke, 'stroke_width': 2}, 'confidence': 1}
                    for owner, kind, bbox, fill, stroke in rows]}
                payload = json.loads(body['messages'][1]['content'][0]['text'].split('\nINPUT:\n', 1)[1])
                candidates = [c['id'] for c in payload['evidence']['candidates'] if c.get('text') == 'Hello']
                value['objects'].append({'id': 'label', 'category': 'text', 'bbox': [130, 65, 65, 30], 'text': 'Hello', 'confidence': 1, 'candidate_ids': candidates, 'style_hint': {'color': '#111111', 'font_size': 24, 'font_family': 'DejaVu Sans'}})
            elif stage == 'representation':
                value = {'styles': [{'id': owner, 'value': {'fill': fill, 'stroke': stroke, 'stroke_width': 2}} for owner, kind, bbox, fill, stroke in rows],
                         'plans': [{'label_id': owner, 'builder': kind, 'style_id': owner} for owner, kind, bbox, fill, stroke in rows]}
                value['styles'].append({'id': 'text', 'value': {'color': '#111111', 'font_size': 24, 'font_family': 'DejaVu Sans'}})
                value['plans'].append({'label_id': 'label', 'builder': 'text', 'style_id': 'text'})
            elif stage == 'refinement':
                value = {'acceptable': True, 'owner_stage': 'none', 'mechanism': 'smoke-complete', 'summary': 'Synthetic geometry is acceptable',
                         'affected_label_ids': [], 'affected_primitive_ids': [], 'confidence': 1, 'operations': []}
            else:
                raise AssertionError(stage)
            response = {'choices': [{'message': {'content': json.dumps(wire(schema, value))}, 'finish_reason': 'stop'}], 'usage': {'prompt_tokens': 1, 'completion_tokens': 1}}
            self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(json.dumps(response).encode())
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    monkeypatch.setenv('DECOMPOSER_BASE_URL', f'http://127.0.0.1:{server.server_port}/v1')
    monkeypatch.setenv('DECOMPOSER_API_KEY', 'smoke-secret')
    monkeypatch.setenv('DECOMPOSER_MODEL', 'mock-vision')
    monkeypatch.setenv('DECOMPOSER_REFINEMENT_ROUNDS', '1')
    monkeypatch.delenv('DECOMPOSER_ACCESS_TOKEN', raising=False)
    try:
        import time
        with TestClient(create_app(jobs_root=tmp_path)) as client:
            response = client.post('/api/jobs', files={'file': ('example.png', source.getvalue(), 'image/png')})
            assert response.status_code == 202, response.text
            jid = response.json()['id']
            for _ in range(1200):
                record = client.get(f'/api/jobs/{jid}').json()
                if record['state'] in {'complete', 'failed'}: break
                time.sleep(.1)
            assert record['state'] == 'complete', record
            result = client.get(f'/api/jobs/{jid}/pptx')
            assert result.status_code == 200 and result.content[:2] == b'PK'
            preview = client.get(f'/api/jobs/{jid}/preview')
            assert preview.status_code == 200
            assert Image.open(io.BytesIO(preview.content)).size == (320, 160)
            run = tmp_path / 'jobs' / jid / 'run'
            structure = inspect_pptx(run / 'output/editable.pptx')
            assert structure['text_run_count'] >= 1
            assert structure['shape_count'] >= 3 and not structure['is_single_screenshot_like']
            assert json.loads((run / 'observations/candidates.json').read_text())['sources']['ocr']['status'] == 'ready'
            assert json.loads((run / 'preprocessing-provenance.json').read_text())['mode'] == 'fresh'
            assert stages[:2] == ['recognition', 'representation']
            assert 'refinement' in stages
            for path in run.rglob('*.json'):
                assert 'smoke-secret' not in path.read_text()
    finally:
        server.shutdown(); thread.join(); server.server_close()
