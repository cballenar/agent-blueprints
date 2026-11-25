#!/usr/bin/env python3
"""Phase 0 concurrency, lease recovery, and SHA-256 GitHub queue hash gate (project-agnostic)."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

AGENT_COMMENT_PREFIXES = ("**[Agent]**", "[Agent]")
SKIP_EXIT_CODE = 10
DEFAULT_LEASE_TTL = 1800  # 30 minutes


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


def _git_common_dir(repo_root: Path) -> Path:
    raw = Path(_run(["git", "rev-parse", "--git-common-dir"], cwd=repo_root))
    return raw if raw.is_absolute() else (repo_root / raw).resolve()


def _parse_iso_epoch(ts: str | None) -> float:
    if not ts:
        return 0.0
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _latest_local_activity(repo_root: Path, git_dir: Path, dirty_status: str) -> float:
    latest = 0.0
    try:
        latest = max(latest, float(_run(["git", "log", "-1", "--format=%ct"], cwd=repo_root) or 0))
    except subprocess.CalledProcessError:
        pass

    index_file = git_dir / "index"
    if index_file.exists():
        latest = max(latest, index_file.stat().st_mtime)

    for line in dirty_status.splitlines():
        rel = line[3:].strip().split(" -> ")[-1].strip('"')
        candidate = repo_root / rel
        if candidate.exists():
            latest = max(latest, candidate.stat().st_mtime)
    return latest


def _read_lease(lease_file: Path) -> dict[str, Any] | None:
    if not lease_file.is_file():
        return None
    try:
        return json.loads(lease_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_lease(lease_file: Path, ttl_seconds: int, mode: str) -> None:
    if lease_file.parent.is_dir():
        payload = {
            "started_at": int(time.time()),
            "ttl_seconds": ttl_seconds,
            "mode": mode,
        }
        lease_file.write_text(f"{json.dumps(payload)}\n", encoding="utf-8")


def _clear_lease(lease_file: Path) -> None:
    if lease_file.is_file():
        lease_file.unlink(missing_ok=True)


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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Phase 0 concurrency, lease recovery & SHA-256 GitHub queue gate."
    )
    parser.add_argument(
        "--exit-code",
        action="store_true",
        help="Exit 10 on SKIP:* so shell/cron wrappers can gate agent launch with '&&'.",
    )
    parser.add_argument(
        "--lease-ttl",
        type=int,
        default=DEFAULT_LEASE_TTL,
        help=f"Seconds of inactivity before a leased lock becomes recoverable (default: {DEFAULT_LEASE_TTL}).",
    )
    args = parser.parse_args()
    skip_code = SKIP_EXIT_CODE if args.exit_code else 0
    now = time.time()

    repo_root = _repo_root()
    git_dir = _git_common_dir(repo_root)
    state_hash_file = git_dir / "preflight_state.sha256"
    lease_file = git_dir / "dispatcher_lease.json"

    # 1. Concurrency & Stale-Lease Check
    branch = _run(["git", "branch", "--show-current"], cwd=repo_root)
    dirty_status = _run(["git", "status", "--porcelain"], cwd=repo_root)
    in_progress = _run_json(
        [
            "gh", "issue", "list", "--state", "open",
            "--label", "status:in-progress",
            "--json", "number,title,updatedAt",
        ],
        cwd=repo_root,
    )

    local_locked = branch != "main" or bool(dirty_status)
    remote_locked = bool(in_progress)
    lease = _read_lease(lease_file)

    if not local_locked and not remote_locked:
        _clear_lease(lease_file)
    else:
        reasons: list[str] = []
        if branch != "main":
            reasons.append(f"branch={branch} != main")
        if dirty_status:
            reasons.append("dirty working tree")
        if in_progress:
            nums = ",".join(f"#{i['number']}" for i in in_progress)
            reasons.append(f"in-progress issues: {nums}")
        reason_str = "; ".join(reasons)

        # Never clobber local git state if no autonomous lease exists (protects human interactive work).
        if local_locked and lease is None:
            print(f"SKIP:BUSY (unleased local state: {reason_str})")
            return skip_code

        ttl = int((lease or {}).get("ttl_seconds") or args.lease_ttl)
        last_touch = float((lease or {}).get("started_at") or 0.0)
        if local_locked:
            last_touch = max(last_touch, _latest_local_activity(repo_root, git_dir, dirty_status))
        for issue in in_progress:
            last_touch = max(last_touch, _parse_iso_epoch(issue.get("updatedAt")))

        age = int(max(0.0, now - last_touch)) if last_touch > 0 else ttl
        if age < ttl:
            print(f"SKIP:BUSY ({reason_str}; active {age}s < {ttl}s TTL)")
            return skip_code

        _write_lease(lease_file, args.lease_ttl, mode="recover")
        recovery_payload = {
            "age_seconds": age,
            "branch": branch,
            "dirty": bool(dirty_status),
            "in_progress_issues": [
                {"number": i["number"], "title": i.get("title", "")} for i in in_progress
            ],
        }
        print(
            f"RUN:RECOVER_STALE (age={age}s) "
            f"{json.dumps(recovery_payload, separators=(',', ':'))}"
        )
        return 0

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

    _write_lease(lease_file, args.lease_ttl, mode="work")
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
