# Security policy

## Reporting a vulnerability

Please use [GitHub Security Advisories](https://github.com/sergeyshmakov/runpod-mineru/security/advisories/new) to report security issues privately. Do **not** open public issues for security problems.

You should expect an initial response within 5 working days.

## Scope

In scope:
- Code injection / unsafe deserialization in `handler.py` or `mineru_client/`
- Path traversal via `volume_path` or `basename`
- Resource exhaustion via crafted input that bypasses the documented limits
- Exposure of `RUNPOD_API_KEY` or other secrets through the code paths in this repo

Out of scope (please report upstream):
- Vulnerabilities in [MinerU](https://github.com/opendatalab/MinerU) — report to opendatalab
- Vulnerabilities in vLLM, RunPod platform, the base Docker image, or transitive Python dependencies — report to their respective maintainers

## Hardening notes for operators

- Always set `RUNPOD_API_KEY` via environment variable; never commit it. `.env` is `.gitignore`d but be careful with shell history.
- Treat `volume_path` as a privileged input — only mount volumes you control, and validate paths in any caller code that builds them from user input.
- Set `execution_timeout` low enough to prevent a stuck job from costing you a runaway GPU bill.
