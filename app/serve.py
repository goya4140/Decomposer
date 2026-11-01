#!/usr/bin/env python3
import os
from decomposer.settings import load_config

if __name__ == '__main__':
    load_config()
    import uvicorn
    host = os.environ.get('DECOMPOSER_HOST', '127.0.0.1')
    if host not in {'127.0.0.1', 'localhost', '::1'} and not os.environ.get('DECOMPOSER_ACCESS_TOKEN') and os.environ.get('DECOMPOSER_CONTAINER_LOCAL_ONLY') != '1':
        raise SystemExit('Set DECOMPOSER_ACCESS_TOKEN before exposing the service beyond localhost')
    uvicorn.run('service.app:app', host=host, port=int(os.environ.get('DECOMPOSER_PORT', '7860')), workers=1)
