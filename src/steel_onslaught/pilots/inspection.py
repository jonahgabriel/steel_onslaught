"""Read-only projections for operator prompt/rule inspection and editing.

These helpers turn an already-validated application overlay into typed, closed
projections an operator surface (CLI today, browser workbench next) can render
without importing composition internals or gaining any runtime authority.  A
projection is pure: it opens no ledger, provider, or transport.

Two things are intentionally kept together here:

* :func:`project_effective_prompts` answers "what is each mech actually flying
  with", after operator prompt overrides, with the same digest the runner
  records — so the surface an operator edits is the surface replay checks.
* :func:`project_rule_catalog` answers "what rule handlers can I turn on, and
  which are on" for a given overlay, from the same allowlist composition uses.
"""

from __future__ import annotations

from steel_onslaught.cards.rules import default_rule_registry
from steel_onslaught.contracts.application import ModelSOApplicationOverlay
from steel_onslaught.match.composition import project_effective_prompt_provenance
from steel_onslaught.pilots.persona_prompts import ModelSOMatchPromptProvenance
from steel_onslaught.pilots.programming import ModelSOCardRuleCatalogProjection


def project_effective_prompts(
    overlay: ModelSOApplicationOverlay,
) -> ModelSOMatchPromptProvenance:
    """Return the effective, post-override prompt identity for one overlay.

    The filesystem-touching projection is owned by the composition root
    (``project_effective_prompt_provenance``); this is the read-only inspection
    entry point operator surfaces call.
    """

    return project_effective_prompt_provenance(overlay)


def project_rule_catalog(
    overlay: ModelSOApplicationOverlay,
) -> ModelSOCardRuleCatalogProjection:
    """Return the installed-rule catalog and this overlay's enabled selection.

    The registry is the same allowlist composition builds.  A ``pack_id`` that
    does not match the built pack fails closed, exactly as composition does, so
    the catalog can never advertise handlers a match would not actually load.
    """

    registry = default_rule_registry()
    binding = overlay.contracts.balance_rule_pack
    if binding is None:
        return registry.catalog(())
    if binding.pack_id != registry.pack_id:
        raise ValueError(
            f"overlay selects unknown balance rule pack {binding.pack_id!r}; "
            f"available pack is {registry.pack_id!r}"
        )
    return registry.catalog(binding.handler_ids)


__all__ = [
    "project_effective_prompts",
    "project_rule_catalog",
]
