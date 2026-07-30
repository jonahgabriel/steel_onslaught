"""Collect-only pytest plugin that reports which items a marker filter dropped.

Loaded explicitly (``-p tests._ci_marker_census``) by the OMN-15493 guard in
``tests/test_ci_marker_selection.py``. That guard needs, for one single
collection pass, both halves of the marker filter's verdict: what survived and
what was deselected, each with its marker set.

Why a plugin instead of diffing two ``--collect-only`` runs:

1. **Node ids are not stable across runs.** ``tests/ledger/test_sqlite_ledger.py``
   parametrizes over envelopes carrying freshly generated UUIDs, so the same
   test has a different id in every collection. Diffing the id lists of a
   bare collect against a filtered collect reports that test as "deselected"
   in both directions -- a phantom the guard would either trip over or have to
   paper over with fuzzy id matching.
2. **Deselection semantics should not be reimplemented.** ``pytest_deselected``
   is fired by pytest's own mark plugin after it evaluates the ``-m``
   expression, so this census records the real verdict of the real evaluator
   applied to the real collected items -- not a second-guess of pytest's
   marker algebra written in test code.

The plugin is inert unless ``STEEL_MARKER_CENSUS_OUT`` names an output path, so
importing it has no effect on an ordinary run.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

#: Env var naming the JSON file to write the census to. Absent -> plugin is a
#: no-op, which keeps this module harmless if it is ever loaded by accident.
CENSUS_OUT_ENV_VAR = "STEEL_MARKER_CENSUS_OUT"

# Deselection is reported incrementally (the mark filter and the keyword filter
# each fire the hook), so entries accumulate here until collection finishes.
_DESELECTED: list[dict[str, Any]] = []


def _describe(item: pytest.Item) -> dict[str, Any]:
    """Render one collected item as ``{nodeid, markers}``.

    ``iter_markers()`` -- not ``own_markers`` -- is what pytest's ``-m``
    evaluation itself consults, so it is what the census must record: a marker
    applied at module or class scope counts for the items underneath it.
    """
    return {
        "nodeid": item.nodeid,
        "markers": sorted({mark.name for mark in item.iter_markers()}),
    }


def pytest_deselected(items: Sequence[pytest.Item]) -> None:
    """Record every item pytest drops, whatever dropped it."""
    _DESELECTED.extend(_describe(item) for item in items)


def pytest_collection_finish(session: pytest.Session) -> None:
    """Write the census once collection (and therefore deselection) is final."""
    out = os.environ.get(CENSUS_OUT_ENV_VAR)
    if not out:
        return
    payload = {
        "markexpr": str(session.config.option.markexpr or ""),
        "selected": [_describe(item) for item in session.items],
        "deselected": list(_DESELECTED),
    }
    Path(out).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
