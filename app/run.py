#!/usr/bin/env python3
"""Convert one scientific figure with the same runtime used by the web service."""
import argparse
import json
from pathlib import Path
import sys
import uuid

from decomposer.engineering import execute
from decomposer.settings import ROOT, load_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--out', type=Path, default=None)
    args = parser.parse_args()
    try:
        config = load_config()
        image = args.input.resolve()
        if not image.is_file():
            raise ValueError('Input image does not exist')
        out = (args.out or ROOT / 'data/jobs' / uuid.uuid4().hex).resolve()
        if out.exists() and any(out.iterdir()):
            raise ValueError('Output directory must be empty')
        result = execute({'sample_id': out.name, 'input': str(image)}, out, config, ROOT / 'knowledge')
    except (ValueError, OSError) as exc:
        parser.exit(2, str(exc) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result['status'] != 'complete':
        sys.exit(1)
    print('PPTX: ' + str(out / 'output/editable.pptx'))


if __name__ == '__main__':
    main()
