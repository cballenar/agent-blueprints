---
name: autonomous-dispatcher
version: 1.0
description: Autonomous GitHub issue triage, execution, verification, and delivery loop. Use during scheduled cron runs or when asked to advance the GitHub backlog autonomously.
---

# Autonomous Dispatcher

Advance the repository continuously from GitHub Issues (`gh`) through verified delivery—respecting the repository's chosen branching/merge strategy in `AGENTS.md` while keeping human decisions and manual spikes non-blocking.

---

## Phase 0: Pre-Flight Concurrency & Hash Gate (Mandatory First Step)

Before reading `AGENTS.md`, project specs, or modifying any files/branches, run:

```bash
python3 .agents/skills/autonomous-dispatcher/scripts/preflight_check.py
```

- **Concurrency Lock (`SKIP:BUSY`):** Aborts if `branch != main`, `git status --porcelain` is non-empty, or any open issue holds `status:in-progress`.
- **Queue Hash (`SKIP:NO_CHANGE` / `SKIP:NO_ACTIONABLE_WORK`):** Compares a SHA-256 digest of open `status:ready` issues, open PRs, and human-queue state against `.git/preflight_state.sha256`.
- **Early Exit Rule:** If stdout starts with `SKIP:`, output that single line verbatim and end the turn immediately with zero file reads or extra tool calls. Proceed only on `RUN:WORK_READY`.

---

## Phase 1: Sync & Triage Human Replies

1. Sync `main`:
   ```bash
   git checkout main && git pull --ff-only
   ```
2. Inspect human-queue issues (`status:needs-decision`, `status:human-spike`):
   ```bash
   gh issue list --state open --label "status:needs-decision" --json number,title,assignees,comments,updatedAt
   gh issue list --state open --label "status:human-spike" --json number,title,assignees,comments,updatedAt
   ```
3. For any issue where `<owner>` posted a reply (a latest comment not prefixed with `**[Agent]**`) or removed themselves as assignee:
   - Record settled decisions in the project spec or as an issue comment.
   - Transition the issue to `status:ready` (or close if it was a completed spike):
     ```bash
     gh issue edit <n> --remove-label "status:needs-decision" --add-label "status:ready" --remove-assignee <owner>
     ```
   - Extend/reopen an existing issue when iterating on the same topic instead of fragmenting into duplicates; file child `status:ready` issues only for distinct new workstreams.

---

## Phase 2: Select Work

1. If the repo uses PRs (**Option B** or the **Release Bundle PR** add-on in `AGENTS.md`), check open PRs first:
   ```bash
   gh pr list --state open --json number,title,headRefName,statusCheckRollup,mergeable
   ```
   Verify and merge any ready, green PR before starting duplicate work.
2. Fetch unassigned `status:ready` issues:
   ```bash
   gh issue list --state open --label "status:ready" --search "no:assignee" --json number,title,labels,milestone,body
   ```
   Under **Option B (PR-Gated / Proposal-First)**, never start implementing issues opened strictly as questions or proposals until authorized (`status:ready` or explicit approval).
3. Order by dependency and domain (`domain:*`). Pick either a single issue or a non-colliding batch whose files do not overlap.

---

## Phase 3: Claim, Execute & Verify

1. Claim each issue:
   ```bash
   gh issue edit <n> --remove-label "status:ready" --add-label "status:in-progress"
   ```
2. Follow the **Branching, Merging & Release Strategy** configured in `AGENTS.md`:
   - **Option A (Direct-to-Main):** Work on `main` (or a short local branch merged straight to `main`).
   - **Option B (PR-Gated / Proposal-First):** Branch `feat/issue-<n>-<slug>` or `fix/issue-<n>-<slug>` from `main`.
   - **Release Bundle PR Add-On (if enabled):** Target the active integration/release branch (`develop` or `release/vX.Y.Z`) before bundling into `main`.
   - *Parallel Mode (when multiple non-colliding domains are ready):* Isolate each writer in its own worktree/workspace with an independent verification pass; fall back to sequential execution if the runtime restricts nested workflows.
3. Implement acceptance criteria and run the repository's verification checks after the final edit; never proceed with failing or skipped checks.

---

## Phase 4: Land, Unblock & Follow-Ups

1. Commit using Conventional Commits (`feat|fix|docs(<scope>): <summary> (#<n>)`).
2. Land according to `AGENTS.md`:
   - **Option A (Direct-to-Main):** Push verified commit referencing `Closes #<n>` (or close via `gh issue close <n>`) and remove `status:in-progress`.
   - **Option B (PR-Gated / Proposal-First):** Push branch, open PR with `Closes #<n>`, wait for green CI (`gh pr checks <pr> --watch`), squash-merge (`gh pr merge <pr> --squash --delete-branch`), then `git checkout main && git pull --ff-only`.
   - **Release Bundle PR Add-On (if enabled):** Land verified issue work onto the integration/release branch and open/update the bundle PR into `main` for pre-deploy verification.
3. **Unblock & Chain Next Work:**
   - Remove `status:blocked` on newly unblocked downstream issues and comment with links to the landed work (prefix with `**[Agent]**`).
   - Reopen/append to an existing issue if follow-up work belongs to the same thread; otherwise file new issues (`status:ready` unassigned, or `status:needs-decision` / `status:human-spike` assigned to `<owner>` prefixed with `**[Agent]**`).
4. **If Blocked Mid-Issue:** Never guess past an ambiguity or land broken work. Comment with findings, options, and a recommended default prefixed with `**[Agent]**`, swap `status:in-progress` -> `status:needs-decision`, assign `<owner>`, and move on to unblocked issues.
5. **Milestones:** When all issues in a Milestone close on green `main`, cut a release (`gh release create vX.Y.Z --generate-notes`).

---

## Scheduled Automation Templates

When bootstrapping a repository on a platform that supports agent-created schedules (such as Antigravity's `automation` skill), create the scheduled automation using the appropriate template below and prompt `<owner>` to review permissions and enable it—never force-enable it silently.

### Option 1: Pre-Launch Shell Gate (Preferred When Supported — 0 Agent Launches When Idle)
If your scheduler (cron, launchd, systemd, CI, or wrapper runner) can run a script prior to starting an agent session, gate the launch directly with `--exit-code` (exits `0` only on `RUN:WORK_READY`, `10` on `SKIP:*`):

```bash
cd <repo-root> && python3 .agents/skills/autonomous-dispatcher/scripts/preflight_check.py --exit-code && <launch-agent-command>
```

### Option 2: In-Chat Prompt Gate (For Schedulers That Always Open a Chat)
Use this prompt so idle runs cost one tool call and zero file reads:

```text
Work in <repo-root>. BEFORE reading AGENTS.md, SKILL.md, or any other file, run:
python3 <repo-root>/.agents/skills/autonomous-dispatcher/scripts/preflight_check.py
If stdout starts with SKIP:, output that single line verbatim and end your turn immediately without calling any other tools.
ONLY if stdout starts with RUN:WORK_READY: read AGENTS.md and .agents/skills/autonomous-dispatcher/SKILL.md and execute Phases 1–4.
```
