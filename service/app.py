"""One-worker image-to-PPTX service with persistent job status."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from functools import partial
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import threading
import uuid

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError

from decomposer.common import write_json
from decomposer.engineering import execute
from decomposer.settings import ROOT, load_config

Image.MAX_IMAGE_PIXELS = 25_000_000
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_FORMATS = {'PNG', 'JPEG', 'WEBP', 'TIFF', 'BMP'}


def create_app(*, jobs_root=None, runner=None, config_loader=None):
    jobs = Path(jobs_root or os.environ.get('DECOMPOSER_DATA_DIR', str(ROOT / 'data'))) / 'jobs'
    jobs.mkdir(parents=True, exist_ok=True)
    gate = threading.BoundedSemaphore(8)
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='decomposer')
    runner = runner or execute
    config_loader = config_loader or load_config

    @asynccontextmanager
    async def lifespan(app):
        # Environment and dependencies are validated before accepting jobs.
        config_loader()
        for path in jobs.glob('*/job.json'):
            try:
                record = json.loads(path.read_text())
                if record.get('state') in {'queued', 'running'}:
                    record.update(state='failed', error='Service restarted before this job completed. Submit the image again.')
                    write_json(path, record)
            except (OSError, ValueError):
                continue
        yield
        executor.shutdown(wait=True, cancel_futures=True)

    app = FastAPI(title='Decomposer', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    def authorize(request: Request):
        token = os.environ.get('DECOMPOSER_ACCESS_TOKEN', '')
        supplied = request.headers.get('authorization', '').removeprefix('Bearer ')
        if token and not hmac.compare_digest(token, supplied):
            raise HTTPException(401, 'Access token required')

    def job_path(job_id):
        if not re.fullmatch(r'[0-9a-f]{32}', job_id):
            raise HTTPException(404, 'Job not found')
        path = jobs / job_id
        if not (path / 'job.json').is_file():
            raise HTTPException(404, 'Job not found')
        return path

    def work(path, image, config):
        record = {'id': path.name, 'state': 'running'}
        write_json(path / 'job.json', record)
        try:
            result = runner({'sample_id': path.name, 'input': str(image)}, path / 'run', config, ROOT / 'knowledge')
            if result.get('status') != 'complete':
                raise RuntimeError(result.get('error') or 'Conversion failed')
            if not (path / 'run/output/editable.pptx').is_file():
                raise RuntimeError('Conversion did not produce a PPTX')
            record.update(state='complete', validation_passed=result.get('validation_passed'), seconds=result.get('seconds'))
            if result.get('validation_passed') is False:
                record['warning'] = 'PPTX generated; visual similarity is below the configured threshold. Please review the preview.'
        except Exception as exc:
            secret = os.environ.get('DECOMPOSER_API_KEY', '')
            error = str(exc)
            if secret:
                error = error.replace(secret, '[redacted]')
            record.update(state='failed', error=error[:1500])
        finally:
            write_json(path / 'job.json', record)
            gate.release()

    @app.get('/')
    def index():
        return FileResponse(ROOT / 'service/index.html', media_type='text/html')

    @app.get('/healthz')
    def health():
        return {'status': 'ok'}

    @app.post('/api/jobs', status_code=202, dependencies=[Depends(authorize)])
    async def submit(file: UploadFile = File(...)):
        config = config_loader()
        if not gate.acquire(blocking=False):
            raise HTTPException(429, 'Conversion queue is full; try again later')
        path = jobs / uuid.uuid4().hex
        path.mkdir()
        image = path / 'source'
        queued = False
        try:
            total = 0
            with image.open('wb') as target:
                while chunk := await file.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_UPLOAD_BYTES:
                        raise HTTPException(413, 'Image must be 20 MiB or smaller')
                    target.write(chunk)
            try:
                with Image.open(image) as source:
                    if source.format not in ALLOWED_FORMATS:
                        raise ValueError('Unsupported image format')
                    if source.width * source.height > Image.MAX_IMAGE_PIXELS:
                        raise ValueError('Image must have at most 25 million pixels')
                    source.verify()
            except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
                raise HTTPException(400, 'Upload a valid PNG, JPEG, WebP, TIFF or BMP image (up to 25 million pixels)') from exc
            write_json(path / 'job.json', {'id': path.name, 'state': 'queued'})
            executor.submit(work, path, image, config)
            queued = True
            return {'id': path.name, 'state': 'queued'}
        finally:
            await file.close()
            if not queued:
                gate.release()
                shutil.rmtree(path, ignore_errors=True)

    @app.get('/api/jobs/{job_id}', dependencies=[Depends(authorize)])
    def status(job_id: str):
        path = job_path(job_id)
        record = json.loads((path / 'job.json').read_text())
        status_path = path / 'run/status.json'
        if record['state'] == 'running' and status_path.is_file():
            record['phase'] = json.loads(status_path.read_text()).get('phase')
        return record

    @app.get('/api/jobs/{job_id}/{artifact}', dependencies=[Depends(authorize)])
    def download(job_id: str, artifact: str):
        if artifact not in {'pptx', 'preview'}:
            raise HTTPException(404, 'Artifact not found')
        path = job_path(job_id)
        record = json.loads((path / 'job.json').read_text())
        if record['state'] != 'complete':
            raise HTTPException(409, 'Job has not completed successfully')
        target = path / 'run/output' / ('editable.pptx' if artifact == 'pptx' else 'preview.png')
        if not target.is_file():
            raise HTTPException(404, 'Artifact not found')
        return FileResponse(target, filename='decomposer.pptx' if artifact == 'pptx' else 'preview.png')

    return app


app = create_app()
