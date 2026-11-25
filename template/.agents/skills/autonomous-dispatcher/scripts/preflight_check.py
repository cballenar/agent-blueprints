#!/usr/bin/env python3
"""Phase 0 concurrency guard and SHA-256 GitHub queue hash gate (project-agnostic)."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

AGENT_COMMENT_PREFIXES = ("**[Agent]**", "[Agent]")
SKIP_EXIT_CODE = 10


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def _run_json(cmd: list[str], cwd: Path) -> Any:
    raw = _run(cmd, cwd=cwd)
    return json.loads(raw) if raw else []


def _repo_root() -> Path:
    return Path(_run(["git", "rev-parse", "--show-toplevel"]))


def _gh_owner(repo_root: Path) -> str:
    return _run(["gh", "api", "user", "--jq", ".login"], cwd=repo_root)


def _looks_like_waiting_on_human(issue: dict[str, Any], owner: str) -> bool:
    """Return True when a human-queue issue is still assigned to owner and awaits a reply."""
    assignees = {a.get("login", "") for a in issue.get("assignees", [])}
    if owner not in assignees:
        return False

    comments = issue.get("comments") or []
    if not comments:
        return True

    latest_body = (comments[-1].get("body") or "").strip()
    return (
        any(latest_body.startswith(prefix) for prefix in AGENT_COMMENT_PREFIXES)
        or latest_body.startswith(f"@{owner} ")
    )


def _compute_digest(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()[:12]


def _git_common_dir(repo_root: Path) -> Path:
    raw = Path(_run(["git", "rev-parse", "--git-common-dir"], cwd=repo_root))
    return raw if raw.is_absolute() else (repo_root / raw).resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 0 concurrency & SHA-256 GitHub queue gate.")
    parser.add_argument(
        "--exit-code",
        action="store_true",
        help="Exit 10 on SKIP:* so shell/cron wrappers can gate agent launch with '&&'.",
    )
    args = parser.parse_args()
    skip_code = SKIP_EXIT_CODE if args.exit_code else 0

    repo_root = _repo_root()
    state_hash_file = _git_common_dir(repo_root) / "preflight_state.sha256"

    # 1. Concurrency lock
    branch = _run(["git", "branch", "--show-current"], cwd=repo_root)
    if branch != "main":
        print(f"SKIP:BUSY (branch={branch} != main)")
        return skip_code

    if _run(["git", "status", "--porcelain"], cwd=repo_root):
        print("SKIP:BUSY (dirty working tree)")
        return skip_code

    in_progress = _run_json(
        ["gh", "issue", "list", "--state", "open", "--label", "status:in-progress", "--json", "number"],
        cwd=repo_root,
    )
    if in_progress:
        nums = ",".join(f"#{i['number']}" for i in in_progress)
        print(f"SKIP:BUSY (in-progress issues: {nums})")
        return skip_code

    # 2. GitHub queue snapshot & SHA-256 hash
    owner = _gh_owner(repo_root)
    ready_raw = _run_json(
        [
            "gh", "issue", "list", "--state", "open",
            "--label", "status:ready", "--search", "no:assignee",
            "--json", "number,title,updatedAt",
        ],
        cwd=repo_root,
    )
    open_prs_raw = _run_json(
        [
            "gh", "pr", "list", "--state", "open",
            "--json", "number,title,headRefName,updatedAt",
        ],
        cwd=repo_root,
    )
    needs_decision_raw = _run_json(
        [
            "gh", "issue", "list", "--state", "open",
            "--label", "status:needs-decision",
            "--json", "number,title,assignees,comments,updatedAt",
        ],
        cwd=repo_root,
    )
    human_spike_raw = _run_json(
        [
            "gh", "issue", "list", "--state", "open",
            "--label", "status:human-spike",
            "--json", "number,title,assignees,comments,updatedAt",
        ],
        cwd=repo_root,
    )

    human_by_num: dict[int, dict[str, Any]] = {
        int(issue["number"]): issue for issue in [*needs_decision_raw, *human_spike_raw]
    }
    human_snapshot = [
        {
            "number": num,
            "updatedAt": issue.get("updatedAt"),
            "assignees": sorted(a.get("login", "") for a in issue.get("assignees", [])),
            "comment_count": len(issue.get("comments") or []),
            "last_comment_at": (
                issue["comments"][-1].get("createdAt") if issue.get("comments") else None
            ),
        }
        for num, issue in sorted(human_by_num.items())
    ]

    digest = _compute_digest(
        {
            "ready_issues": sorted(
                [{"number": i["number"], "updatedAt": i.get("updatedAt")} for i in ready_raw],
                key=lambda x: x["number"],
            ),
            "open_prs": sorted(
                [
                    {
                        "number": p["number"],
                        "headRefName": p.get("headRefName"),
                        "updatedAt": p.get("updatedAt"),
                    }
                    for p in open_prs_raw
                ],
                key=lambda x: x["number"],
            ),
            "human_issues": human_snapshot,
        }
    )

    saved_digest = (
        state_hash_file.read_text(encoding="utf-8").strip()
        if state_hash_file.is_file()
        else ""
    )
    has_queue_work = bool(ready_raw or open_prs_raw)

    if digest == saved_digest and not has_queue_work:
        print(f"SKIP:NO_CHANGE (sha256={digest})")
        return skip_code

    human_updates = [
        {"number": num, "title": issue["title"]}
        for num, issue in sorted(human_by_num.items())
        if not _looks_like_waiting_on_human(issue, owner)
    ]

    if state_hash_file.parent.is_dir():
        state_hash_file.write_text(f"{digest}\n", encoding="utf-8")

    if not has_queue_work and not human_updates:
        print(f"SKIP:NO_ACTIONABLE_WORK (sha256={digest})")
        return skip_code

    actionable = {
        "sha256": digest,
        "ready_issues": [{"number": i["number"], "title": i["title"]} for i in ready_raw],
        "open_prs": [{"number": p["number"], "title": p["title"]} for p in open_prs_raw],
        "human_updates": human_updates,
    }
    print(f"RUN:WORK_READY (sha256={digest}) {json.dumps(actionable, separators=(',', ':'))}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or exc.stdout or str(exc)).strip().replace("\n", " ")
        print(f"SKIP:ERROR ({err})", file=sys.stderr)
        raise SystemExit(1)
