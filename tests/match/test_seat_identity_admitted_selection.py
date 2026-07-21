"""Seat identity on the ADMITTED RUNTIME SELECTION, not the overlay template.

An overlay's authored ``programmers`` block is only a template.  Both live
launch paths rebind every model seat's ``pilot_spec_id`` from the option the
operator actually selected (``_admitted_seat_overlay``), so a
differentiated-looking overlay proves nothing about the match that runs.

These tests drive the real shipped ``contracts_data`` through exactly the two
functions the browser start path uses — ``_admitted_seat_overlay`` and then
``build_card_programmers`` — for both live launch shapes:

* the **catalog** path (``live_glm_cards`` + ``model_catalogs/configured_v1``),
  which is what a clean browser session actually starts, and
* the plain **roster** path (``standard_v1_qwen`` + ``rosters/canonical_qwen35``).

Neither of those overlays declares a split ``deck_policy``.  That is the point:
the guard must not be contingent on ``deck_policy`` being present, or it covers
one unreferenced overlay and none of the reachable ones.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest
import yaml  # type: ignore[import-untyped]

from steel_onslaught.cli.play import _admitted_seat_overlay, _InjectedSecretResolver
from steel_onslaught.commands.browser_gateway import ModelSOBrowserStartMatchRequest
from steel_onslaught.contracts.application import (
    ModelSOApplicationOverlay,
    ModelSOCardProgrammerBinding,
)
from steel_onslaught.contracts.commands import (
    ModelSOStartMatchCommand,
    ModelSOStartMatchSeatSelection,
)
from steel_onslaught.contracts.model_catalog import ModelSOModelCatalog
from steel_onslaught.contracts.player_selection import ModelSOPlayerRosterBinding
from steel_onslaught.llm.programming import LLMProgrammingPilot
from steel_onslaught.llm.schemas import ModelSOOpenAIChatRequest, ModelSOOpenAIChatResponse
from steel_onslaught.match.composition import (
    SeatIdentityError,
    build_card_programmers,
    build_llm_dependencies,
    load_application_overlay,
    load_model_catalog_pilot_registry,
    load_model_catalog_runtime_overlay,
    load_model_catalog_runtime_sources,
    load_pilot_registry,
)

pytestmark = pytest.mark.integration

_ROOT = Path(__file__).resolve().parents[2]
_CONTRACTS = _ROOT / "contracts_data"
# The launch overlay + catalog index a browser demo session actually starts on.
_CATALOG_LAUNCH_OVERLAY = _CONTRACTS / "overlays/live_glm_cards.yaml"
_CATALOG_INDEX = _CONTRACTS / "model_catalogs/configured_v1.yaml"
# The plain roster launch shape for the same provider family.
_ROSTER_OVERLAY = _CONTRACTS / "overlays/standard_v1_qwen.yaml"
_ROSTER = _CONTRACTS / "rosters/canonical_qwen35.yaml"

_MATCH_ID = "match.01JABCDE0123456789ABCDEFGX"
_COMMAND_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")


class _UnusedTransport:
    """Fail loudly if seat validation ever binds a provider before deciding."""

    def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        request: ModelSOOpenAIChatRequest,
        timeout_seconds: float,
    ) -> ModelSOOpenAIChatResponse:
        del url, headers, request, timeout_seconds
        raise AssertionError("seat identity must be decided without calling a provider")


def _secrets() -> _InjectedSecretResolver:
    return _InjectedSecretResolver.from_cli(
        glm_api_key="test-glm",
        openrouter_api_key="test-openrouter",
        gemini_api_key="test-gemini",
    )


def _roster() -> ModelSOPlayerRosterBinding:
    return ModelSOPlayerRosterBinding.model_validate_json(
        json.dumps(yaml.safe_load(_ROSTER.read_text(encoding="utf-8")))
    )


def _request(*, red_option_id: str, blue_option_id: str) -> ModelSOBrowserStartMatchRequest:
    return ModelSOBrowserStartMatchRequest(
        match_id=_MATCH_ID,
        command=ModelSOStartMatchCommand(
            schema_version="1",
            kind="steel_onslaught.start_match",
            command_id=_COMMAND_ID,
            expected_overlay_sha256="1" * 64,
            expected_roster_sha256="2" * 64,
            selections=(
                ModelSOStartMatchSeatSelection(side="red", option_id=red_option_id),
                ModelSOStartMatchSeatSelection(side="blue", option_id=blue_option_id),
            ),
        ),
    )


def _catalog_launch() -> tuple[ModelSOApplicationOverlay, ModelSOModelCatalog, dict[str, object]]:
    base = load_application_overlay(_CATALOG_LAUNCH_OVERLAY)
    catalog, source_overlays = load_model_catalog_runtime_sources(_CATALOG_INDEX)
    _, merged = load_model_catalog_runtime_overlay(_CATALOG_INDEX, base)
    return merged, catalog, dict(source_overlays)


def _catalog_personas(*, red_option_id: str, blue_option_id: str) -> dict[str, str]:
    """Run the catalog launch path end to end and report the bound personas."""

    merged, catalog, source_overlays = _catalog_launch()
    selected = _admitted_seat_overlay(
        overlay=merged,
        roster=catalog.to_roster_binding(),
        request=_request(red_option_id=red_option_id, blue_option_id=blue_option_id),
        catalog=catalog,
        source_overlays=source_overlays,  # type: ignore[arg-type]
    )
    card_binding = selected.contracts.card_catalog
    assert card_binding is not None
    registry = load_model_catalog_pilot_registry(_CATALOG_INDEX)
    llm = build_llm_dependencies(
        merged,
        secret_resolver=_secrets(),
        http_transport=_UnusedTransport(),
    )
    try:
        programmers = build_card_programmers(
            card_binding.programmers,
            registry=registry,
            llm=llm,
            deck_policy=card_binding.deck_policy,
        )
        personas: dict[str, str] = {}
        for side, programmer in programmers.items():
            assert isinstance(programmer, LLMProgrammingPilot)
            personas[side] = programmer._persona.persona_id
        return personas
    finally:
        llm.close()


def _roster_personas(*, red_option_id: str, blue_option_id: str) -> dict[str, str]:
    """Run the plain roster launch path end to end (no catalog at all)."""

    overlay = load_application_overlay(_ROSTER_OVERLAY)
    roster = _roster()
    selected = _admitted_seat_overlay(
        overlay=overlay,
        roster=roster,
        request=_request(red_option_id=red_option_id, blue_option_id=blue_option_id),
    )
    card_binding = selected.contracts.card_catalog
    assert card_binding is not None
    registry = load_pilot_registry(overlay.contracts.pilot_registry_dir)
    llm = build_llm_dependencies(overlay, http_transport=_UnusedTransport())
    try:
        programmers = build_card_programmers(
            card_binding.programmers,
            registry=registry,
            llm=llm,
            deck_policy=card_binding.deck_policy,
        )
        personas: dict[str, str] = {}
        for side, programmer in programmers.items():
            assert isinstance(programmer, LLMProgrammingPilot)
            personas[side] = programmer._persona.persona_id
        return personas
    finally:
        llm.close()


def test_reachable_launch_overlays_declare_no_split_deck_policy() -> None:
    """Pin the reachability fact this whole guard depends on.

    If seat validation is ever made contingent on ``deck_policy`` again, this
    test is the record that doing so would leave every launch path a browser
    session can actually reach completely unguarded.
    """

    merged, _catalog, _sources = _catalog_launch()
    catalog_binding = merged.contracts.card_catalog
    assert catalog_binding is not None
    assert catalog_binding.card_mode_enabled is True
    assert catalog_binding.deck_policy is None

    roster_overlay = load_application_overlay(_ROSTER_OVERLAY)
    roster_binding = roster_overlay.contracts.card_catalog
    assert roster_binding is not None
    assert roster_binding.card_mode_enabled is True
    assert roster_binding.deck_policy is None


def test_catalog_mirror_selection_fails_closed() -> None:
    """The same catalog option on both seats is not a contest."""

    with pytest.raises(SeatIdentityError, match="distinct card programmer identities"):
        _catalog_personas(
            red_option_id="player_option.qwen35_model",
            blue_option_id="player_option.qwen35_model",
        )


def test_catalog_distinct_selection_binds_two_personas() -> None:
    personas = _catalog_personas(
        red_option_id="player_option.qwen35_model",
        blue_option_id="player_option.qwen27_model",
    )

    assert personas == {"red": "berserker", "blue": "sniper"}


def test_catalog_same_persona_on_two_models_is_a_legitimate_contest() -> None:
    """Identity is (model, persona) — not persona alone.

    Sniper-vs-sniper across two different models is the cleanest
    model-vs-model comparison there is; rejecting it would break the product,
    so the guard must not collapse to a persona-uniqueness rule.
    """

    personas = _catalog_personas(
        red_option_id="player_option.qwen35_sniper",
        blue_option_id="player_option.qwen27_model",
    )

    assert personas == {"red": "sniper", "blue": "sniper"}


def test_roster_mirror_selection_fails_closed() -> None:
    """The roster path admits the same option for both seats; runtime must not."""

    roster = _roster()
    # The roster genuinely permits this selection: the guard has to be at
    # runtime, because the contract layer never rejects it.
    for seat in roster.seats:
        assert "player_option.qwen35_model" in seat.allowed_option_ids

    with pytest.raises(SeatIdentityError, match="distinct card programmer identities"):
        _roster_personas(
            red_option_id="player_option.qwen35_model",
            blue_option_id="player_option.qwen35_model",
        )


def test_roster_distinct_selection_binds_two_personas() -> None:
    personas = _roster_personas(
        red_option_id="player_option.qwen35_model",
        blue_option_id="player_option.qwen35_sniper",
    )

    assert personas == {"red": "berserker", "blue": "sniper"}


def test_roster_selection_overrides_the_overlay_authored_template() -> None:
    """The admitted option owns the seat, and the template owns the policy.

    The roster branch has no catalog and no source overlay, so the seat's
    non-identity policy comes from the launch overlay's own authored binding.
    That branch had no direct assertion before; without it a regression could
    silently drop ``failure_policy`` while still looking correct.
    """

    overlay = load_application_overlay(_ROSTER_OVERLAY)
    roster = _roster()
    authored = overlay.contracts.card_catalog
    assert authored is not None
    # Authored default: red=berserker spec, blue=sniper spec, both fail-closed.
    assert {binding.side: binding.pilot_spec_id for binding in authored.programmers} == {
        "red": "pilot.llm.qwen35",
        "blue": "pilot.llm.qwen35_sniper",
    }

    selected = _admitted_seat_overlay(
        overlay=overlay,
        roster=roster,
        request=_request(
            red_option_id="player_option.qwen35_sniper",
            blue_option_id="player_option.qwen35_model",
        ),
    )
    card_binding = selected.contracts.card_catalog
    assert card_binding is not None
    # The seats are swapped relative to the authored template: the admitted
    # option, not the overlay default, owns each seat's pilot spec.
    assert {binding.side: binding.pilot_spec_id for binding in card_binding.programmers} == {
        "red": "pilot.llm.qwen35_sniper",
        "blue": "pilot.llm.qwen35",
    }
    # ...while the template still owns the non-identity policy.
    assert {binding.failure_policy for binding in card_binding.programmers} == {"raise"}


def test_roster_seat_without_an_authored_template_is_synthesized_not_dropped() -> None:
    """A seat with no authored binding is still bound to its admitted pilot.

    Dropping it would silently demote a live LLM seat to the deterministic
    priority planner, which is the exact class of failure this lane exists to
    remove.  This is the synthesized-``ModelSOCardProgrammerBinding`` branch.
    """

    overlay = load_application_overlay(_ROSTER_OVERLAY)
    card_catalog = overlay.contracts.card_catalog
    assert card_catalog is not None
    red_only = card_catalog.model_copy(
        update={
            "programmers": tuple(
                binding for binding in card_catalog.programmers if binding.side == "red"
            )
        }
    )
    contracts = overlay.contracts.model_copy(update={"card_catalog": red_only})
    partial_overlay = overlay.model_copy(update={"contracts": contracts})
    roster = _roster()

    selected = _admitted_seat_overlay(
        overlay=partial_overlay,
        roster=roster,
        request=_request(
            red_option_id="player_option.qwen35_model",
            blue_option_id="player_option.qwen35_sniper",
        ),
    )
    card_binding = selected.contracts.card_catalog
    assert card_binding is not None
    blue = next(binding for binding in card_binding.programmers if binding.side == "blue")
    assert isinstance(blue, ModelSOCardProgrammerBinding)
    assert blue.pilot_spec_id == "pilot.llm.qwen35_sniper"
    # A synthesized binding keeps the closed contract's fail-closed default.
    assert blue.failure_policy == "raise"


def test_overlay_without_any_programmers_is_left_alone() -> None:
    """No declared programmers anywhere means the seat stays deterministic."""

    overlay = load_application_overlay(_ROSTER_OVERLAY)
    card_catalog = overlay.contracts.card_catalog
    assert card_catalog is not None
    contracts = overlay.contracts.model_copy(
        update={"card_catalog": card_catalog.model_copy(update={"programmers": ()})}
    )
    bare_overlay = overlay.model_copy(update={"contracts": contracts})
    roster = _roster()

    selected = _admitted_seat_overlay(
        overlay=bare_overlay,
        roster=roster,
        request=_request(
            red_option_id="player_option.qwen35_model",
            blue_option_id="player_option.qwen35_sniper",
        ),
    )

    assert selected is bare_overlay
