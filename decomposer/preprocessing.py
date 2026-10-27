"""Build fresh evidence on any machine, without historical run bundles."""
from pathlib import Path
import shutil

from PIL import Image, ImageOps

from .common import sha256, write_json
from .detectors import collect
from .evidence import materialize


def prepare(sample: dict, out: Path, config: dict) -> tuple[dict, dict]:
    image = out / 'input-normalized.png'
    with Image.open(sample['input']) as source:
        source = ImageOps.exif_transpose(source).convert('RGBA')
        normalized = Image.alpha_composite(Image.new('RGBA', source.size, 'white'), source).convert('RGB')
        normalized.save(image)
    canvas = normalized.size
    sample.update(width=canvas[0], height=canvas[1], sha256=sha256(sample['input']))
    (out / 'input').mkdir(exist_ok=True)
    shutil.copy2(image, out / 'input/normalized.png')
    write_json(out / 'input/input.json', {
        'source': str(Path(sample['input']).resolve()),
        'source_sha256': sample['sha256'], 'canvas': list(canvas),
    })
    candidates = collect(image, canvas, config, out / 'observations')
    for name, detector in config.get('detectors', {}).items():
        if detector.get('command') and candidates['sources'].get(name, {}).get('status') != 'ready':
            raise RuntimeError(f'{name} preprocessing failed; inspect observations/{name}.stderr.log')
    evidence = materialize(image, candidates, canvas, config, out / 'observations')
    write_json(out / 'preprocessing-provenance.json', {
        'mode': 'fresh', 'source_sha256': sample['sha256'],
        'canvas': list(canvas), 'sources': candidates['sources'],
    })
    return candidates, evidence
