#!/usr/bin/env python3
"""Validate agent skill markdown files in this repository."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
LOCAL_LINK_RE = re.compile(r"\]\(([^)#?][^)]*)\)")


def parse_frontmatter(text: str) -> dict[str, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError("missing YAML frontmatter")

    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required; run cloud-agent-install.sh first") from exc

    data = yaml.safe_load(match.group(1))
    if not isinstance(data, dict):
        raise ValueError("frontmatter must be a mapping")

    return {str(key): "" if value is None else str(value) for key, value in data.items()}


def validate_skill(skill_path: Path) -> list[str]:
    errors: list[str] = []
    text = skill_path.read_text(encoding="utf-8")

    try:
        frontmatter = parse_frontmatter(text)
    except (ValueError, RuntimeError) as exc:
        return [f"{skill_path.relative_to(ROOT)}: {exc}"]

    for field in ("name", "description"):
        if not frontmatter.get(field, "").strip():
            errors.append(f"{skill_path.relative_to(ROOT)}: frontmatter missing '{field}'")

    skill_dir = skill_path.parent
    for match in LOCAL_LINK_RE.finditer(text):
        target = match.group(1).strip()
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        resolved = (skill_dir / target).resolve()
        if not resolved.is_file():
            errors.append(
                f"{skill_path.relative_to(ROOT)}: broken local link '{target}'"
            )

    return errors


def main() -> int:
    skill_files = sorted(ROOT.glob("*/SKILL.md"))
    if not skill_files:
        print("ERROR: no */SKILL.md files found", file=sys.stderr)
        return 1

    errors: list[str] = []
    for skill_path in skill_files:
        errors.extend(validate_skill(skill_path))

    if errors:
        print("Skill validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(f"Validated {len(skill_files)} skill(s):")
    for skill_path in skill_files:
        frontmatter = parse_frontmatter(skill_path.read_text(encoding="utf-8"))
        print(f"  - {skill_path.parent.name}: {frontmatter['name']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
