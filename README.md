# Agent Blueprints

Starter template and skills for autonomous and interactive GitHub-backed development. Primarily built for **Google Antigravity** but can easily be adapted to other software.

## Available Template

[`template/`](./template/) defines an agent-ready workspace using GitHub Issues (`gh`) as a living ledger, selectable project structure and branching/release strategies (`AGENTS.md`), and an `autonomous-dispatcher` skill with a SHA-256 queue hash & concurrency pre-flight gate for scheduled unattended runs.

*(Note: While there is only a single blueprint today it will move to `templates/<name>/` if distinct templates are added in the future.)*

## Usage
Copy the contents of [`template/`](./template/) into your project root and trim the unused options in `AGENTS.md`.

