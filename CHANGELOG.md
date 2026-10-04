# Changelog

## 0.1.0 — 2026-10-04
- `gldoctor check`: runner-header lint (GLD001–008), syntax check, gasless dry run via `gen_getContractSchemaForCode` with GenVM error classification and traceback extraction, optional `genvm-lint` passthrough, `--json`, `--strict`.
- `gldoctor explain`: consensus-vs-execution verdict, GenVM result decoding, votes, deployed-source header check; `--from-file`.
- `gldoctor fix`: pin/insert/move the py-genlayer runner header (diff or `--write`).
- `gldoctor networks --ping`.
- pre-commit hooks, composite GitHub Action, live Studio demo.
