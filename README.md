# Agent Blueprints

Starter template and skills for autonomous and interactive GitHub-backed development. Primarily built for **Google Antigravity** but can easily be adapted to other software.

## Available Template

[`template/`](./template/) defines an agent-ready workspace using GitHub Issues (`gh`) as a living ledger, selectable project structure and branching/release strategies (`AGENTS.md`), and:
- **`repo-bootstrap` skill** — Idempotent `bootstrap.py` script to verify `gh` auth, create canonical `status:*` / `domain:*` labels, scaffold `PROJECT_SPEC.md`, and trim `AGENTS.md`.
- **`autonomous-dispatcher` skill** — Scheduled/unattended backlog loop with a SHA-256 queue hash, lease recovery, and concurrency pre-flight gate (`preflight_check.py`).
- **`quality-gate` skill** — Pre-land diff, acceptance-criteria, and test-integrity check before pushing or merging.
- **`blueprint-sync` skill** — Compares local `AGENTS.md`, rules, and skills against `cballenar/agent-blueprints` by file-level version headers to pull upstream updates safely.
- **`autonomous-safety` rule** — Unattended-only guardrails (control-plane boundary, test integrity, and 3-cycle retry cap).

*(Note: While there is only a single blueprint today it will move to `templates/<name>/` if distinct templates are added in the future.)*

## Usage
Copy the contents of [`template/`](./template/) into your project root and run the **`repo-bootstrap`** skill (or `python3 .agents/skills/repo-bootstrap/scripts/bootstrap.py`).

