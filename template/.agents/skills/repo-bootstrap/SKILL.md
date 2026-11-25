---
name: repo-bootstrap
version: 1.0
description: Initialize a repository from the agent-blueprints template. Verifies git/gh auth, creates required status:* and domain:* GitHub labels, scaffolds PROJECT_SPEC.md, and trims AGENTS.md to the project's chosen structure and merge strategy.
---

# Repo Bootstrap

Use this skill after copying `template/` into a repository (or when onboarding an existing repo to the `AGENTS.md` + `autonomous-dispatcher` workflow).

## 1. Pre-Flight & Label Sync

Run `bootstrap.py` first in `--dry-run` mode to verify `git`, `gh auth status`, and remote repo access:

```bash
python3 .agents/skills/repo-bootstrap/scripts/bootstrap.py --dry-run
```

If the user has identified modules/areas (or you can infer them from top-level directories), pass them via `--domains`:

```bash
python3 .agents/skills/repo-bootstrap/scripts/bootstrap.py --domains api,ui,infra
```

Without `--dry-run`, this idempotently creates/updates:
- `status:ready`, `status:in-progress`, `status:needs-decision`, `status:human-spike`, `status:blocked`
- Any requested `domain:<area>` labels
- `PROJECT_SPEC.md` (if missing, unless `--no-spec` is passed)

## 2. Tailor `AGENTS.md`

Inspect the repository layout and confirm with `<owner>` (or infer when obvious):
1. **Header (`Project & Spec`):** Fill in `<Project Title>`, `<owner>/<repo>`, and `<1-2 sentence summary>`.
2. **Project Structure:** Keep the single matching Option (**A** Multi-Part, **B** Lean Monorepo, **C** Infrastructure/IaC, or **D** Content/Research), replace `<verify commands>` with the real test/lint/build commands, and delete the unused options.
3. **Branching, Merging & Release Strategy:** Keep **Option A** (Direct-to-Main) or **Option B** (PR-Gated) and delete the unused option (and the Release Bundle PR add-on unless needed).
4. **Autonomous Execution:**
   - If working **purely interactively**, delete the `Autonomous Execution` section from `AGENTS.md`.
   - If enabling **scheduled/unattended runs**, keep `Autonomous Execution` and configure the schedule using the templates in `.agents/skills/autonomous-dispatcher/SKILL.md` (always prompt `<owner>` before enabling).

## 3. Verify Readiness

Confirm `AGENTS.md` has no leftover placeholder tokens (`<Project Title>`, `<owner>/<repo>`, `<verify commands>`) and run `python3 .agents/skills/autonomous-dispatcher/scripts/preflight_check.py --dry-run` (if autonomous mode is enabled) to verify the GitHub queue gate works cleanly.
