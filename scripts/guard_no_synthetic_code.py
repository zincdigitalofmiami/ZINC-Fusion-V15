#!/usr/bin/env python3
"""
ZINC-FUSION-V15 Guardrail: No Synthetic/Placeholder Code

This is a repo-level regression check that fails if known "synthetic/placeholder"
code patterns reappear in `scripts/` or `src/`.

It does NOT inspect database contents.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PatternCheck:
    regex: re.Pattern[str]
    description: str


CHECKS: list[PatternCheck] = [
    PatternCheck(re.compile(r"backfill_placeholder"), "placeholder backfill marker"),
    PatternCheck(
        re.compile(r"Historical placeholder - neutral sentiment"),
        "historical placeholder headline",
    ),
    PatternCheck(
        re.compile(r"hash\\(str\\([^\\n]*date[^\\n]*\\)\\)\\s*%\\s*100"),
        "hash-mod synthetic counts",
    ),
    PatternCheck(
        re.compile(r"""df\\s*\\[\\s*["']adx_14["']\\s*\\]\\s*=\\s*50(?:\\.0)?\\b"""),
        "ADX placeholder constant",
    ),
    PatternCheck(
        re.compile(r"""df\\s*\\[\\s*["']mfi_14["']\\s*\\]\\s*=\\s*50(?:\\.0)?\\b"""),
        "MFI placeholder constant",
    ),
]


def iter_python_files(root: Path) -> list[Path]:
    paths: list[Path] = []
    for folder in ("scripts", "src"):
        base = root / folder
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if path.name.startswith("."):
                continue
            if path.name == "guard_no_synthetic_code.py":
                continue
            paths.append(path)
    return sorted(paths)


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    offenders: list[str] = []

    for path in iter_python_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="replace")

        lines = text.splitlines()

        for check in CHECKS:
            for line_no, line in enumerate(lines, start=1):
                if check.regex.search(line):
                    offenders.append(
                        f"{path.relative_to(root)}:{line_no} {check.description}: {line.strip()}"
                    )

    if offenders:
        print("FAILED: synthetic/placeholder code patterns detected:\n")
        for item in offenders:
            print(f"  - {item}")
        return 1

    print("OK: no synthetic/placeholder code patterns detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
