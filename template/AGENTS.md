<!-- version: 1.2 -->
# `<Project Title>` — Agent Workspace Rules

## Project & Spec
*(Fill in on deployment.)*
- **Repo:** `<owner>/<repo>` | **Spec:** `[PROJECT_SPEC.md](./PROJECT_SPEC.md)`
- **Goal:** `<1–2 sentence summary>`

## Project Structure
*(Keep the option matching this repo and delete the rest on deployment, or run `.agents/skills/repo-bootstrap/SKILL.md`. Shared convention: `.agents/skills/` holds domain runbooks/scripts and `.agents/rules/` holds execution guardrails.)*

### Option A: Multi-Part / Hybrid
- `<component-a>/`, `<component-b>/` — Independent subsystems (`<verify commands>`).
- `packages/` — Shared schemas or contracts.
- `fixtures/` — Golden snapshots, test corpora, or generated/physical assets.
- `submodules/` *(optional)* — Independent external repos.
- **External Boundary:** Never mutate remote hosts/infra directly; emit deployment templates here.

### Option B: Lean Monorepo / Single-Project
- `src/` — Primary source (`<verify commands>`).
- `tests/` — Automated tests or validation scripts.
- `assets/` *(optional)* — Static media or fixtures.

### Option C: Infrastructure / Homelab / IaC
- `hosts/` — Host inventories and machine/network configs.
- `services/` — Declarative service units, compose/container templates, proxy rules.
- `scripts/` — Validation and dry-run helpers (`<dry-run / lint commands>`).
- **Safety Boundary:** Never apply destructive or live host mutations autonomously; validate via dry-run/lint and raise `status:human-spike` for live cutovers.

### Option D: Content / Research / Non-Code
- `sources/` — References, datasets, or raw notes.
- `drafts/` — Work-in-progress deliverables.
- `outputs/` — Published or review-ready outputs (`<link / schema / rubric checks>`).

---

## GitHub Issues as Living Ledger

GitHub Issues (`gh`) record *when*, *why*, and *how* every change happened—whether working interactively or autonomously.

- **Single Account:** Agents run as `<owner>` via `gh` (no bot user); ownership is determined by assignee + status label. Prefix agent follow-up comments with `**[Agent]**` to distinguish them from `<owner>` replies.
- **Log Approved Work:** Log every confirmed/approved request, feature, or fix as an issue so commits reference `#<n>`.
- **Evolve, Don't Sprawl:** Append context/decisions as comments, link related issues (`Refs #<n>`), and **reopen/extend** closed issues instead of creating duplicates around the same topic.
- **Labels & Grouping:** Exclusive status (`status:ready`, `status:in-progress`, `status:needs-decision`, `status:human-spike`, `status:blocked`); `domain:<area>` (modules), Milestones (release waves), optional GitHub Projects (human/cross-repo view; labels + Milestones stay authoritative).
- **Non-Blocking Human Tasks:** For ambiguities (`status:needs-decision`) or manual/physical tasks (`status:human-spike`), post `**[Agent]**` options, tradeoffs, and a recommended default, assign `<owner>`, mark strictly dependent issues `status:blocked`, and continue unblocked work.

---

## Branching, Merging & Release Strategy
*(Keep Option A or Option B and delete the unused one. Keep the Release Bundle PR add-on only if this repo has a staging/deployment gate.)*

### Option A: Direct-to-Main (Atomic / No PRs)
- Commit verified, approved changes directly to `main` (or merge a short local branch straight to `main`) with `Closes #<n>` or `Refs #<n>`, push, and close the issue.

### Option B: PR-Gated / Proposal-First
- Issues may be opened strictly as questions or proposals—do not implement or open a PR until authorized (`status:ready` or explicit approval).
- Once authorized, branch `feat/issue-<n>-<slug>` or `fix/issue-<n>-<slug>` from `main`, open a PR with `Closes #<n>`, wait for green CI (`gh pr checks --watch`), squash-merge (`gh pr merge <pr> --squash --delete-branch`), and pull `main`.

### Optional Add-On: Release / Deployment Bundle PRs *(Option A or B)*
- Accumulate verified commits/branches onto an integration/release branch (`develop` or `release/vX.Y.Z`), then open one bundle PR into `main` for pre-deploy verification.

### Delivery Rules
- **Commits:** Conventional Commits referencing `#<n>` (`feat|fix|docs(<scope>): <summary> (#<n>)`).
- **Verification:** Run repo verification checks after the final edit and pass `.agents/skills/quality-gate/SKILL.md` before landing; never push or merge failing/skipped checks.
- **Releases:** Cut tagged releases per completed Milestone on green `main`: `gh release create vX.Y.Z --generate-notes`.

---

## Autonomous Execution
*(Optional — delete this entire section if working purely interactively.)*

Enables scheduled or unattended agent runs against unassigned `status:ready` issues without colliding with interactive sessions.

### Phase 0: Scheduled Concurrency & Hash Gate
Run `preflight_check.py --exit-code` *before* launching an agent if your scheduler supports pre-launch shell gates; otherwise, scheduled runs MUST execute `python3 <path/to/preflight_check.py>` as their **first tool call before reading any files**:
1. **Lock (`SKIP:BUSY`):** Abort if `branch != main`, `git status --porcelain` non-empty, or open `status:in-progress` > `0` within the active lease TTL (or whenever local git is dirty without an autonomous lease, protecting interactive work).
2. **Stale Recovery (`RUN:RECOVER_STALE`):** Emitted if a prior autonomous run's lease (`.git/dispatcher_lease.json`, default 30m) and activity expired mid-flight. Land finished work if verified; otherwise stash uncommitted WIP, restore clean `main`, reset orphaned `status:in-progress` -> `status:ready`, and exit.
3. **Hash (`SKIP:NO_CHANGE` / `SKIP:NO_ACTIONABLE_WORK`):** SHA-256 of open `status:ready`, open PRs, and human-queue assignees/comments cached in `.git/preflight_state.sha256`.
4. If stdout starts with `SKIP:`, reply with that line and stop immediately (0 file reads, 0 extra calls). Proceed only on `RUN:WORK_READY` or `RUN:RECOVER_STALE`.

### Autonomous Loop (One Wave Per Run)
1. Sync `main`; triage `<owner>` replies on human issues (update spec, transition to `status:ready` or close, unblock downstream issues) and finish open PRs first.
2. Execute **at most one wave per run** (1 issue in single-agent mode, or 1 non-colliding `domain:*` batch across isolated `share`/`branch` worker workspaces), remove `status:in-progress` on completion, return to clean `main`, and **exit**—never loop back to claim another wave in the same session.
3. Unblock satisfied `status:blocked` issues and file follow-up `status:ready` / `status:needs-decision` / `status:human-spike` issues before exiting.
