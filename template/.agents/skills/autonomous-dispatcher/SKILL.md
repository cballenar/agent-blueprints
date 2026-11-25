---
name: autonomous-dispatcher
version: 1.3
description: Autonomous GitHub issue triage, execution, verification, and delivery loop. Use during scheduled cron runs or when asked to advance the GitHub backlog autonomously.
---

# Autonomous Dispatcher

Advance the repository continuously from GitHub Issues (`gh`) through verified delivery—respecting the repository's chosen branching/merge strategy in `AGENTS.md` while keeping human decisions and manual spikes non-blocking.

---

## Phase 0: Pre-Flight Concurrency, Lease & Hash Gate (Mandatory First Step)

Before reading `AGENTS.md`, project specs, or modifying any files/branches, run:

```bash
python3 .agents/skills/autonomous-dispatcher/scripts/preflight_check.py
```

- **Concurrency Lock (`SKIP:BUSY`):** Aborts if an autonomous run is still within its lease/activity TTL (`.git/dispatcher_lease.json`, default 30m) or if local git is dirty/off-`main` without a lease (protecting interactive human sessions).
- **Queue Hash (`SKIP:NO_CHANGE` / `SKIP:NO_ACTIONABLE_WORK`):** Compares a SHA-256 digest of open `status:ready` issues, open PRs, and human-queue state against `.git/preflight_state.sha256`.
- **Early Exit Rule:** If stdout starts with `SKIP:`, output that single line verbatim and end the turn immediately with zero file reads or extra tool calls.
- **Stale Lock Recovery (`RUN:RECOVER_STALE`):** Emitted when a prior autonomous run timed out mid-flight. Execute **Recovery Only** and end the turn:
  1. If the orphaned branch/PR is complete and passes repo verification, finish landing it per Phase 4.
  2. Otherwise, preserve any uncommitted changes (`git stash push -u -m "stale-recover-<issue>"`), return to clean `main` (`git checkout main && git pull --ff-only`), and reset each orphaned issue from `status:in-progress` back to `status:ready` (or `status:needs-decision` with a `**[Agent]**` note if blocked).
  3. Remove `.git/dispatcher_lease.json` and exit immediately without starting new issues.

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

## Phase 2: Select One Wave of Work

Each scheduled session executes **at most one wave** and exits—never loop back for a second wave in the same session.

1. If the repo uses PRs (**Option B** or the **Release Bundle PR** add-on in `AGENTS.md`), check open PRs first:
   ```bash
   gh pr list --state open --json number,title,headRefName,statusCheckRollup,mergeable
   ```
   If a ready, green PR exists, verifying and merging it counts as this run's wave.
2. Otherwise, fetch unassigned `status:ready` issues:
   ```bash
   gh issue list --state open --label "status:ready" --search "no:assignee" --json number,title,labels,milestone,body
   ```
   Under **Option B (PR-Gated / Proposal-First)**, never implement issues opened strictly as questions or proposals until authorized (`status:ready` or explicit approval).
3. Order by dependency and domain (`domain:*`):
   - **Single-Agent Mode (default):** Pick **1** issue.
   - **Parallel / Swarm Mode (when isolated `share`/`branch` workspaces or worktrees are available):** Pick **1 bounded batch** of non-colliding `domain:*` issues whose files do not overlap (1 issue per isolated worker).

---

## Phase 3: Claim, Execute & Verify

1. Claim the selected issue(s):
   ```bash
   gh issue edit <n> --remove-label "status:ready" --add-label "status:in-progress"
   ```
2. Follow the **Branching, Merging & Release Strategy** configured in `AGENTS.md`:
   - **Option A (Direct-to-Main):** Work on `main` (or a short local branch merged straight to `main`).
   - **Option B (PR-Gated / Proposal-First):** Branch `feat/issue-<n>-<slug>` or `fix/issue-<n>-<slug>` from `main`.
   - **Release Bundle PR Add-On (if enabled):** Target the active integration/release branch (`develop` or `release/vX.Y.Z`) before bundling into `main`.
   - *Parallel Mode:* Dispatch each issue to its own isolated worker (`workspace: "share"` or `"branch"`), keeping the primary workspace clean on `main` until verified branches are ready to land.
3. Implement acceptance criteria and run the repository's verification checks after the final edit; never proceed with failing or skipped checks. Respect `.agents/rules/autonomous-safety.md` (max 3 retry cycles on the same failure; never edit control-plane files autonomously).
4. Run the `quality-gate` skill (`.agents/skills/quality-gate/SKILL.md`) to audit the diff against issue acceptance criteria before Phase 4.

---

## Phase 4: Land, Unblock & Exit

1. Commit using Conventional Commits (`feat|fix|docs(<scope>): <summary> (#<n>)`).
2. Land according to `AGENTS.md`:
   - **Option A (Direct-to-Main):** Push verified commit referencing `Closes #<n>` (or close via `gh issue close <n>`).
   - **Option B (PR-Gated / Proposal-First):** Push branch, open PR with `Closes #<n>`, and queue auto-merge (`gh pr merge <pr> --auto --squash --delete-branch`). If auto-merge is not enabled on the repo, do **not** block on `gh pr checks --watch` in unattended runs—leave the open PR for the next tick's Phase 2 to squash-merge once green (`gh pr merge <pr> --squash --delete-branch`). Always return to clean `main` (`git checkout main && git pull --ff-only`) before exiting.
   - **Release Bundle PR Add-On (if enabled):** Land verified issue work onto the integration/release branch and open/update the bundle PR into `main` for pre-deploy verification.
3. **Clean Up Status Label (All Strategies):**
   ```bash
   gh issue edit <n> --remove-label "status:in-progress"
   ```
4. **Unblock & Chain Next Work:**
   - Remove `status:blocked` on newly unblocked downstream issues and comment with links to the landed work (prefix with `**[Agent]**`).
   - Reopen/append to an existing issue if follow-up work belongs to the same thread; otherwise file new issues (`status:ready` unassigned, or `status:needs-decision` / `status:human-spike` assigned to `<owner>` prefixed with `**[Agent]**`).
5. **If Blocked Mid-Issue:** Never guess past an ambiguity or land broken work. Comment with findings, options, and a recommended default prefixed with `**[Agent]**`, swap `status:in-progress` -> `status:needs-decision`, assign `<owner>`, and restore clean `main`.
6. **Milestones & Exit:** When all issues in a Milestone close on green `main`, cut a release (`gh release create vX.Y.Z --generate-notes`). Remove `.git/dispatcher_lease.json` if present, ensure `git status --porcelain` is clean on `main`, and **end the turn** (leave remaining `status:ready` issues for the next scheduled tick).

---

## Scheduled Automation Templates

When bootstrapping a repository on a platform that supports agent-created schedules (such as Antigravity's `automation` skill), create the scheduled automation using the appropriate template below and prompt `<owner>` to review permissions and enable it—never force-enable it silently.

- **Unattended Permissions:** Headless runs require pre-approved network/config access for `gh`, `git`, and `preflight_check.py` (e.g., `BypassSandbox` or allowlisted command rules) so they do not stall on interactive permission prompts.
- **Upgrading from v1.0:** Updating files in-repo does not update external scheduler prompts. Ensure any existing scheduled prompt triggers on `RUN:` (or both `RUN:WORK_READY` and `RUN:RECOVER_STALE`) so timed-out runs are recovered.

### Option 1: Pre-Launch Shell Gate (Preferred When Supported — 0 Agent Launches When Idle)
If your scheduler (cron, launchd, systemd, CI, or wrapper runner) can run a script prior to starting an agent session, gate the launch directly with `--exit-code` (exits `0` on `RUN:*`, `10` on `SKIP:*`):

```bash
cd <repo-root> && python3 .agents/skills/autonomous-dispatcher/scripts/preflight_check.py --exit-code && <launch-agent-command>
```

### Option 2: In-Chat Prompt Gate (For Schedulers That Always Open a Chat)
Use this prompt so idle runs cost one tool call and zero file reads:

```text
Work in <repo-root>. BEFORE reading AGENTS.md, SKILL.md, or any other file, run:
python3 <repo-root>/.agents/skills/autonomous-dispatcher/scripts/preflight_check.py
If stdout starts with SKIP:, output that single line verbatim and end your turn immediately without calling any other tools.
ONLY if stdout starts with `RUN:` — read AGENTS.md and .agents/skills/autonomous-dispatcher/SKILL.md and execute the corresponding phase, then exit after one wave.
```
