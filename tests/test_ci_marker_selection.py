"""OMN-15493: CI's pytest marker filter must not silently drop tests.

``.github/workflows/ci.yml`` used to run ``pytest -m "unit or integration"``.
That is an *allowlist*: a test with no marker matches neither term, so it is
deselected and never runs -- silently, with CI still green. At the time this
guard was written 13 tests were in exactly that state (8 in
``tests/cards/test_actions.py``, 2 in
``tests/cli/test_frontend_bootstrap_workbench.py``, 2 in
``tests/contracts/test_live_variation_contracts.py``, 1 in
``tests/contracts/test_model_catalog.py``). All 13 passed when run directly, so
the loss was pure coverage, invisible in every CI log.

The fix inverts the filter to the *denylist* ``-m "not live"``: an unmarked test
now runs by default, and forgetting a marker can no longer cost coverage. The
tests below are the mechanism that keeps it that way -- a rule stated only in a
comment above the ``run:`` line would not survive the next person who edits it.

The contract is two-sided, because each side fails in the opposite direction:

* Nothing without an exclusion marker may be deselected -- otherwise the
  allowlist regression returns and coverage silently drains again.
* Every ``live``-marked test must still be deselected -- otherwise "fixing" the
  first half by simply deleting ``-m`` would let the real-infra tests
  (``tests/live/``, which drive a real Kafka broker and a real LLM endpoint)
  run on a hosted runner.

Both are answered from a single collection pass; see ``tests/_ci_marker_census``
for why a single pass, and not a diff of two ``--collect-only`` runs, is the
only reliable way to ask.

A denylist also makes marker *spelling* load-bearing for the first time: a test
written ``@pytest.mark.liv`` no longer matches ``live``, so instead of being
skipped it runs. ``--strict-markers`` closes that new hole, and the last test
here proves it genuinely rejects an unregistered marker rather than merely
appearing in the config.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

from tests._ci_marker_census import CENSUS_OUT_ENV_VAR

REPO_ROOT = Path(__file__).parent.parent
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PYPROJECT = REPO_ROOT / "pyproject.toml"

#: The only markers CI is allowed to exclude. ``live`` means "real external
#: infra, explicit opt-in only" (registered in pyproject.toml); it is the one
#: category that genuinely must not run on a hosted runner. Adding a marker
#: here widens what CI may skip, so it should be a deliberate, reviewed edit.
INTENTIONALLY_EXCLUDED_MARKERS = frozenset({"live"})

# "pytest" as a whole word, so `npm test` / `playwright install` do not match.
_PYTEST_INVOCATION_RE = re.compile(r"(?<![\w-])pytest(?![\w-])")
# A quoted -m argument. An unquoted expression fails this parse on purpose:
# the guard refuses to guess at a shape it has not been taught to read.
_MARKEXPR_RE = re.compile(r"(?<![\w-])-m\s+(?P<quote>[\"'])(?P<expr>.+?)(?P=quote)")


def _ci_pytest_run_steps() -> list[str]:
    """Every ``run:`` block in ci.yml that invokes pytest."""
    workflow: Any = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    return [
        run
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if isinstance(run := step.get("run"), str) and _PYTEST_INVOCATION_RE.search(run)
    ]


def _ci_marker_expression() -> str:
    """The exact ``-m`` expression CI runs the backend suite with."""
    steps = _ci_pytest_run_steps()
    assert len(steps) == 1, (
        f"Expected exactly one pytest invocation in {CI_WORKFLOW.name}, found "
        f"{len(steps)}. This guard reasons about a single marker filter; if CI "
        f"grows a second pytest run, teach the guard about it rather than "
        f"letting one of the two go unchecked.\nFound: {steps!r}"
    )
    matches = _MARKEXPR_RE.findall(steps[0])
    assert len(matches) == 1, (
        f"Expected exactly one quoted -m marker expression in the CI pytest "
        f"step, found {len(matches)}. Without one, this guard cannot verify "
        f"what CI skips.\nStep: {steps[0]!r}"
    )
    expr = _MARKEXPR_RE.search(steps[0])
    assert expr is not None  # findall already proved it matches
    return expr.group("expr")


def _nodeids_lacking_any(entries: list[dict[str, Any]], markers: frozenset[str]) -> list[str]:
    return [
        str(entry["nodeid"]) for entry in entries if not (set(map(str, entry["markers"])) & markers)
    ]


def _nodeids_having_any(entries: list[dict[str, Any]], markers: frozenset[str]) -> list[str]:
    return [str(entry["nodeid"]) for entry in entries if set(map(str, entry["markers"])) & markers]


@pytest.fixture(scope="module")
def ci_collection_census(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Collect the whole suite under CI's own marker expression, once.

    Runs the real pytest binary against the real test tree with the expression
    read out of the real workflow file, so the verdict recorded here is the
    verdict CI gets -- not a model of it.
    """
    markexpr = _ci_marker_expression()
    census_path = tmp_path_factory.mktemp("ci_marker_census") / "census.json"

    env = dict(os.environ)
    # -p imports the plugin before pytest inserts the rootdir on sys.path, so
    # the import path has to be made explicit here.
    env["PYTHONPATH"] = os.pathsep.join(
        [str(REPO_ROOT), env["PYTHONPATH"]] if env.get("PYTHONPATH") else [str(REPO_ROOT)]
    )
    env[CENSUS_OUT_ENV_VAR] = str(census_path)

    result = subprocess.run(
        [
            "uv",
            "run",
            "--no-sync",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "tests._ci_marker_census",
            "-m",
            markexpr,
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
    )
    assert result.returncode == 0, (
        f"Collecting the suite with CI's filter (-m {markexpr!r}) failed with "
        f"exit code {result.returncode}.\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    assert census_path.exists(), (
        f"The marker census plugin wrote nothing to {census_path}. Did the -p "
        f"import fail?\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    census: dict[str, Any] = json.loads(census_path.read_text(encoding="utf-8"))
    assert census["markexpr"] == markexpr, (
        f"Census recorded marker expression {census['markexpr']!r}, expected "
        f"{markexpr!r} -- the subprocess did not run the filter under test."
    )
    return census


@pytest.mark.unit
def test_ci_workflow_declares_exactly_one_quoted_pytest_marker_filter() -> None:
    """The shape this guard depends on is itself asserted, not assumed."""
    expr = _ci_marker_expression()
    assert expr.strip(), f"CI's -m expression is empty: {expr!r}"


@pytest.mark.unit
def test_ci_marker_filter_deselects_nothing_that_lacks_an_exclusion_marker(
    ci_collection_census: dict[str, Any],
) -> None:
    """No test may be dropped by CI merely for having no marker (OMN-15493).

    This is the regression that motivated the guard. Against the old
    ``-m "unit or integration"`` allowlist it fails and names all 13 unmarked
    casualties; against ``-m "not live"`` the deselected set is exactly the
    ``live`` tests.
    """
    silently_dropped = _nodeids_lacking_any(
        ci_collection_census["deselected"], INTENTIONALLY_EXCLUDED_MARKERS
    )
    assert not silently_dropped, (
        f"CI's marker filter (-m {ci_collection_census['markexpr']!r}) deselects "
        f"{len(silently_dropped)} test(s) that carry none of the markers CI is "
        f"allowed to exclude ({sorted(INTENTIONALLY_EXCLUDED_MARKERS)}). These "
        f"tests exist, pass, and never run in CI:\n  "
        + "\n  ".join(silently_dropped)
        + "\n\nEither the filter is an allowlist again (make it a denylist, e.g. "
        '-m "not live"), or a genuinely excludable category needs a registered '
        "marker and an entry in INTENTIONALLY_EXCLUDED_MARKERS."
    )


@pytest.mark.unit
def test_ci_marker_filter_still_excludes_every_live_marked_test(
    ci_collection_census: dict[str, Any],
) -> None:
    """The real-infra opt-out must survive any future edit to the filter.

    Deleting ``-m`` altogether would satisfy the test above while pointing the
    hosted runner at a real Kafka broker and a real LLM endpoint.
    """
    leaked = _nodeids_having_any(ci_collection_census["selected"], frozenset({"live"}))
    assert not leaked, (
        f"CI's marker filter (-m {ci_collection_census['markexpr']!r}) selects "
        f"{len(leaked)} test(s) marked `live`, which require real external "
        f"infra (Kafka + a live LLM endpoint) and must never run on a hosted "
        f"runner:\n  " + "\n  ".join(leaked)
    )


@pytest.mark.unit
def test_ci_pytest_step_passes_strict_markers() -> None:
    """The denylist needs ``--strict-markers`` on CI's own command line.

    Under the old allowlist a misspelled marker was merely deselected -- an
    invisible non-event. Under ``-m "not live"`` a test written
    ``@pytest.mark.liv`` does not match ``live``, so it gets *selected*, and CI
    reaches for a real Kafka broker and a real LLM endpoint.

    This asserts the flag's presence; the test below asserts it actually bites,
    which is the part that cannot be taken on trust (see ``PYPROJECT``'s
    OMN-15493 note: the same flag in ``addopts`` is a no-op on pytest 9.0.3).
    """
    step = _ci_pytest_run_steps()[0]
    assert "--strict-markers" in step, (
        "CI's pytest step must pass --strict-markers so a misspelled marker "
        f"fails collection rather than quietly running.\nStep: {step!r}"
    )


@pytest.mark.unit
def test_strict_markers_actually_rejects_an_unregistered_marker(tmp_path: Path) -> None:
    """Prove ``--strict-markers`` bites, against this repo's real config.

    Both halves matter and are asserted together:

    * a *registered* marker still collects -- which is also what proves the
      probe is reading this project's real ``markers`` list rather than an
      empty config, where every marker would fail and the test below would
      pass for the wrong reason;
    * an *unregistered* marker fails collection.

    The probe modules are written outside the repo tree and pointed back at
    ``pyproject.toml`` with ``-c``, so a concurrent test run never sees them.
    """
    registered = tmp_path / "test_registered_marker_probe.py"
    registered.write_text(
        "import pytest\n\n\n@pytest.mark.unit\ndef test_probe() -> None:\n    pass\n",
        encoding="utf-8",
    )
    unregistered = tmp_path / "test_unregistered_marker_probe.py"
    unregistered.write_text(
        "import pytest\n\n\n@pytest.mark.liv\ndef test_probe() -> None:\n    pass\n",
        encoding="utf-8",
    )

    def _collect(target: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "uv",
                "run",
                "--no-sync",
                "pytest",
                "-c",
                str(PYPROJECT),
                "--strict-markers",
                "--collect-only",
                "-q",
                str(target),
            ],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )

    ok = _collect(registered)
    assert ok.returncode == 0, (
        "A registered marker (`unit`) must still collect under "
        f"--strict-markers; got exit {ok.returncode}. If this fails, the probe "
        f"is not reading this project's markers list.\nstdout:\n{ok.stdout}\n"
        f"stderr:\n{ok.stderr}"
    )

    typo = _collect(unregistered)
    assert typo.returncode != 0 and "not found in `markers`" in typo.stdout, (
        "--strict-markers did NOT reject the unregistered marker `liv`, so a "
        "misspelled `live` marker would run on a hosted CI runner and reach "
        f"real infra. Exit {typo.returncode}.\nstdout:\n{typo.stdout}\n"
        f"stderr:\n{typo.stderr}"
    )
