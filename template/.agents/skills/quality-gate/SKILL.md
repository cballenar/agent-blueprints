---
name: quality-gate
version: 1.0
description: Pre-land diff, acceptance-criteria, and test-integrity gate. Run after verification checks pass and before committing/pushing to main or merging a PR.
---

# Quality Gate

Run this gate after all repo verification commands pass and **before** landing changes (`git push` or `gh pr merge`).

## 1. Diff & Scope Check

Inspect the full diff against `main` (`git diff main...HEAD` or `git diff` if working directly on `main`) and verify:
- **Acceptance Criteria:** Every requirement in the claimed issue (`gh issue view <n>`) is actually implemented end-to-end—not stubbed, hardcoded, or half-wired.
- **No Strays:** No debug logs, temporary files, commented-out blocks, or unrelated edits outside the issue's scope.

## 2. Test & Verification Integrity

- **Zero Skips / Relaxations:** Confirm the diff does not introduce skipped tests (`.skip`, `@pytest.mark.skip`, `xfail`), `|| true` shell masks, or weakened assertions just to pass CI.
- **Fresh Run:** Verification commands were executed *after* the final edit, with all reported cases passing.

## 3. Spec & Docs Sync

- If the change alters architecture, external interfaces, or repo verification commands, update `PROJECT_SPEC.md` (or `AGENTS.md` in interactive mode) in the same wave so docs do not drift.

## 4. Verdict

- **Pass:** Proceed to commit/push/merge.
- **Fail:** Fix the gap and re-run verification before landing. If blocked by ambiguity or a control-plane boundary, escalate via `status:needs-decision`.
