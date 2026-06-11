"""Reducers own canonical match state, folded from the event ledger.

Import concrete reducers from their modules (``reducers.lifecycle``,
``reducers.movement``, ...) — only the shared error type is re-exported here
so parallel reducer tasks never need to edit this file.
"""

from steel_onslaught.reducers.errors import ReducerError

__all__ = ["ReducerError"]
