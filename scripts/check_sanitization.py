#!/usr/bin/env python3
"""Forward-blocking sanitization gate for the PUBLIC steel_onslaught repo.

This repo is public. A single direct push to ``main`` (the repo's normal solo
workflow) can leak developer-machine and private-network detail into a public
commit with no chance to walk it back. This gate detects that leakage class in
tracked content BEFORE it is committed (pre-commit hook) and again in CI
(``sanitize-text`` job), so neither path can land a leak silently.

Detected leak classes
---------------------
* Absolute developer-machine paths (``/Users/...`` and ``/Volumes/...``) — these
  break portability (`uv sync` on any other machine/CI runner) and expose the
  author's local layout.
* Tailscale CGNAT tailnet IPs (``100.64.0.0/10``) — private mesh addresses that
  are meaningless (and revealing) off the author's tailnet.
* Private LAN IPs (``192.168.0.0/16``) — internal lab addresses.
* Embedded ``ssh user@host`` invocations — private-host operational recipes.

This is deliberately dependency-free (stdlib ``re`` only) so it runs under
pre-commit's own interpreter without the project's pydantic/pyyaml deps.

Allowlist
---------
Two mechanisms, both narrow and reviewable:

1. **Path allowlist** — a small glob set for files that legitimately carry a
   placeholder or that *define/test these very patterns* (they would otherwise
   self-flag). The gitignored local-endpoint overlay's committed EXAMPLE
   (``*.local.yaml.example``) and any real ``*.local.yaml`` (gitignored anyway)
   are exempt so their ``<placeholder-host>`` lines never trip the IP patterns.
2. **Per-line marker** — a line carrying ``# sanitize-ok`` is skipped. Reserved
   for docs/fixtures that must show a path/IP shape for illustration.

Modes
-----
``check_sanitization.py FILE [FILE ...]``   scan explicit files (pre-commit passes
                                            the staged file set here).
``check_sanitization.py --all``             scan every tracked text file
                                            (``git ls-files``) — the CI mode.

With neither argument the gate defaults to ``--all``.

Exit code is non-zero if any forbidden pattern is found; the offending file,
line number, and a description are printed so the author knows exactly what to
remove.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

# --- Forbidden-content patterns --------------------------------------------
# Each entry: (compiled pattern, human description). Kept as literals so a
# reviewer can read exactly what is banned. The Tailscale entry uses the precise
# CGNAT block (100.64.0.0/10) rather than all of 100.0.0.0/8 so a stray legit
# ``100.x`` value in code cannot false-positive; only a full 4-octet address in
# the mesh range matches.
SANITIZATION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"/Users/"), "Absolute developer-machine path (/Users/...)"),
    (re.compile(r"/Volumes/"), "Absolute developer-machine path (/Volumes/...)"),
    (
        re.compile(r"\b100\.(?:6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.\d{1,3}\.\d{1,3}\b"),
        "Tailscale CGNAT tailnet IP (100.64.0.0/10)",
    ),
    (re.compile(r"\b192\.168\.\d{1,3}\.\d{1,3}\b"), "Private LAN IP (192.168.0.0/16)"),
    (
        re.compile(r"\bssh\s+[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+"),
        "Embedded ssh user@host invocation",
    ),
]

# Files exempt from file-walk scanning. THIS gate script and its test define/test
# the forbidden patterns as literals, so scanning them would self-flag; the
# ``*.local.yaml*`` entries cover the committed placeholder overlay example (and
# any real, gitignored overlay). Matched against the repo-relative POSIX path.
ALLOWLIST_PATH_GLOBS: tuple[str, ...] = (
    "scripts/check_sanitization.py",
    "tests/test_check_sanitization.py",
    "*.local.yaml",
    "*.local.yaml.example",
)

# Per-line escape hatch: a line carrying this marker is skipped.
_LINE_MARKER = "# sanitize-ok"

# Text extensions scanned in --all mode. The leak this gate exists to stop
# actually landed in ``uv.lock`` and ``pyproject.toml``, so ``.lock``/``.toml``
# are explicitly in scope, not just source.
_SCANNABLE_SUFFIXES: frozenset[str] = frozenset(
    {
        ".py",
        ".pyi",
        ".yaml",
        ".yml",
        ".toml",
        ".lock",
        ".md",
        ".txt",
        ".json",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".sql",
        ".ini",
        ".cfg",
        ".sh",
        ".html",
        ".css",
        ".example",
    }
)


def is_path_allowlisted(rel_path: str) -> bool:
    """True if ``rel_path`` (repo-relative POSIX) matches an allowlist glob."""
    p = PurePosixPath(rel_path)
    for glob in ALLOWLIST_PATH_GLOBS:
        if p.match(glob):
            return True
    return False


def scan_text(text: str, *, label: str = "text") -> list[str]:
    """Scan ``text`` for forbidden patterns, honoring the per-line marker.

    Returns one error string per offending line, prefixed with ``label`` and the
    1-indexed line number. Lines carrying ``# sanitize-ok`` are skipped.
    """
    errors: list[str] = []
    for i, line in enumerate(text.splitlines(), 1):
        if _LINE_MARKER in line:
            continue
        for pattern, description in SANITIZATION_PATTERNS:
            if pattern.search(line):
                errors.append(f"{label}:{i}: {description} — matches /{pattern.pattern}/")
                break  # one error per line
    return errors


def scan_file(rel_path: str) -> list[str]:
    """Scan a single tracked file, applying the path allowlist first."""
    if is_path_allowlisted(rel_path):
        return []
    try:
        content = Path(rel_path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # Unreadable or binary — nothing to scan.
        return []
    return scan_text(content, label=rel_path)


def _tracked_files() -> list[str]:
    """Return repo-relative POSIX paths of all tracked files (``git ls-files``)."""
    out = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [line for line in out.splitlines() if line]


def _scannable(rel_path: str) -> bool:
    suffix = PurePosixPath(rel_path).suffix
    return suffix in _SCANNABLE_SUFFIXES


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", help="Explicit files to scan (pre-commit mode)")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Scan every tracked text file via `git ls-files` (CI mode)",
    )
    args = parser.parse_args(argv)

    if args.files:
        targets = list(args.files)
    else:
        # No explicit files -> CI mode: walk the whole tracked tree.
        targets = [p for p in _tracked_files() if _scannable(p)]

    errors: list[str] = []
    for rel_path in targets:
        errors.extend(scan_file(rel_path))

    if errors:
        print("Sanitization gate FAILED — forbidden private content found:", file=sys.stderr)
        for err in errors:
            print(f"  x {err}", file=sys.stderr)
        print(
            "\nThis repo is PUBLIC. Remove absolute /Users//Volumes/ paths, "
            "Tailscale (100.64.0.0/10) and LAN (192.168.0.0/16) IP literals, and "
            "embedded `ssh user@host` recipes. For private endpoints use the "
            "gitignored *.local.yaml overlay (see providers.local.yaml.example). "
            "A line that must show a path/IP shape may carry `# sanitize-ok`.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
