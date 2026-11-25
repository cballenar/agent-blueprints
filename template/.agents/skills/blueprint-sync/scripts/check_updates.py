#!/usr/bin/env python3
"""Compare local AGENTS.md, rules, and skills against upstream agent-blueprints by file version."""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

DEFAULT_UPSTREAM_REPO = "cballenar/agent-blueprints"
DEFAULT_UPSTREAM_REF = "main"
TEMPLATE_PREFIX = "template/"

HTML_VERSION_RE = re.compile(r"<!--\s*version:\s*([0-9]+(?:\.[0-9]+)*)\s*-->", re.IGNORECASE)
YAML_VERSION_RE = re.compile(r"^version:\s*['\"]?([0-9]+(?:\.[0-9]+)*)['\"]?\s*$", re.MULTILINE)


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


def _parse_version(text: str, rel_path: str) -> str | None:
    if rel_path.endswith("SKILL.md"):
        if text.startswith("---"):
            end = text.find("\n---", 3)
            frontmatter = text[:end] if end != -1 else text[:400]
            match = YAML_VERSION_RE.search(frontmatter)
            if match:
                return match.group(1)
    match = HTML_VERSION_RE.search(text[:500])
    return match.group(1) if match else None


def _version_tuple(ver: str) -> tuple[int, ...]:
    return tuple(int(part) for part in ver.split("."))


def _fetch_tree(repo: str, ref: str) -> list[str]:
    raw = _run(["gh", "api", f"repos/{repo}/git/trees/{ref}?recursive=1"])
    data = json.loads(raw)
    return [
        item["path"].removeprefix(TEMPLATE_PREFIX)
        for item in data.get("tree", [])
        if item.get("type") == "blob" and item.get("path", "").startswith(TEMPLATE_PREFIX)
    ]


def _fetch_file(repo: str, ref: str, rel_path: str) -> str:
    raw = _run(["gh", "api", f"repos/{repo}/contents/{TEMPLATE_PREFIX}{rel_path}?ref={ref}"])
    payload = json.loads(raw)
    content = payload.get("content", "")
    return base64.b64decode(content).decode("utf-8")


def _is_versioned_target(rel_path: str) -> bool:
    return (
        rel_path == "AGENTS.md"
        or rel_path.startswith(".agents/rules/") and rel_path.endswith(".md")
        or rel_path.startswith(".agents/skills/") and rel_path.endswith("/SKILL.md")
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare local blueprint files against upstream by file-level version."
    )
    parser.add_argument("--repo", default=DEFAULT_UPSTREAM_REPO, help="Upstream owner/repo.")
    parser.add_argument("--ref", default=DEFAULT_UPSTREAM_REF, help="Upstream branch or SHA.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = _repo_root()
    upstream_files = _fetch_tree(args.repo, args.ref)
    targets = sorted(path for path in upstream_files if _is_versioned_target(path))

    results: list[dict[str, Any]] = []
    for rel_path in targets:
        upstream_text = _fetch_file(args.repo, args.ref, rel_path)
        upstream_ver = _parse_version(upstream_text, rel_path)
        local_path = root / rel_path

        if not local_path.is_file():
            results.append(
                {
                    "file": rel_path,
                    "status": "NEW",
                    "local_version": None,
                    "upstream_version": upstream_ver,
                }
            )
            continue

        local_text = local_path.read_text(encoding="utf-8")
        local_ver = _parse_version(local_text, rel_path)

        if not local_ver or not upstream_ver:
            status = "UNVERSIONED"
        elif _version_tuple(upstream_ver) > _version_tuple(local_ver):
            status = "OUTDATED"
        elif _version_tuple(upstream_ver) == _version_tuple(local_ver):
            status = "UP_TO_DATE"
        else:
            status = "AHEAD"

        results.append(
            {
                "file": rel_path,
                "status": status,
                "local_version": local_ver,
                "upstream_version": upstream_ver,
            }
        )

    print(json.dumps({"upstream": f"{args.repo}@{args.ref}", "files": results}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or exc.stdout or str(exc)).strip().replace("\n", " ")
        print(f"SYNC_CHECK_ERROR: {err}", file=sys.stderr)
        raise SystemExit(1)
