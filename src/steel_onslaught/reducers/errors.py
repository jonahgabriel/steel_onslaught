"""Shared reducer error type.

Lives in its own module so the parallel reducer tasks (19-26) can import it
without touching ``reducers/__init__.py`` or each other's modules.
"""

from __future__ import annotations


class ReducerError(Exception):
    """Raised when a reducer rejects an event that violates a match invariant.

    The message starts with a stable snake_case code (e.g. ``tick_skip``,
    ``speed_exceeded``, ``insufficient_pressure``) followed by ``: <detail>``.
    """
