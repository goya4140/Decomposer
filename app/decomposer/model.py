"""Vision API transport. Credentials are read from the process environment only."""
from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import time
import urllib.error
import urllib.request

from .common import write_json
from .schemas import omit_null_fields


class ModelRequestError(RuntimeError):
    pass


class ModelExecutionBlocked(RuntimeError):
    pass


def _redact(value: str, secret: str) -> str:
    return value.replace(secret, '[redacted]') if secret else value


def invoke_json(stage, prompt, payload, schema, image, config, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    model = config['model']
    key = os.environ.get('DECOMPOSER_API_KEY', '')
    if not key:
        raise ModelRequestError('DECOMPOSER_API_KEY is required')
    text = prompt + '\nUse null for optional fields that do not apply.\nINPUT:\n' + json.dumps(payload, ensure_ascii=False)
    write_json(directory / 'input.json', payload)
    write_json(directory / 'schema.json', schema)
    (directory / 'prompt.txt').write_text(text)
    mode = model.get('response_mode', 'json_schema')
    body = {
        'model': model['name'],
        'messages': [
            {'role': 'system', 'content': 'Use only the supplied image and prompt. Use no tools. Return a JSON object matching this schema exactly: ' + json.dumps(schema, ensure_ascii=False)},
            {'role': 'user', 'content': [
                {'type': 'text', 'text': text},
                {'type': 'image_url', 'image_url': {
                    'url': 'data:' + (mimetypes.guess_type(str(image))[0] or 'image/png') + ';base64,' + base64.b64encode(Path(image).read_bytes()).decode(),
                    'detail': model.get('image_detail', 'high'),
                }},
            ]},
        ],
    }
    if mode == 'json_schema':
        body['response_format'] = {'type': 'json_schema', 'json_schema': {'name': 'decomposer_' + stage, 'strict': True, 'schema': schema}}
    elif mode == 'json_object':
        body['response_format'] = {'type': 'json_object'}
    elif mode != 'prompt_only':
        raise ModelRequestError('Unsupported response mode')
    if model.get('effort'):
        body['reasoning_effort'] = model['effort']
    if model.get('max_completion_tokens'):
        body['max_completion_tokens'] = model['max_completion_tokens']
    url = model['base_url'].rstrip('/') + '/chat/completions'
    started = time.monotonic()
    metadata = {'stage': stage, 'backend': 'vision-api', 'model_name': model['name'], 'fallback_used': False}
    try:
        request = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
            'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json',
        }, method='POST')
        # Do not follow redirects with credentials to another host.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        opener = urllib.request.build_opener(NoRedirect)
        with opener.open(request, timeout=model.get('timeout_seconds', 900)) as response:
            result = json.loads(response.read())
        choice = result['choices'][0]
        content = choice['message'].get('content')
        if choice.get('finish_reason') in {'length', 'content_filter'}:
            raise ModelRequestError('Model response stopped: ' + choice['finish_reason'])
        if isinstance(content, list):
            content = ''.join(item.get('text', '') for item in content if isinstance(item, dict))
        if not content or not content.strip():
            raise ModelRequestError('Model returned empty content')
        raw = content.strip()
        if raw.startswith('```') and raw.endswith('```'):
            raw = '\n'.join(raw.splitlines()[1:-1])
        proposal = json.loads(raw)
        if not isinstance(proposal, dict):
            raise ModelRequestError('Model must return a JSON object')
        # Validate the actual provider output, including prompt-only responses.
        import jsonschema
        jsonschema.validate(proposal, schema)
        (directory / 'response.txt').write_text(json.dumps(proposal, ensure_ascii=False))
        metadata.update(status='complete', usage=result.get('usage'), finish_reason=choice.get('finish_reason'))
        return omit_null_fields(proposal), metadata
    except urllib.error.HTTPError as exc:
        # Error bodies may echo request data or credentials. Retain only status.
        metadata.update(status='request_failed', error=f'Vision API HTTP {exc.code}')
        raise ModelExecutionBlocked(metadata['error']) from None
    except Exception as exc:
        metadata.update(status='request_failed', error=_redact(f'{type(exc).__name__}: {exc}', key))
        raise ModelRequestError(metadata['error']) from None
    finally:
        metadata['seconds'] = round(time.monotonic() - started, 3)
        write_json(directory / 'metadata.json', metadata)


def fixture_or_model(stage, prompt, payload, schema, image, config, directory, fixture_dir):
    """Reuse only completed calls with exactly matching request identities."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    identity = {
        'model': config.get('model', {}), 'stage': stage,
        'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
        'image_sha256': hashlib.sha256(Path(image).read_bytes()).hexdigest(),
        'input': payload, 'schema': schema,
    }
    ip, mp, rp = (directory / n for n in ['call-identity.json', 'metadata.json', 'response.txt'])
    if ip.exists():
        if json.loads(ip.read_text()) != identity:
            raise ModelRequestError('Existing call identity differs; use a fresh output directory')
        if mp.exists() and rp.exists():
            metadata = json.loads(mp.read_text())
            if metadata.get('status') == 'complete' and not metadata.get('fallback_used'):
                return omit_null_fields(json.loads(rp.read_text())), metadata
    write_json(ip, identity)
    return invoke_json(stage, prompt, payload, schema, image, config, directory)
