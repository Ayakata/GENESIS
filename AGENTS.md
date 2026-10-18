# Genesis development

- Read GENESIS_ROADMAP.md for authoritative scope/status; never close a checkbox without evidence.
- The near-term agent sandbox is temporary. Do not encode species or ecological roles into chemistry.
- Keep numerical state in arrays; use owned, versioned RNG streams, never global randomness.
- Core cannot depend on CLI/history/viewer. Lab observation must not become an external fitness.
- State schemas, configuration schemas and numerical rules have independent versions.
- Resource sources, sinks and action costs must be explicit and covered by invariant tests.
- Before closing work: pytest, Ruff check/format, strict mypy, relevant reproducibility scenarios.
- Preserve reports/configs/code fingerprints and document limitations and negative results.
- Use local git commits; do not invent a remote or publish externally without user instruction.
