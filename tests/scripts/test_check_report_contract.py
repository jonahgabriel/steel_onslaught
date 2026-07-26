"""Golden-chain agent dispatch report contract gate (SO-REPORT-CONTRACT) --
real RED and GREEN cases per dispatch role.

Builds a throwaway real git repo (for every ``*_sha`` content anchor -- an
actual commit whose SHA either does or does not appear in the fixture repo's
history) and real files on disk under a real ``--repo-root`` (for every
``*_paths`` content anchor), then drives the real
``scripts.check_report_contract.main`` entrypoint end to end -- no mocks, no
stubbing of ``git`` or the filesystem. Every RED case is a seeded fixture
proving the gate actually fires through the real validation path, mirroring
the seeded-RED bar set by ``test_check_preregistration_timing.py`` and
``test_check_contamination_gate.py``.

Mandatory RED cases (one set per applicable role, per the 2026-07-25
directive this gate exists to satisfy):

* the bare ``"Done."`` report,
* the literal-``"test"`` placeholder fill across every string field,
* a well-shaped report whose SHA does not resolve to a real commit,
* a well-shaped report citing a nonexistent artifact path,
* a content-anchor field present with the checking context
  (``--git-dir``/``--repo-root``) withheld -- fail-closed, never a silent
  pass.

Plus one realistic GREEN case per role.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.check_report_contract import check_content_anchors, main
from steel_onslaught.contracts.dispatch_report import (
    ModelSOImplementerReport,
    validate_substantive_report_text,
)

pytestmark = pytest.mark.integration


# --------------------------------------------------------------------------
# Fixture helpers -- real git repo, real files, real report JSON on disk
# --------------------------------------------------------------------------


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")


def _commit_file(repo: Path, relpath: str, content: str) -> str:
    """Write and commit ``relpath`` inside ``repo``; return the new commit sha."""
    path = repo / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _git(repo, "add", relpath)
    _git(repo, "commit", "-q", "-m", f"commit {relpath}")
    return _git(repo, "log", "-1", "--format=%H").strip()


def _write_report(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


_SUBSTANTIVE_SUMMARY = (
    "Implemented the golden-chain report contract module and CLI validator, "
    "added seeded RED/GREEN tests per role, and confirmed ruff/mypy/pytest "
    "all pass locally before opening the PR."
)


# --------------------------------------------------------------------------
# validate_substantive_report_text -- pure unit-level (real code path)
# --------------------------------------------------------------------------


def test_validate_substantive_report_text_accepts_real_prose() -> None:
    assert validate_substantive_report_text(_SUBSTANTIVE_SUMMARY) == _SUBSTANTIVE_SUMMARY


def test_validate_substantive_report_text_accepts_prose_that_mentions_the_word_test() -> None:
    """A real report that legitimately uses the word 'test' in a sentence must
    never be flagged -- placeholder matching is exact-literal, not substring.
    """
    text = "Ran the full integration test suite locally; all 214 tests passed before push."
    assert validate_substantive_report_text(text) == text


@pytest.mark.parametrize(
    "literal", ["test", "TEST", "Test.", "  test  ", "todo", "placeholder", "lorem ipsum"]
)
def test_validate_substantive_report_text_rejects_placeholder_literals(literal: str) -> None:
    with pytest.raises(ValueError, match="placeholder"):
        validate_substantive_report_text(literal)


@pytest.mark.parametrize(
    "literal",
    ["Done.", "done", "Task complete.", "No further action taken.", "Finished", "ok."],
)
def test_validate_substantive_report_text_rejects_bare_acknowledgements(literal: str) -> None:
    with pytest.raises(ValueError, match="bare acknowledgement"):
        validate_substantive_report_text(literal)


def test_validate_substantive_report_text_rejects_under_length_filler() -> None:
    with pytest.raises(ValueError, match="too short"):
        validate_substantive_report_text("Fixed the bug, all good now.")  # 29 chars


def test_validate_substantive_report_text_rejects_empty() -> None:
    with pytest.raises(ValueError, match="empty or whitespace-only"):
        validate_substantive_report_text("   ")


# --------------------------------------------------------------------------
# check_content_anchors -- unit-level, real git repo + real filesystem
# --------------------------------------------------------------------------


def test_check_content_anchors_fails_closed_when_git_dir_withheld(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    sha = _commit_file(repo, "a.txt", "x\n")
    report = ModelSOImplementerReport.model_validate_json(
        json.dumps(
            {
                "role": "implementer",
                "pr_number": 1,
                "branch": "b",
                "head_sha": sha,
                "verdict": "implemented",
                "files_changed_paths": ["a.txt"],
                "summary": _SUBSTANTIVE_SUMMARY,
            }
        )
    )
    violations = check_content_anchors(report, git_dir=None, repo_root=repo)
    assert any("head_sha" in v and "--git-dir was not provided" in v for v in violations)


def test_check_content_anchors_all_clean_on_real_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    sha = _commit_file(repo, "a.txt", "x\n")
    report = ModelSOImplementerReport.model_validate_json(
        json.dumps(
            {
                "role": "implementer",
                "pr_number": 1,
                "branch": "b",
                "head_sha": sha,
                "verdict": "implemented",
                "files_changed_paths": ["a.txt"],
                "summary": _SUBSTANTIVE_SUMMARY,
            }
        )
    )
    violations = check_content_anchors(report, git_dir=repo / ".git", repo_root=repo)
    assert violations == []


# --------------------------------------------------------------------------
# main() -- implementer role
# --------------------------------------------------------------------------


def test_main_passes_for_a_realistic_implementer_report(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    sha = _commit_file(repo, "scripts/check_report_contract.py", "# fixture\n")
    report_path = _write_report(
        tmp_path / "report.json",
        {
            "role": "implementer",
            "pr_number": 4821,
            "branch": "jonah/so-report-contracts-golden",
            "head_sha": sha,
            "verdict": "implemented",
            "files_changed_paths": ["scripts/check_report_contract.py"],
            "summary": _SUBSTANTIVE_SUMMARY,
        },
    )
    exit_code = main(
        [
            "--role",
            "implementer",
            "--report",
            str(report_path),
            "--git-dir",
            str(repo / ".git"),
            "--repo-root",
            str(repo),
        ]
    )
    assert exit_code == 0


def test_main_fails_on_bare_done_report_implementer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Mandatory seeded RED: the exact 2026-07-25 failure mode."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    sha = _commit_file(repo, "scripts/check_report_contract.py", "# fixture\n")
    report_path = _write_report(
        tmp_path / "report.json",
        {
            "role": "implementer",
            "pr_number": 4821,
            "branch": "jonah/so-report-contracts-golden",
            "head_sha": sha,
            "verdict": "implemented",
            "files_changed_paths": ["scripts/check_report_contract.py"],
            "summary": "Done.",
        },
    )
    exit_code = main(
        [
            "--role",
            "implementer",
            "--report",
            str(report_path),
            "--git-dir",
            str(repo / ".git"),
            "--repo-root",
            str(repo),
        ]
    )
    err = capsys.readouterr().err
    assert exit_code == 1
    assert "bare acknowledgement" in err


def test_main_fails_on_literal_test_placeholder_fill_implementer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Mandatory seeded RED: the worst class from the directive -- every
    string field filled with the literal word 'test'. This must fail on
    MULTIPLE independent grounds (verdict outside the closed enum, SHA shape,
    placeholder summary), proving shape-only validation cannot let it through.
    """
    report_path = _write_report(
        tmp_path / "report.json",
        {
            "role": "test",
            "pr_number": 1,
            "branch": "test",
            "head_sha": "test",
            "verdict": "test",
            "files_changed_paths": ["test"],
            "summary": "test",
        },
    )
    exit_code = main(["--role", "implementer", "--report", str(report_path)])
    err = capsys.readouterr().err
    assert exit_code == 1
    assert "field 'role'" in err
    assert "field 'verdict'" in err
    assert "field 'head_sha'" in err
    assert "placeholder value 'test'" in err


def test_main_fails_when_head_sha_does_not_resolve_implementer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Mandatory seeded RED: well-shaped report, but the cited SHA is not a
    real commit in the provided --git-dir (a fabricated/invented hash).
    """
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "scripts/check_report_contract.py", "# fixture\n")
    fabricated_sha = "0" * 40
    report_path = _write_report(
        tmp_path / "report.json",
        {
            "role": "implementer",
            "pr_number": 4821,
            "branch": "jonah/so-report-contracts-golden",
            "head_sha": fabricated_sha,
            "verdict": "implemented",
            "files_changed_paths": ["scripts/check_report_contract.py"],
            "summary": _SUBSTANTIVE_SUMMARY,
        },
    )
    exit_code = main(
        [
            "--role",
            "implementer",
            "--report",
            str(report_path),
            "--git-dir",
            str(repo / ".git"),
            "--repo-root",
            str(repo),
        ]
    )
    err = capsys.readouterr().err
    assert exit_code == 1
    assert "does not resolve to a real commit" in err


def test_main_fails_when_artifact_path_does_not_exist_implementer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Mandatory seeded RED: well-shaped report citing an artifact path that
    does not exist under --repo-root (an invented file citation).
    """
    repo = tmp_path / "repo"
    _init_repo(repo)
    sha = _commit_file(repo, "scripts/check_report_contract.py", "# fixture\n")
    report_path = _write_report(
        tmp_path / "report.json",
        {
            "role": "implementer",
            "pr_number": 4821,
            "branch": "jonah/so-report-contracts-golden",
            "head_sha": sha,
            "verdict": "implemented",
            "files_changed_paths": ["scripts/this_file_was_never_written.py"],
            "summary": _SUBSTANTIVE_SUMMARY,
        },
    )
    exit_code = main(
        [
            "--role",
            "implementer",
            "--report",
            str(report_path),
            "--git-dir",
            str(repo / ".git"),
            "--repo-root",
            str(repo),
        ]
    )
    err = capsys.readouterr().err
    assert exit_code == 1
    assert "does not exist under --repo-root" in err
    assert "this_file_was_never_written.py" in err


def test_main_fails_closed_when_context_withheld_implementer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A perfectly well-shaped report with no --git-dir/--repo-root supplied
    must FAIL, not silently pass -- an unchecked content anchor is not a
    validated one.
    """
    repo = tmp_path / "repo"
    _init_repo(repo)
    sha = _commit_file(repo, "scripts/check_report_contract.py", "# fixture\n")
    report_path = _write_report(
        tmp_path / "report.json",
        {
            "role": "implementer",
            "pr_number": 4821,
            "branch": "jonah/so-report-contracts-golden",
            "head_sha": sha,
            "verdict": "implemented",
            "files_changed_paths": ["scripts/check_report_contract.py"],
            "summary": _SUBSTANTIVE_SUMMARY,
        },
    )
    exit_code = main(["--role", "implementer", "--report", str(report_path)])
    err = capsys.readouterr().err
    assert exit_code == 1
    assert "was not provided" in err


# --------------------------------------------------------------------------
# main() -- verifier role
# --------------------------------------------------------------------------


def test_main_passes_for_a_realistic_verifier_report(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    sha = _commit_file(repo, "docs/evidence/SO-9999.md", "# fixture evidence\n")
    report_path = _write_report(
        tmp_path / "report.json",
        {
            "role": "verifier",
            "pr_number": 4821,
            "verified_sha": sha,
            "verdict": "confirmed",
            "evidence_paths": ["docs/evidence/SO-9999.md"],
            "summary": (
                "Re-ran the seeded RED/GREEN suite against the pushed commit and confirmed "
                "every violation fires through the real validator, not a mock."
            ),
        },
    )
    exit_code = main(
        [
            "--role",
            "verifier",
            "--report",
            str(report_path),
            "--git-dir",
            str(repo / ".git"),
            "--repo-root",
            str(repo),
        ]
    )
    assert exit_code == 0


def test_main_fails_on_bare_ack_report_verifier(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    sha = _commit_file(repo, "docs/evidence/SO-9999.md", "# fixture evidence\n")
    report_path = _write_report(
        tmp_path / "report.json",
        {
            "role": "verifier",
            "pr_number": 4821,
            "verified_sha": sha,
            "verdict": "confirmed",
            "evidence_paths": ["docs/evidence/SO-9999.md"],
            "summary": "No further action taken.",
        },
    )
    exit_code = main(
        [
            "--role",
            "verifier",
            "--report",
            str(report_path),
            "--git-dir",
            str(repo / ".git"),
            "--repo-root",
            str(repo),
        ]
    )
    err = capsys.readouterr().err
    assert exit_code == 1
    assert "bare acknowledgement" in err


def test_main_fails_on_literal_test_placeholder_fill_verifier(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report_path = _write_report(
        tmp_path / "report.json",
        {
            "role": "test",
            "pr_number": 1,
            "verified_sha": "test",
            "verdict": "test",
            "evidence_paths": ["test"],
            "summary": "test",
        },
    )
    exit_code = main(["--role", "verifier", "--report", str(report_path)])
    err = capsys.readouterr().err
    assert exit_code == 1
    assert "field 'verdict'" in err
    assert "placeholder value 'test'" in err


def test_main_fails_when_verified_sha_does_not_resolve_verifier(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "docs/evidence/SO-9999.md", "# fixture evidence\n")
    report_path = _write_report(
        tmp_path / "report.json",
        {
            "role": "verifier",
            "pr_number": 4821,
            "verified_sha": "f" * 40,
            "verdict": "confirmed",
            "evidence_paths": ["docs/evidence/SO-9999.md"],
            "summary": (
                "Re-ran the seeded RED/GREEN suite against the pushed commit and confirmed "
                "every violation fires through the real validator, not a mock."
            ),
        },
    )
    exit_code = main(
        [
            "--role",
            "verifier",
            "--report",
            str(report_path),
            "--git-dir",
            str(repo / ".git"),
            "--repo-root",
            str(repo),
        ]
    )
    err = capsys.readouterr().err
    assert exit_code == 1
    assert "does not resolve to a real commit" in err


def test_main_fails_when_evidence_path_does_not_exist_verifier(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    sha = _commit_file(repo, "docs/evidence/SO-9999.md", "# fixture evidence\n")
    report_path = _write_report(
        tmp_path / "report.json",
        {
            "role": "verifier",
            "pr_number": 4821,
            "verified_sha": sha,
            "verdict": "confirmed",
            "evidence_paths": ["docs/evidence/SO-0000-never-written.md"],
            "summary": (
                "Re-ran the seeded RED/GREEN suite against the pushed commit and confirmed "
                "every violation fires through the real validator, not a mock."
            ),
        },
    )
    exit_code = main(
        [
            "--role",
            "verifier",
            "--report",
            str(report_path),
            "--git-dir",
            str(repo / ".git"),
            "--repo-root",
            str(repo),
        ]
    )
    err = capsys.readouterr().err
    assert exit_code == 1
    assert "does not exist under --repo-root" in err


# --------------------------------------------------------------------------
# main() -- lander role
# --------------------------------------------------------------------------


def test_main_passes_for_a_realistic_lander_report(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    sha = _commit_file(repo, "a.txt", "x\n")
    report_path = _write_report(
        tmp_path / "report.json",
        {
            "role": "lander",
            "pr_number": 4821,
            "merge_sha": sha,
            "verdict": "merged",
            "summary": (
                "Squash-merged PR #4821 into main after CI went green on the second push; "
                "no conflicts, no CodeRabbit threads outstanding."
            ),
        },
    )
    exit_code = main(
        ["--role", "lander", "--report", str(report_path), "--git-dir", str(repo / ".git")]
    )
    assert exit_code == 0


def test_main_fails_on_bare_ack_report_lander(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    sha = _commit_file(repo, "a.txt", "x\n")
    report_path = _write_report(
        tmp_path / "report.json",
        {
            "role": "lander",
            "pr_number": 4821,
            "merge_sha": sha,
            "verdict": "merged",
            "summary": "Task complete.",
        },
    )
    exit_code = main(
        ["--role", "lander", "--report", str(report_path), "--git-dir", str(repo / ".git")]
    )
    err = capsys.readouterr().err
    assert exit_code == 1
    assert "bare acknowledgement" in err


def test_main_fails_on_literal_test_placeholder_fill_lander(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report_path = _write_report(
        tmp_path / "report.json",
        {
            "role": "test",
            "pr_number": 1,
            "merge_sha": "test",
            "verdict": "test",
            "summary": "test",
        },
    )
    exit_code = main(["--role", "lander", "--report", str(report_path)])
    err = capsys.readouterr().err
    assert exit_code == 1
    assert "field 'verdict'" in err
    assert "placeholder value 'test'" in err


def test_main_fails_when_merge_sha_does_not_resolve_lander(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "a.txt", "x\n")
    report_path = _write_report(
        tmp_path / "report.json",
        {
            "role": "lander",
            "pr_number": 4821,
            "merge_sha": "1" * 40,
            "verdict": "merged",
            "summary": (
                "Squash-merged PR #4821 into main after CI went green on the second push; "
                "no conflicts, no CodeRabbit threads outstanding."
            ),
        },
    )
    exit_code = main(
        ["--role", "lander", "--report", str(report_path), "--git-dir", str(repo / ".git")]
    )
    err = capsys.readouterr().err
    assert exit_code == 1
    assert "does not resolve to a real commit" in err


# --------------------------------------------------------------------------
# main() -- scout role
# --------------------------------------------------------------------------


def test_main_passes_for_a_realistic_scout_report(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "src/steel_onslaught/contracts/incentive.py", "# fixture\n")
    report_path = _write_report(
        tmp_path / "report.json",
        {
            "role": "scout",
            "verdict": "found",
            "findings_paths": ["src/steel_onslaught/contracts/incentive.py"],
            "summary": (
                "Located the existing structural-incentive model this ticket should mirror "
                "for style: one BaseModel per concept, frozen+extra=forbid+strict config."
            ),
        },
    )
    exit_code = main(["--role", "scout", "--report", str(report_path), "--repo-root", str(repo)])
    assert exit_code == 0


def test_main_fails_on_bare_ack_report_scout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "src/steel_onslaught/contracts/incentive.py", "# fixture\n")
    report_path = _write_report(
        tmp_path / "report.json",
        {
            "role": "scout",
            "verdict": "found",
            "findings_paths": ["src/steel_onslaught/contracts/incentive.py"],
            "summary": "Done.",
        },
    )
    exit_code = main(["--role", "scout", "--report", str(report_path), "--repo-root", str(repo)])
    err = capsys.readouterr().err
    assert exit_code == 1
    assert "bare acknowledgement" in err


def test_main_fails_on_literal_test_placeholder_fill_scout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report_path = _write_report(
        tmp_path / "report.json",
        {
            "role": "test",
            "verdict": "test",
            "findings_paths": ["test"],
            "summary": "test",
        },
    )
    exit_code = main(["--role", "scout", "--report", str(report_path)])
    err = capsys.readouterr().err
    assert exit_code == 1
    assert "field 'verdict'" in err
    assert "placeholder value 'test'" in err


def test_main_fails_when_findings_path_does_not_exist_scout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "src/steel_onslaught/contracts/incentive.py", "# fixture\n")
    report_path = _write_report(
        tmp_path / "report.json",
        {
            "role": "scout",
            "verdict": "found",
            "findings_paths": ["src/steel_onslaught/contracts/does_not_exist.py"],
            "summary": (
                "Located the existing structural-incentive model this ticket should mirror "
                "for style: one BaseModel per concept, frozen+extra=forbid+strict config."
            ),
        },
    )
    exit_code = main(["--role", "scout", "--report", str(report_path), "--repo-root", str(repo)])
    err = capsys.readouterr().err
    assert exit_code == 1
    assert "does not exist under --repo-root" in err


def test_main_scout_report_omits_pr_number_and_still_passes(tmp_path: Path) -> None:
    """Scout is the one role with no PR requirement (investigation precedes
    any PR) -- a deliberate, documented per-role scope narrowing, not an
    accidental gap: pr_number stays optional only here.
    """
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "src/steel_onslaught/contracts/incentive.py", "# fixture\n")
    report_path = _write_report(
        tmp_path / "report.json",
        {
            "role": "scout",
            "verdict": "not_found",
            "findings_paths": ["src/steel_onslaught/contracts/incentive.py"],
            "summary": (
                "Searched the contracts/ tree for an existing report-contract model and found "
                "none; incentive.py is the closest style precedent to build the new one from."
            ),
        },
    )
    exit_code = main(["--role", "scout", "--report", str(report_path), "--repo-root", str(repo)])
    assert exit_code == 0


# --------------------------------------------------------------------------
# main() -- cross-role fail-closed / input-handling cases
# --------------------------------------------------------------------------


def test_main_fails_closed_on_missing_report_file(tmp_path: Path) -> None:
    exit_code = main(["--role", "implementer", "--report", str(tmp_path / "missing.json")])
    assert exit_code == 1


def test_main_fails_closed_on_invalid_json(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    report_path.write_text("{not valid json", encoding="utf-8")
    exit_code = main(["--role", "implementer", "--report", str(report_path)])
    assert exit_code == 1


def test_main_fails_closed_when_report_is_a_json_array(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    report_path.write_text("[1, 2, 3]", encoding="utf-8")
    exit_code = main(["--role", "implementer", "--report", str(report_path)])
    assert exit_code == 1


def test_main_fails_when_report_role_field_disagrees_with_cli_role(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A report cannot be silently re-labeled by the --role CLI flag: the
    role field is REQUIRED on the report itself and must agree.
    """
    repo = tmp_path / "repo"
    _init_repo(repo)
    sha = _commit_file(repo, "docs/evidence/SO-9999.md", "# fixture evidence\n")
    report_path = _write_report(
        tmp_path / "report.json",
        {
            "role": "verifier",
            "pr_number": 4821,
            "verified_sha": sha,
            "verdict": "confirmed",
            "evidence_paths": ["docs/evidence/SO-9999.md"],
            "summary": (
                "Re-ran the seeded RED/GREEN suite against the pushed commit and confirmed "
                "every violation fires through the real validator, not a mock."
            ),
        },
    )
    exit_code = main(["--role", "implementer", "--report", str(report_path)])
    err = capsys.readouterr().err
    assert exit_code == 1
    assert "field 'role'" in err
