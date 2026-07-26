#!/usr/bin/env python3
"""Golden-chain agent dispatch report contract gate (SO-REPORT-CONTRACT).

2026-07-25 finding: seven dispatched agents returned bare acknowledgements
(``"Done."``, ``"Task complete."``, ``"No further action taken."``) in place
of a typed final result, and one filled a required 4-field schema with the
literal string ``"test"`` in every field -- which VALIDATED, because the
schema in use checked shape only. This script closes that gap the same way
``check_preregistration_timing.py`` and ``check_contamination_gate.py`` close
their seams: a typed pydantic contract per role
(``steel_onslaught.contracts.dispatch_report``) for the self-contained
checks (verdict is a closed enum, ``pr_number`` is a positive int, free text
is rejected on placeholder/bare-ack patterns and on under-length filler),
plus a second pass here for the checks that need live repo state -- a git
SHA field must resolve to a real commit, and artifact-path fields must
resolve, *and stay contained*, under ``--repo-root``, to files that actually
exist -- an artifact path that escapes the repo root (``../../../etc/hosts``,
or an absolute path such as ``/etc/hosts``) is rejected even if it resolves
to a real file on disk.

Usage
-----
    uv run python scripts/check_report_contract.py \\
        --role implementer \\
        --report path/to/report.json \\
        --git-dir path/to/repo/.git \\
        --repo-root path/to/repo

``--role`` selects which of the four closed contracts
(``implementer``/``verifier``/``lander``/``scout``) the report is validated
against; a report whose own ``role`` field disagrees fails the pydantic
Literal check (a report cannot be silently re-labeled by the CLI flag).

Exit codes
----------
0   the report parses against the selected role's typed contract AND every
    content anchor field it carries resolves against the provided
    ``--git-dir``/``--repo-root``.
1   any pydantic validation failure (bad shape, non-positive ``pr_number``,
    verdict outside the closed enum, placeholder/bare-acknowledgement/
    under-length free text) OR any content anchor fails to resolve OR a
    content-anchor-bearing field is present in the report but the context
    needed to check it was not supplied (fail-closed: an unchecked anchor
    is a failure, never a silent pass -- "optional input means the check
    does not exist").

Field-name-suffix convention (mirrors ``contracts/dispatch_report.py``): any
field ending ``_sha`` is checked via ``git cat-file -e`` in ``--git-dir``;
any field ending ``_paths`` (a list of strings) is resolved under
``--repo-root`` and checked both for containment (the resolved path must
stay under ``--repo-root``) and for existence. This is generic over all four
current roles and any future role added to ``ROLE_TO_MODEL`` without
touching this script.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from pydantic import BaseModel, ValidationError

from steel_onslaught.contracts.dispatch_report import ROLE_TO_MODEL, SODispatchRole


class ReportContractError(Exception):
    """Raised for any fail-closed condition surfaced as a single top-level error."""


def _load_report_text(path: Path) -> str:
    """Read and shallow-validate the report file, returning its raw JSON text.

    The raw text (not a pre-parsed dict) is what gets handed to
    ``model_cls.model_validate_json`` below -- these report contracts are
    strict pydantic models (``ConfigDict(strict=True)``, the repo-wide
    convention), and pydantic's strict *python*-mode validation requires an
    actual ``Enum`` instance for enum fields, rejecting the plain string a
    JSON file naturally deserializes to. JSON-mode validation
    (``model_validate_json``) is the documented, correct pydantic v2 path for
    external JSON input under strict models and accepts the plain string.
    """
    if not path.exists():
        raise ReportContractError(f"report file not found: {path}")
    text = path.read_text(encoding="utf-8")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ReportContractError(f"{path}: invalid JSON ({exc})") from exc
    if not isinstance(parsed, dict):
        raise ReportContractError(f"{path}: report must be a JSON object")
    return text


def _sha_resolves(git_dir: Path, sha: str) -> bool:
    result = subprocess.run(
        ["git", "--git-dir", str(git_dir), "cat-file", "-e", sha],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def check_content_anchors(
    report: BaseModel, *, git_dir: Path | None, repo_root: Path | None
) -> list[str]:
    """Return SPECIFIC violation strings for every content-anchor field on
    ``report`` that fails to resolve (or whose required context was not
    provided). ``[]`` means every anchor on this report checked out.
    """
    violations: list[str] = []
    for field_name in type(report).model_fields:
        value = getattr(report, field_name)
        if field_name.endswith("_sha"):
            if value is None:
                continue
            if git_dir is None:
                violations.append(
                    f"field '{field_name}' is a git-SHA content anchor ({value!r}) but "
                    "--git-dir was not provided -- an unchecked anchor is a fail-closed violation"
                )
                continue
            if not git_dir.exists():
                violations.append(f"--git-dir does not exist: {git_dir}")
                continue
            if not _sha_resolves(git_dir, str(value)):
                violations.append(
                    f"field '{field_name}' SHA {value!r} does not resolve to a real commit "
                    f"in --git-dir {git_dir}"
                )
        elif field_name.endswith("_paths"):
            if not value:
                continue
            if repo_root is None:
                violations.append(
                    f"field '{field_name}' is an artifact-path content anchor ({value!r}) but "
                    "--repo-root was not provided -- an unchecked anchor is a fail-closed violation"
                )
                continue
            resolved_root = repo_root.resolve()
            for artifact in value:
                # Resolve BEFORE checking existence, and require the resolved
                # path to stay under resolved_root. Existence alone is not
                # containment: pathlib silently discards repo_root entirely
                # when `artifact` is itself absolute (`repo_root / "/etc/hosts"
                # == Path("/etc/hosts")`), and `../../../etc/hosts` walks out
                # via `..` segments -- both resolve to a real file outside the
                # repo and must never pass. `.resolve()` also follows
                # symlinks, so a committed symlink pointing outside the repo
                # is caught the same way.
                resolved_artifact = (repo_root / artifact).resolve()
                try:
                    resolved_artifact.relative_to(resolved_root)
                except ValueError:
                    violations.append(
                        f"field '{field_name}' cites an artifact path that escapes "
                        f"--repo-root {repo_root} (resolves to {resolved_artifact}): {artifact}"
                    )
                    continue
                if not resolved_artifact.exists():
                    violations.append(
                        f"field '{field_name}' cites an artifact path that does not exist under "
                        f"--repo-root {repo_root}: {artifact}"
                    )
    return violations


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--role",
        required=True,
        choices=[role.value for role in SODispatchRole],
        help="dispatch role the report is validated against",
    )
    parser.add_argument("--report", type=Path, required=True, help="path to the JSON report file")
    parser.add_argument(
        "--git-dir",
        type=Path,
        default=None,
        help="git dir used to resolve any '*_sha' content anchor field (e.g. <repo>/.git)",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="repo root used to resolve any '*_paths' artifact content anchor field",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    role = SODispatchRole(args.role)
    model_cls = ROLE_TO_MODEL[role]

    try:
        report_text = _load_report_text(args.report)
    except ReportContractError as exc:
        print(f"REPORT CONTRACT GATE FAILED (fail-closed) [{role.value}]: {exc}", file=sys.stderr)
        return 1

    try:
        report = model_cls.model_validate_json(report_text)
    except ValidationError as exc:
        print(f"REPORT CONTRACT GATE FAILED (fail-closed) [{role.value}]:", file=sys.stderr)
        for err in exc.errors():
            loc = ".".join(str(part) for part in err["loc"]) or "<root>"
            print(f"  x field '{loc}': {err['msg']}", file=sys.stderr)
        return 1

    git_dir = args.git_dir.resolve() if args.git_dir is not None else None
    repo_root = args.repo_root.resolve() if args.repo_root is not None else None
    anchor_violations = check_content_anchors(report, git_dir=git_dir, repo_root=repo_root)
    if anchor_violations:
        print(f"REPORT CONTRACT GATE FAILED (fail-closed) [{role.value}]:", file=sys.stderr)
        for violation in anchor_violations:
            print(f"  x {violation}", file=sys.stderr)
        return 1

    print(
        f"OK: {role.value} report at {args.report} satisfies the golden-chain report contract "
        f"(shape, closed-enum verdict, substantive free text, and every content anchor resolved)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
