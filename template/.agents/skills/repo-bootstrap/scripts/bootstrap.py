#!/usr/bin/env python3
"""Idempotent GitHub label and workspace bootstrapper for agent-blueprints."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

STATUS_LABELS: list[tuple[str, str, str]] = [
    ("status:ready", "0E8A16", "Approved and ready for agent or human pickup"),
    ("status:in-progress", "FBCA04", "Currently claimed and actively being worked"),
    ("status:needs-decision", "D93F0B", "Blocked on human decision or ambiguity"),
    ("status:human-spike", "5319E7", "Requires manual, physical, or human-only action"),
    ("status:blocked", "B60205", "Blocked by an upstream issue or dependency"),
]

DOMAIN_COLOR = "1D76DB"

PROJECT_SPEC_TEMPLATE = """# Project Specification

## Goal
<!-- 1-2 sentence summary of what this repository delivers. -->

## Architecture & Boundaries
<!-- Key components, external boundaries, and invariants. -->

## Verification
<!-- Exact commands required to verify changes before landing. -->
"""


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def _repo_root() -> Path:
    return Path(_run(["git", "rev-parse", "--show-toplevel"]))


def _check_gh_auth(repo_root: Path) -> str:
    _run(["gh", "auth", "status"], cwd=repo_root)
    return _run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
        cwd=repo_root,
    )


def _sync_label(
    repo_root: Path,
    name: str,
    color: str,
    description: str,
    dry_run: bool,
) -> dict[str, Any]:
    cmd = [
        "gh",
        "label",
        "create",
        name,
        "--color",
        color,
        "--description",
        description,
        "--force",
    ]
    if not dry_run:
        _run(cmd, cwd=repo_root)
    return {"name": name, "color": color, "action": "would_sync" if dry_run else "synced"}


def _ensure_spec(repo_root: Path, dry_run: bool) -> str:
    spec_path = repo_root / "PROJECT_SPEC.md"
    if spec_path.exists():
        return "exists"
    if not dry_run:
        spec_path.write_text(PROJECT_SPEC_TEMPLATE, encoding="utf-8")
        return "created"
    return "would_create"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap GitHub status/domain labels and PROJECT_SPEC.md."
    )
    parser.add_argument(
        "--domains",
        default="",
        help="Comma-separated domain names to create as domain:<name> labels.",
    )
    parser.add_argument(
        "--no-spec",
        action="store_true",
        help="Skip creating PROJECT_SPEC.md if missing.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate git/gh access and print planned changes without mutating.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = _repo_root()
    name_with_owner = _check_gh_auth(repo_root)

    labels_to_sync = list(STATUS_LABELS)
    for raw in args.domains.split(","):
        domain = raw.strip().removeprefix("domain:")
        if domain:
            labels_to_sync.append((f"domain:{domain}", DOMAIN_COLOR, f"Workstream: {domain}"))

    synced_labels = [
        _sync_label(repo_root, name, color, desc, args.dry_run)
        for name, color, desc in labels_to_sync
    ]

    spec_status = "skipped" if args.no_spec else _ensure_spec(repo_root, args.dry_run)

    summary = {
        "repo": name_with_owner,
        "root": str(repo_root),
        "dry_run": args.dry_run,
        "labels": synced_labels,
        "project_spec": spec_status,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or exc.stdout or str(exc)).strip().replace("\n", " ")
        print(f"BOOTSTRAP_ERROR: {err}", file=sys.stderr)
        raise SystemExit(1)
