<!-- version: 1.1 -->
# Autonomous Safety Guardrails

**Scope:** These rules apply **only during unattended / scheduled (`autonomous-dispatcher`) runs**. Interactive sessions with human collaborators are governed by normal workspace judgment.

These guardrails prevent runaway loops and self-modification without blocking normal feature, bugfix, or refactoring work:

1. **Control-Plane & Secrets Boundary:**
   - Do **not** modify `.agents/`, `AGENTS.md`, `.github/workflows/`, or `.env*` / credential files autonomously.
   - Normal source code, tests, docs, build configs, and dependency manifests (`package.json`, `pyproject.toml`, etc.) remain freely editable as required by the issue.
   - If an issue legitimately requires a workflow, rule, or `AGENTS.md` change, post the proposed diff under `**[Agent]**`, set `status:needs-decision`, assign the default human assignee(s) from `AGENTS.md`, and exit cleanly.

2. **Test Integrity:**
   - Never delete, skip (`.skip`, `@pytest.mark.skip`, `xfail`), or weaken existing tests to force a green check.
   - Updating test assertions when the issue explicitly changes expected behavior is allowed and expected.

3. **Anti-Thrash Retry Cap:**
   - Allow at most **3 edit-and-verify cycles** on the same failing error within a single wave.
   - If verification still fails after 3 attempts, stop looping: restore clean `main`, post root-cause findings and options prefixed with `**[Agent]**`, swap `status:in-progress` -> `status:needs-decision`, assign the default human assignee(s) from `AGENTS.md`, and end the turn.
