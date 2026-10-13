# Decomposer

Decomposer converts a scientific figure into an editable, single-slide PowerPoint presentation. Vision models propose structured JSON for Recognition, Representation, and Layout. A deterministic compiler creates native PowerPoint shapes and text; bounded refinement and measured registration improve the rendered result.

This release contains the framework source, stage prompts, schemas, reference adapters, configuration templates, and synthetic tests. Research datasets, annotations, model weights, historical knowledge snapshots, benchmark outputs, and evaluation results are excluded. The knowledge engine remains available and starts empty. This release does not reproduce the historical benchmark or its learned knowledge snapshot.

## Architecture

```text
Source image + optional OCR/SAM candidates
  -> Evidence IR
  -> Recognition JSON: object identity, text, relationships
  -> Raster authorization: approved localized leaves only
  -> Representation JSON: component-local editable primitives
  -> Layout JSON: global placement, rotation, order
  -> Scene IR
  -> Deterministic PPTX compiler
  -> Render / validation / provenance
  -> Bounded refinement with acceptance and rollback
  -> Measured native text, shadow, fill, and style registration
  -> Final validation + deliverable manifest
```

See [architecture](docs/architecture.md), [adapter contracts](docs/adapters.md), and [release scope](docs/release-scope.md).

## Setup

Run from the repository root. Python 3.10+ and Node.js 18+ are required. Full visual validation also requires LibreOffice (`soffice`), Poppler (`pdftoppm`), and fonts appropriate for the source image.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
npm ci
```

Dependencies and detector/model services are installed separately. No third-party binaries or model weights are bundled.

## Offline smoke example

The example generates a small geometric input and stage proposals locally. It needs no API key, network access, research image, or historical run.

```bash
python examples/make_synthetic_example.py --out runs/synthetic-input
python run.py --input runs/synthetic-input/source.png \
  --config configs/base.json \
  --fixture-dir runs/synthetic-input/fixtures \
  --out runs/synthetic-smoke --no-render
```

This checks canonicalization, assembly, native PPTX compilation, structural validation, and provenance. `--no-render` skips visual validation, refinement, and measured registration. `structural_success` is not proof of visual fidelity. Remove `--no-render` to enable the renderer; the example includes a fixture that tells refinement to stop without a model call.

## Model-backed run

Copy `configs/base.json` to `config.local.json`. Set `runtime.node`, `runtime.soffice`, and `runtime.pdftoppm` to commands available on PATH or absolute executable paths. Configure detector commands if needed; OCR and SAM are disabled in the portable base configuration.

For the reference OpenAI-compatible adapter, supply credentials through environment variables and choose a vision model supported by your endpoint:

```bash
export MODEL_BASE_URL="https://your-provider.example/v1"
export MODEL_NAME="your-vision-model"
read -r -s MODEL_API_KEY
export MODEL_API_KEY
python run.py --input /absolute/path/to/figure.png \
  --config config.local.json \
  --model-profile configs/models/openai-compatible.example.json \
  --out runs/my-figure
```

The example profile requests `json_schema`; switch its `--response-mode` to `json_object` or `prompt_only` if required by your provider. Use a model that accepts images. The Codex transport is also included; replace the placeholder model in `configs/models/codex.example.json` with an available model. Its command-line flags must be supported by your installed Codex CLI.

On macOS with Swift and Apple Vision available, `configs/macos-ocr.json` supplies an OCR override. Merge its `detectors.ocr` entry into `config.local.json`, or pass it via `--model-profile` when no separate model override is needed; the CLI overlays arbitrary config sections recursively.

## Outputs and tests

Deliverables appear under `<out>/output/`: `editable.pptx`, rendering and validation reports, provenance, and a page manifest. A full rendered run also produces `preview.png`. Inspect `<out>/status.json` and `output/validation.json`; file existence alone does not indicate a successful run. `--resume` reuses validated completed stages.

```bash
python -m pytest -q
```

Tests use generated inputs and mocked or fixture model responses. Some integration tests need Node.js and the installed npm dependency; render checks require LibreOffice and Poppler.

## License

Apache-2.0; see [LICENSE](LICENSE) and [NOTICE](NOTICE). Dependencies keep their own licenses.
