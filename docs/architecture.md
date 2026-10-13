# Framework architecture

The public snapshot retains all Python modules in `decomposer/` and the deterministic backend in `backend/compile.mjs`. Schemas live in `decomposer/schemas.py`; stage instructions live in `prompts/`. The snapshot's internal version is `1.1.0-refinement-memory`.

| Layer | Source | Responsibility |
| --- | --- | --- |
| CLI / orchestration | `run.py`, `decomposer/pipeline.py` | Config overlays, checkpoints, stage execution, resume and terminal status |
| Model transport | `decomposer/model.py`, `adapters/` | JSON-only model requests, schemas, isolated CLI calls or external processes |
| Observations | `detectors.py`, `evidence.py` | Optional detector candidates and traceable immutable evidence |
| Recognition | `recognition.py` | Object identity, category, exact source text, bounds and connector relations |
| Asset policy | `asset_policy.py` | Authorize only bounded localized raster leaves; reject screenshot-like substitutions |
| Representation | `representation.py`, `representation_compact.py`, `representation_shards.py` | Component-local primitives, styles, geometry and text; optional compact or sharded generation |
| Layout | `layout.py` | Global bounds, rotation, scale and z-order |
| Assembly | `assemble.py` | Combine local representation with global placement into native scene IR |
| Compiler / renderer | `pptx.py`, `polygons.py`, `backend/compile.mjs` | PptxGenJS serialization, native DrawingML geometry and real PPTX rendering |
| Quality / provenance | `quality.py`, `validation.py`, `provenance.py`, `text_visibility.py` | Structural and visual checks, editable source identity, shape-level traceability |
| Refinement | `refinement.py` | Diagnose one issue, enforce source-stage ownership, compile/render candidate, accept or roll back |
| Registration | `*_registration.py`, `rendered_text_ink.py`, `native_text_style_probe.py` | Measured correction of native text, fill, panels, shadows, tracking and style |
| Knowledge / evidence | `knowledge.py`, `evolution.py`, `fixture_provenance.py` | Capture evidence, bounded retrieval, lifecycle state, checkpoint and replay provenance |

## Contracts

Models return JSON proposals. They do not write executable compiler code or OOXML. Canonicalization validates and repairs proposal structure, but a required failed model stage cannot be accepted as a completed stage simply because fallback content is structurally valid.

Recognition owns identity and source text; Representation owns local primitive geometry and style; Layout owns global placement. Assembly alone combines these outputs. The deterministic compiler owns serialization. A refinement patch must declare its labels and respect the owning stage's fields.

Native non-equation text preserves source identity. Approved photographs or other irreducible leaves can remain localized images. Whole-page raster replacement is blocked. SVG files are not used as an intermediate or output; a path primitive's SVG-compatible path syntax is converted to native DrawingML geometry.

Refinement uses a fixed focus region, local pixel similarity and edge IoU, global regression tolerance, and structural/provenance gates. It commits only accepted candidates and retains rejected evidence. Configured refinement rounds are capped at three in the reference configuration. Deterministic post-render registration applies additional bounded, stage-specific acceptance gates and records candidate selection, rollback, and hash chains.

## Empty knowledge initialization

Recognition, Representation, and Layout receive no runtime memories. Refinement may retrieve bounded, problem-related knowledge. `refinement.knowledge_path: null` uses `<out>/knowledge`, initially empty; it records evidence from the user's own runs. Set a path explicitly to share a user-maintained knowledge store. Historical evidence, memories, and mirrored skill packages are not included.

The structural smoke example does not exercise rendered refinement or every registration branch. The test suite covers those contracts with synthetic inputs and mocked measurements; model quality and font-sensitive rendering remain dependent on the user's runtime.
