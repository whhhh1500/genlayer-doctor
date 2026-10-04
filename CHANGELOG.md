# Changelog

## 0.2.0 — 2026-10-04
- **Web UI** (GitHub Pages, `docs/`): paste a contract for the header lint + gasless Studio dry run (ABI or decoded GenVM error), "Fix header", or paste a tx hash for the consensus-vs-execution verdict, decoded result, votes, emitted messages and deployed-header check. Deep links `#tx=…&net=…`. Network selector (studionet, localnet, custom RPC).
- `docs/gldoctor.js`: dependency-free ES-module port of header/diagnose/explain with the same finding codes, including a small Python-literal parser for Studio's error payloads (with a regex fallback).
- `tests/js/`: 14 parity tests against the recorded Studio fixtures. CI runs them.
- `explain` handles genlayer-js style numeric statuses and `{status, payload}` results in the browser port.

## 0.1.0 — 2026-10-04
- `gldoctor check`: runner-header lint (GLD001–008), syntax check, gasless dry run via `gen_getContractSchemaForCode` with GenVM error classification and traceback extraction, optional `genvm-lint` passthrough, `--json`, `--strict`.
- `gldoctor explain`: consensus-vs-execution verdict, GenVM result decoding, votes, deployed-source header check; `--from-file`.
- `gldoctor fix`: pin/insert/move the py-genlayer runner header (diff or `--write`).
- `gldoctor networks --ping`.
- pre-commit hooks, composite GitHub Action, live Studio demo.
