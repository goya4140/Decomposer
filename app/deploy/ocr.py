#!/usr/bin/env python3
"""Local OCR adapter: Tesseract TSV to the detector JSON contract."""
import base64
import csv
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    request = json.load(sys.stdin)
    with tempfile.TemporaryDirectory(prefix='decomposer-ocr-') as temp:
        image = Path(temp) / 'input.png'
        image.write_bytes(base64.b64decode(request['image'], validate=True))
        command = ['tesseract', str(image), 'stdout', '-l', os.environ.get('DECOMPOSER_OCR_LANG', 'eng'), '--psm', '11', 'tsv']
        process = subprocess.run(command, capture_output=True, text=True, timeout=120, check=True)
    lines = {}
    for row in csv.DictReader(io.StringIO(process.stdout), delimiter='\t', quoting=csv.QUOTE_NONE):
        text = (row.get('text') or '').strip()
        if not text or float(row['conf']) < 0:
            continue
        key = tuple(row[k] for k in ['page_num', 'block_num', 'par_num', 'line_num'])
        lines.setdefault(key, []).append(row)
    items = []
    for words in lines.values():
        left = min(int(w['left']) for w in words)
        top = min(int(w['top']) for w in words)
        right = max(int(w['left']) + int(w['width']) for w in words)
        bottom = max(int(w['top']) + int(w['height']) for w in words)
        items.append({'bbox': [left, top, right-left, bottom-top], 'text': ' '.join(w['text'] for w in words),
                      'confidence': sum(float(w['conf']) for w in words) / (100 * len(words))})
    print(json.dumps({'schema_version': 'decomposer.ocr-response.v2', 'items': items}))


if __name__ == '__main__':
    main()
