# Adapter contracts

## Vision model

All model stages receive a prompt, image, input JSON and closed output schema. The `codex-cli` backend passes these to an isolated Codex CLI process. `external-json` supports any configured executable that follows the contract.

`model.command` is an executable string or an argument list. `model.arguments` supports `{stage}`, `{prompt_file}`, `{schema_file}`, and `{image_file}`. The complete prompt is also supplied on stdin. Emit the final JSON object on stdout and diagnostics on stderr. A nonzero exit, timeout, invalid JSON or failed model call cannot become a successful generation checkpoint.

The included `adapters/openai_compatible_vision.py` uses a Chat Completions vision request. It supports `json_schema`, `json_object`, and `prompt_only`; endpoint support varies. It reads the URL, API key and model from named environment variables. List required variables in `model.environment_allowlist`. The URL can include `/v1`; the adapter appends `/chat/completions`.

Run metadata omits inherited credential values. Avoid placing secrets in command arguments, profiles or adapter diagnostics. Run directories retain prompts, source images and responses for audit and are excluded from the source release.

## Detectors

SAM and OCR are subprocess interfaces, not bundled detector implementations. `detectors.sam.command` and `detectors.ocr.command` should be argument lists. Each command receives one JSON object on stdin:

```json
{"schema_version":"decomposer.ocr-request.v2","image":"BASE64_IMAGE_BYTES","canvas":{"width":640,"height":360},"options":{}}
```

Use `decomposer.sam-request.v2` for SAM. Respond with a JSON object containing `items`. An item has an `id`, a pixel-coordinate `bbox` in `[x, y, width, height]`, and optional `confidence`. OCR items include `text`; SAM items can include `role` and mask-related fields consumed by the evidence layer. The collector also accepts `text_regions` for OCR and `regions` for SAM.

The default base configuration disables both detectors. This permits a model-only run but does not reproduce detector-backed research settings. Apple Vision OCR is included as an optional macOS adapter; other OCR or segmentation engines and weights must be supplied separately.

## Renderer

Configure `runtime.node`, `runtime.soffice`, `runtime.pdftoppm` and a timeout. Rendering converts the compiled PPTX to PDF with LibreOffice, then rasterizes it at the source canvas resolution with Poppler. Rendered fidelity depends on available fonts. `--no-render` performs structural compilation without visual refinement or registration.
