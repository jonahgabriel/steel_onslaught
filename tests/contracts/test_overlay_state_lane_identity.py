"""Corpus-wide invariant: every overlay's ``.onex_state`` lane is its OWN lane.

Overlays are written by copy-paste from a sibling -- that is how the corpus
grew to 60 files -- and the one thing a copy-paste reliably gets wrong is the
state-storage block, because a wrong lane still parses, still validates, and
still runs.  It fails silently and destructively: the run appends to ANOTHER
overlay's ledger, leaderboard, and learning artifacts, contaminating that
lane's evidence with matches it never ran.

OMN-15601 is exactly that defect.  ``tactical_split_overdeal_utility_sym_v1_qwen``
declared ``arena_id: foundry_60`` (the symmetric arena) while all seven of its
``.onex_state`` leaves named ``tactical_split_overdeal_utility_asym_v1_qwen`` --
the live lane of a different, real overlay.  It was the ONLY file in the
37-overlay ``tactical_split_overdeal_utility*`` family that borrowed another
overlay's lane; the convention held 36/37 by habit alone.  This suite is what
turns that habit into an enforced invariant, per the standing rule that a rule
without a mechanism is not enforcement.

It runs in the ordinary test path (``tests/contracts/``, ``pytest.mark.unit``),
so a plain suite run catches the next copy-paste; it is not an opt-in script.

Four assertions, in increasing strength:

  1. every ``.onex_state`` value in every overlay is a well-formed path under
     ``.onex_state/steel_onslaught/<lane>/`` (no rogue state roots);
  2. each overlay names exactly ONE lane -- a file whose ledger, leaderboard,
     and learning artifacts scatter across lanes is broken even if each lane is
     otherwise unclaimed;
  3. no two overlays share a lane, unless the sharing is enumerated in
     ``_SHARED_LANE_ALLOWLIST`` below (an explicit decision, not an accident);
  4. no overlay's lane is another overlay FILE's stem.  This is the
     copy-paste signature specifically, and it stays RED even if the donor
     overlay is later renamed or drops its own state block -- which assertion 3
     alone would not catch.

Note on parsing: lanes are extracted from the PARSED YAML document, never from
the file text.  Overlay headers legitimately quote other lanes in prose and in
copy-pasteable ``--state-root`` example commands (e.g. the objdecoy overlay
documents ``ugate_objdecoy_battery``); a text grep would flag those as
violations.  Only values the runtime actually consumes are checked.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).parent.parent.parent
_OVERLAY_DIR = _REPO_ROOT / "contracts_data" / "overlays"

# Any overlay value mentioning this marker must be a state path we can attribute
# to a lane; anything else is a rogue state root and fails assertion 1.
_STATE_MARKER = ".onex_state"
_LANE_PATTERN = re.compile(r"\.onex_state/steel_onslaught/(?P<lane>[A-Za-z0-9_.\-]+)")

# The corpus is large and grows; a glob typo that matched nothing would make
# every assertion below vacuously true, so the count is asserted as a floor.
_MIN_OVERLAY_COUNT = 50

# Deliberate lane sharing, if it is ever genuinely wanted, is enumerated here as
# ``lane -> the exact set of overlay filenames allowed to share it``.  Empty
# today: no two overlays in the corpus legitimately write to one lane.  An entry
# must be exact (not a prefix or a subset) so that adding a THIRD overlay to an
# allowlisted lane still fails, and stale entries are rejected by
# ``test_shared_lane_allowlist_has_no_stale_entries``.
_SHARED_LANE_ALLOWLIST: dict[str, frozenset[str]] = {}


def _iter_strings(node: Any) -> Iterator[str]:
    """Yield every string value in a parsed YAML document, at any depth."""

    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _iter_strings(value)
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from _iter_strings(item)


def _overlay_paths() -> list[Path]:
    paths = sorted(_OVERLAY_DIR.glob("*.yaml"))
    assert len(paths) >= _MIN_OVERLAY_COUNT, (
        f"expected at least {_MIN_OVERLAY_COUNT} overlays under {_OVERLAY_DIR}, "
        f"found {len(paths)} -- the glob is wrong and every assertion in this "
        f"suite would pass vacuously"
    )
    return paths


def _state_values(overlay_path: Path) -> list[str]:
    document = yaml.safe_load(overlay_path.read_text(encoding="utf-8"))
    return [value for value in _iter_strings(document) if _STATE_MARKER in value]


def _lanes(overlay_path: Path) -> set[str]:
    lanes: set[str] = set()
    for value in _state_values(overlay_path):
        lanes.update(match.group("lane") for match in _LANE_PATTERN.finditer(value))
    return lanes


def _lane_owners() -> dict[str, set[str]]:
    """Map each declared lane to the set of overlay filenames declaring it."""

    owners: dict[str, set[str]] = defaultdict(set)
    for overlay_path in _overlay_paths():
        for lane in _lanes(overlay_path):
            owners[lane].add(overlay_path.name)
    return dict(owners)


def test_every_state_value_resolves_to_a_steel_onslaught_lane() -> None:
    """No overlay writes state outside ``.onex_state/steel_onslaught/<lane>/``."""

    rogue: list[str] = []
    for overlay_path in _overlay_paths():
        for value in _state_values(overlay_path):
            if not _LANE_PATTERN.search(value):
                rogue.append(f"{overlay_path.name}: {value}")

    assert not rogue, "state paths outside the steel_onslaught state root:\n" + "\n".join(rogue)


def test_every_overlay_declares_exactly_one_state_lane() -> None:
    """An overlay's ledger/leaderboard/artifacts must all live in ONE lane.

    An overlay with no state paths at all is skipped, not failed: it stores
    nothing on disk and therefore cannot collide with anything.
    """

    scattered: list[str] = []
    for overlay_path in _overlay_paths():
        lanes = _lanes(overlay_path)
        if not lanes:
            continue
        if len(lanes) > 1:
            scattered.append(f"{overlay_path.name}: {sorted(lanes)}")

    assert not scattered, "overlays scattering state across multiple lanes:\n" + "\n".join(
        scattered
    )


def test_no_two_overlays_share_a_state_lane() -> None:
    """Two overlays writing one lane silently merge two experiments' evidence."""

    violations: list[str] = []
    for lane, owners in sorted(_lane_owners().items()):
        if len(owners) == 1:
            continue
        allowed = _SHARED_LANE_ALLOWLIST.get(lane)
        if allowed is not None and allowed == frozenset(owners):
            continue
        violations.append(f"lane {lane!r} is declared by {sorted(owners)}")

    assert not violations, (
        "overlays sharing a state lane (running either one writes the other's "
        "ledger, leaderboard, and learning artifacts):\n" + "\n".join(violations)
    )


def test_no_overlay_borrows_another_overlays_lane_name() -> None:
    """An overlay's lane must not be a DIFFERENT overlay file's stem.

    This is the copy-paste signature: the state block was pasted from a sibling
    and the lane segment was never renamed.  It is checked independently of
    lane sharing so it still fires when the donor overlay is renamed, deleted,
    or has no state block of its own.
    """

    stems = {overlay_path.stem: overlay_path.name for overlay_path in _overlay_paths()}

    violations: list[str] = []
    for overlay_path in _overlay_paths():
        for lane in sorted(_lanes(overlay_path)):
            donor = stems.get(lane)
            if donor is not None and donor != overlay_path.name:
                violations.append(
                    f"{overlay_path.name} writes lane {lane!r}, which is the stem of {donor}"
                )

    assert not violations, "overlays writing another overlay's lane:\n" + "\n".join(violations)


def test_shared_lane_allowlist_has_no_stale_entries() -> None:
    """Every allowlisted lane must still be genuinely shared by those overlays.

    Without this, an allowlist entry outlives the sharing it excused and
    silently re-opens the hole for the next file that lands on that lane.
    """

    owners = _lane_owners()
    stale: list[str] = []
    for lane, allowed in sorted(_SHARED_LANE_ALLOWLIST.items()):
        actual = owners.get(lane, set())
        if frozenset(actual) != allowed:
            stale.append(f"lane {lane!r}: allowlisted {sorted(allowed)}, actual {sorted(actual)}")

    assert not stale, "stale _SHARED_LANE_ALLOWLIST entries:\n" + "\n".join(stale)
