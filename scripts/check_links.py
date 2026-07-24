#!/usr/bin/env python3
"""Check that relative Markdown links resolve to real files. stdlib only.

Skips external links (http/https/mailto) and pure #anchors. Used by CI and
runnable locally: `python3 scripts/check_links.py`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LINK_RE = re.compile(r"\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def is_external(target: str) -> bool:
    return target.startswith(("http://", "https://", "mailto:", "#"))


def main() -> int:
    broken: list[tuple[Path, str]] = []
    for md in sorted(REPO_ROOT.rglob("*.md")):
        if ".git" in md.parts:
            continue
        text = md.read_text(encoding="utf-8")
        for match in LINK_RE.finditer(text):
            target = match.group(1)
            if is_external(target):
                continue
            path_part = target.split("#", 1)[0]
            if not path_part:  # pure anchor within the same file
                continue
            resolved = (md.parent / path_part).resolve()
            if not resolved.exists():
                broken.append((md.relative_to(REPO_ROOT), target))

    if broken:
        print(f"FAIL: {len(broken)} broken relative link(s):")
        for src, target in broken:
            print(f"  - {src}: {target}")
        return 1
    print("OK: all relative Markdown links resolve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
