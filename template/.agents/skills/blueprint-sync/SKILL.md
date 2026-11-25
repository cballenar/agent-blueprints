---
name: blueprint-sync
version: 1.1
description: Sync AGENTS.md, .agents/rules/, and .agents/skills/ with cballenar/agent-blueprints (main) using file-level version headers instead of tags or releases.
---

# Blueprint Sync

1. **Check versions:**
   ```bash
   python3 .agents/skills/blueprint-sync/scripts/check_updates.py
   ```
2. **Apply updates** *(interactive only; if running autonomously, raise `status:needs-decision` per `.agents/rules/autonomous-safety.md`)*:
   - **`NEW` skill/rule:** Fetch all files under `template/.agents/<type>/<name>/` from `cballenar/agent-blueprints` (`main`) and write locally.
   - **`OUTDATED` skill/rule:** Diff upstream vs. local before overwriting so repo-specific tweaks are preserved.
   - **`OUTDATED` `AGENTS.md`:** Never overwrite wholesale. Merge only new/changed sections while keeping `Project & Spec`, trimmed `Project Structure`, and `Branching` choices, then bump `<!-- version: X.Y -->`.
3. **Verify:** Re-run `check_updates.py` (all `UP_TO_DATE`) and `python3 -m py_compile .agents/skills/*/scripts/*.py`. If `autonomous-dispatcher` was updated, check that any external scheduled prompt matches its latest trigger template (e.g., triggering on `RUN:` rather than only `RUN:WORK_READY`).
