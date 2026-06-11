"""Per-match deterministic RNG — Task 24.

``MatchRng`` derives independent sub-seeds for each ``(match_seed, tick,
mech_id, kind)`` tuple using BLAKE2b so that every stochastic resolution in the
match (hit rolls, sensor noise, rupture probability, weapon scatter) is fully
deterministic and replay-reproducible without global state.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class MatchRng:
    """Deterministic per-match RNG wrapper.

    Usage::

        rng = MatchRng(match_seed=12345)
        r = rng.for_event(tick=7, mech_id="mech.red.01", kind="weapon_fire")
        hit = r.random() < hit_probability

    Each call to ``for_event`` returns a **fresh** ``random.Random`` instance
    seeded from the blake2b digest of the four-tuple.  The parent ``MatchRng``
    is stateless — parallel consumers can call ``for_event`` in any order
    without interference.
    """

    match_seed: int

    def for_event(self, tick: int, mech_id: str, kind: str) -> random.Random:
        """Return a fresh ``random.Random`` seeded for the given event context.

        Args:
            tick:    Match tick at which the event is resolved.
            mech_id: Identifier of the acting mech.
            kind:    Resolution kind string (e.g. ``"weapon_fire"``,
                     ``"rupture_survival"``, ``"scatter"``).

        Returns:
            A ``random.Random`` instance seeded deterministically from the
            four-tuple ``(match_seed, tick, mech_id, kind)``.
        """
        h = hashlib.blake2b(
            f"{self.match_seed}|{tick}|{mech_id}|{kind}".encode(),
            digest_size=16,
        ).digest()
        return random.Random(int.from_bytes(h, "big"))
