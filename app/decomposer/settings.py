"""Portable deployment configuration."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def load_config(*, check=True):
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env', override=False)
    config = json.loads((ROOT / 'configs/default.json').read_text())
    url = os.environ.get('DECOMPOSER_BASE_URL', '').strip().rstrip('/')
    model = os.environ.get('DECOMPOSER_MODEL', '').strip()
    if check:
        missing = [name for name in ['DECOMPOSER_API_KEY', 'DECOMPOSER_BASE_URL', 'DECOMPOSER_MODEL'] if not os.environ.get(name, '').strip()]
        if missing:
            raise ValueError('Configure .env: ' + ', '.join(missing))
        parsed = urlparse(url)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('DECOMPOSER_BASE_URL must be an HTTP(S) API base URL without credentials/query/fragment')
        if url.endswith('/chat/completions'):
            raise ValueError('Use the API base URL, e.g. https://provider.example/v1; omit /chat/completions')
        for command in ['node', 'soffice', 'pdftoppm', 'tesseract']:
            if not shutil.which(command):
                raise ValueError('Missing runtime dependency: ' + command + '; run deploy.sh or use Docker')
    config['model'].update(base_url=url, name=model,
        response_mode=os.environ.get('DECOMPOSER_RESPONSE_MODE', 'json_schema'),
        effort=os.environ.get('DECOMPOSER_REASONING_EFFORT', '').strip() or None,
        timeout_seconds=int(os.environ.get('DECOMPOSER_API_TIMEOUT', '900')))
    if config['model']['response_mode'] not in {'json_schema', 'json_object', 'prompt_only'}:
        raise ValueError('Invalid DECOMPOSER_RESPONSE_MODE')
    config['refinement']['max_rounds'] = int(os.environ.get('DECOMPOSER_REFINEMENT_ROUNDS', '1'))
    if not 0 <= config['refinement']['max_rounds'] <= 3:
        raise ValueError('DECOMPOSER_REFINEMENT_ROUNDS must be between 0 and 3')
    config['runtime'].update(node=shutil.which('node') or 'node', soffice=shutil.which('soffice'), pdftoppm=shutil.which('pdftoppm'))
    config['detectors']['ocr']['command'] = [sys.executable, str(ROOT / 'deploy/ocr.py')]
    return config
