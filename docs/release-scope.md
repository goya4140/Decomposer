# Framework-only release scope

Included:

- All `decomposer/*.py` framework modules, unchanged from the source snapshot.
- JSON stage prompts and optional Representation strategies.
- Deterministic native PPTX compiler and its npm lockfile.
- Vision model adapter and optional Apple Vision OCR adapter.
- Knowledge evidence/eligibility audit and stage-snapshot verification utilities.
- Portable configuration templates, installation instructions, Apache-2.0 license.
- Framework tests with synthetic inputs and mocked responses, and a generated smoke example.

Excluded:

- Research images, annotations, dataset manifests and train/test sample lists.
- Run outputs, benchmark results, provider comparison reports, figures and PPTX artifacts.
- Historical `knowledge/evidence`, `knowledge/memory`, and `knowledge/skills` snapshots.
- First-100 training/audit runners, experiment bootstrapping, ad hoc probes, replay/comparison harnesses and their dedicated tests.
- Model weights, bundled binaries, virtual environments and installed npm packages.
- Machine-local configs, personal paths, credentials and historical framework manifests.

Runtime schemas and prompts are framework dependencies and are included. The knowledge engine and deterministic mechanisms already implemented in framework code remain included; only historical knowledge records are excluded.

Mixed shard-generation and knowledge-retrieval test files retain their framework checks while removing imports/tests for excluded experiment harnesses. The pipeline integration test checks the root `node_modules` location used by `npm ci`. Core framework code is otherwise copied byte-for-byte.

This snapshot supports running the framework on a user's own figures. It does not include enough assets to reproduce the historical research evaluation, and makes no benchmark-performance claim.
