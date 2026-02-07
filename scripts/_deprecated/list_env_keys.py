#!/usr/bin/env python3
"""List all environment variable keys referenced in the codebase.

Scans Python (.py), TypeScript (.ts/.tsx), JavaScript (.js/.mjs), and shell (.sh)
files for patterns like os.getenv("X"), process.env.X, $X, etc.
Skips .venv, node_modules, and __pycache__ directories.
"""

import os
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {
    ".venv", "node_modules", "__pycache__", ".git", "AutogluonModels",
    ".next", "data", "models", "logs", ".tmp",
}

EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".mjs", ".sh", ".env"}

# Patterns to match env var references
PATTERNS = [
    # Python: os.getenv("FOO"), os.environ["FOO"], os.environ.get("FOO")
    re.compile(r'os\.(?:getenv|environ\.get|environ\[)\s*\(\s*["\'](\w+)["\']'),
    re.compile(r'os\.environ\[["\'](\w+)["\']\]'),
    # TypeScript/JS: process.env.FOO
    re.compile(r'process\.env\.(\w+)'),
    # Shell: $FOO or ${FOO}
    re.compile(r'\$\{?([A-Z_][A-Z0-9_]+)\}?'),
    # dotenv: KEY=value lines in .env files
    re.compile(r'^([A-Z_][A-Z0-9_]+)=', re.MULTILINE),
]


def scan_file(filepath: Path) -> set[str]:
    """Extract env var names from a file."""
    try:
        text = filepath.read_text(errors="ignore")
    except Exception:
        return set()
    
    keys = set()
    for pattern in PATTERNS:
        keys.update(pattern.findall(text))
    
    # Filter out common false positives
    noise = {"HOME", "PATH", "USER", "SHELL", "PWD", "TERM", "LANG", "TMPDIR"}
    return keys - noise


def main():
    env_keys: dict[str, list[str]] = defaultdict(list)
    
    for root, dirs, files in os.walk(REPO_ROOT):
        # Prune skipped directories
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        
        for fname in files:
            fpath = Path(root) / fname
            if fpath.suffix not in EXTENSIONS:
                continue
            
            keys = scan_file(fpath)
            rel = fpath.relative_to(REPO_ROOT)
            for key in keys:
                env_keys[key].append(str(rel))
    
    if not env_keys:
        print("No environment variable references found.")
        return
    
    print(f"{'ENV KEY':<40} {'FILES'}")
    print("-" * 80)
    for key in sorted(env_keys.keys()):
        files = sorted(set(env_keys[key]))
        print(f"{key:<40} {files[0]}")
        for f in files[1:]:
            print(f"{'':40} {f}")
    
    print(f"\n--- {len(env_keys)} unique env keys across {sum(len(v) for v in env_keys.values())} references ---")


if __name__ == "__main__":
    main()
