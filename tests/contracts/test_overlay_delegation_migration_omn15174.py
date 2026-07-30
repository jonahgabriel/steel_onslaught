"""Corpus census for the overlay provider-binding migration (OMN-15174).

Task 20 of the steel-ONEX dispatch integration plan
(``omni_home/docs/plans/2026-07-26-steel-node-dispatch-integration-plan.md``
§3 P2) migrates overlay provider bindings from ``kind: openai_compatible``
(direct HTTP via ``OpenAICompatibleClient``) to ``kind: onex_delegation``
(routed through the platform delegation chain via
``LlmBusDelegationClient``).

**This module exists because the migration is not mechanical.** Swapping the
binding kind changed observable model behaviour in five ways when batch 1 was
built. Three of the five are now CLOSED by OMN-15482 and are no longer
blockers:

* ``temperature`` was dropped. **CLOSED (OMN-15482):** the wire model gained a
  ``temperature`` field and ``LlmBusDelegationClient`` forwards it verbatim.
* the system/user message split was collapsed into one flat ``prompt`` string.
  **CLOSED (OMN-15482):** ``system_prompt`` is now its own wire field and the
  backend receives two distinct chat roles.
* ``json_mode`` became an appended prompt sentence instead of a wire
  parameter. **CLOSED (OMN-15482):** it maps to
  ``response_format={"type": "json_object"}``; the appended sentence is
  deleted, not retained as a fallback.

Equivalence for all three is proven differentially against
``OpenAICompatibleClient`` in
``tests/llm/test_client_delegation_fidelity_omn15482.py``, and applied-by-the-
backend against the live ``local-coder-mlx`` endpoint by omnimarket's opt-in
``test_live_completion_fidelity_omn15482.py`` (temperature 0.0 -> 3/3 identical
completions vs temperature 1.0 -> 3/3 distinct, same prompt).

Two deltas REMAIN open and are still real blockers:

* ``image_attachment`` is rejected outright (explicitly out of OMN-15482's
  scope; the fail-loud raise is correct behaviour, not a defect).
* ``retry`` has no counterpart -- ``ModelSODelegationProviderBinding`` has no
  such field, while every ``openai_compatible`` binding in this corpus
  declares one. Whether per-overlay retry config needs an equivalent is an
  open design question, deliberately not settled by OMN-15482.

Closing the three did NOT change this census's machine-readable blocking
reasons or any pinned count: those three deltas were never encoded as typed
reasons in ``_classify`` (the typed reasons are image-attachment and
backend-coverage), so the pins below are unchanged and were re-verified green
against this edit. The operative gate on batch 2 is now
``_PROVEN_DELEGATION_MODELS`` -- backend coverage -- not completion fidelity.

For an overlay whose battery numbers are published under ``docs/evidence/``,
migrating under those deltas silently changes the measured system and
confounds the published statistic. That is the provider-confound the
display-salience PROMINENT overlay's ALTERNATIVE READINGS section names and
rejects, and it is why this repo's overlay headers repeatedly state that
existing overlays stay "byte-frozen so historical replays remain valid".

So migration is gated on identity preservation, and the gate is mechanical:
an overlay may migrate only if the delegation backend it would pin serves
**the same model string it already names**. Exactly one backend is proven
live through steel's delegation path -- ``local-coder-mlx``
(``mlx-community/Qwen3.6-35B-A3B-8bit`` on stickybeatz-studio:8401, proven by
OMN-15170's live driver test and OMN-15172's acceptance battery) -- so the
proven-model set below has one member, and batch 1 has one overlay.

The census asserts a **pinned denominator**: adding an overlay, or migrating
one, fails these tests until the pins are updated deliberately. That turns
"~53 overlays remaining, someday" into an enforced, falsifiable number.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from steel_onslaught.contracts.application import (
    ModelSODelegationProviderBinding,
    ModelSOOpenAICompatibleProviderBinding,
)
from steel_onslaught.llm.client_delegation import LlmBusDelegationClient
from steel_onslaught.llm.schemas import (
    ModelSOLlmCompletionRequest,
    ModelSOLlmImageAttachment,
)
from steel_onslaught.match.composition import load_application_overlay

_ROOT = Path(__file__).resolve().parents[2]
_OVERLAY_DIR = _ROOT / "contracts_data/overlays"
_DOCS_DIR = _ROOT / "docs"

# ---------------------------------------------------------------------------
# Pins. Every number and set here is a deliberate declaration; a corpus change
# that does not update them fails loudly rather than drifting silently.
# ---------------------------------------------------------------------------

# Overlays born delegation-bound as PREREGISTERED science artifacts
# (OMN-15166 display-salience arm #1). Never migrated by this ticket, never
# to be modified by any batch of it -- their pre-registration is committed on
# the PROMINENT overlay's own header.
_PREREGISTERED_DELEGATION = frozenset(
    {
        "foundry_60_asym_v1_salience_default_delegation.yaml",
        "foundry_60_asym_v1_salience_prominent_delegation.yaml",
    }
)

# Batch 1 of OMN-15174: the only overlay in the corpus whose migration is
# provably identity-preserving (same model string, same host, zero published
# battery evidence, binding-proof lane rather than a measured battery lane).
_MIGRATED_BATCH_1 = frozenset({"local_200_v1.yaml"})

# Model strings served by a delegation backend that has been proven live
# through steel's own delegation path. ONE member: local-coder-mlx. Widening
# this set is what unblocks a batch 2, and it may only be widened by a live
# proof, not by reading a backend declaration in bifrost_delegation.yaml
# (`local-coder` declares `Qwen3.6-35B-A3B` but carries `endpoint_url: null`
# with no BIFROST_* env var present, so it does not resolve on this path).
_PROVEN_DELEGATION_MODELS = frozenset({"mlx-community/Qwen3.6-35B-A3B-8bit"})

# Overlays carrying an image_attachment provider binding. Hard-blocked:
# LlmBusDelegationClient raises rather than silently dropping the image.
_IMAGE_BLOCKED = frozenset(
    {
        "vision_foundry_60_asym_v2_gemini_img.yaml",
        "vision_foundry_60_asym_v2_openrouter_blank.yaml",
        "vision_foundry_60_asym_v2_openrouter_img.yaml",
        "vision_foundry_60_asym_v2_vertex_img.yaml",
    }
)

_EXPECTED_TOTAL_OVERLAYS = 59
_EXPECTED_MIGRATED_COUNT = 3  # 2 preregistered + 1 batch-1
_EXPECTED_UNMIGRATED_COUNT = 56

# Typed blocking reasons.
_REASON_IMAGE = "image_attachment unsupported by LlmBusDelegationClient"
_REASON_NO_PROVEN_BACKEND = "no live-proven delegation backend serves this model string"


def _overlay_paths() -> list[Path]:
    return sorted(_OVERLAY_DIR.glob("*.yaml"))


def _provider_kinds(path: Path) -> list[str]:
    """Read provider ``kind`` values without going through the typed loader.

    Deliberately a raw YAML read: the census must be able to classify an
    overlay even when the typed loader would reject it, and must not depend
    on the discriminated union staying loadable for every corpus member.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    providers = raw["llm"]["providers"]
    return [str(entry["kind"]) for entry in providers]


def _provider_models(path: Path) -> list[str]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [str(entry["model"]) for entry in raw["llm"]["providers"]]


def _has_image_attachment(path: Path) -> bool:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return any(entry.get("image_attachment") is not None for entry in raw["llm"]["providers"])


def _classify(path: Path) -> tuple[str, str]:
    """Return ``(state, reason)`` for one overlay. ``state`` in {migrated, blocked}."""
    kinds = set(_provider_kinds(path))
    if kinds == {"onex_delegation"}:
        return ("migrated", "")
    if _has_image_attachment(path):
        return ("blocked", _REASON_IMAGE)
    if not set(_provider_models(path)) <= _PROVEN_DELEGATION_MODELS:
        return ("blocked", _REASON_NO_PROVEN_BACKEND)
    return ("blocked", "unclassified")


# ---------------------------------------------------------------------------
# AC3 -- corpus census with a pinned denominator
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_corpus_size_is_pinned() -> None:
    paths = _overlay_paths()
    assert len(paths) == _EXPECTED_TOTAL_OVERLAYS, (
        f"overlay corpus changed size ({len(paths)} != {_EXPECTED_TOTAL_OVERLAYS}); "
        "update the OMN-15174 census pins deliberately -- a new overlay must be "
        "classified as migrated or blocked-with-reason, never silently absorbed"
    )


@pytest.mark.unit
def test_every_overlay_is_classified_and_the_unmigrated_count_is_pinned() -> None:
    migrated: list[str] = []
    blocked: dict[str, str] = {}

    for path in _overlay_paths():
        state, reason = _classify(path)
        if state == "migrated":
            migrated.append(path.name)
        else:
            blocked[path.name] = reason

    # No overlay may fall through classification.
    assert "unclassified" not in blocked.values(), (
        "every unmigrated overlay must carry a typed blocking reason: "
        f"{sorted(name for name, r in blocked.items() if r == 'unclassified')}"
    )

    assert len(migrated) == _EXPECTED_MIGRATED_COUNT
    assert len(blocked) == _EXPECTED_UNMIGRATED_COUNT, (
        f"remaining unmigrated overlay count is {len(blocked)}, pinned at "
        f"{_EXPECTED_UNMIGRATED_COUNT}"
    )
    assert len(migrated) + len(blocked) == _EXPECTED_TOTAL_OVERLAYS


@pytest.mark.unit
def test_migrated_set_is_exactly_the_preregistered_pair_plus_batch_1() -> None:
    migrated = {p.name for p in _overlay_paths() if _classify(p)[0] == "migrated"}
    assert migrated == _PREREGISTERED_DELEGATION | _MIGRATED_BATCH_1


# ---------------------------------------------------------------------------
# AC2 -- binding-shape assertion over the migrated batch
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("overlay_name", sorted(_MIGRATED_BATCH_1))
def test_batch_1_binding_shape(overlay_name: str) -> None:
    overlay = load_application_overlay(_OVERLAY_DIR / overlay_name)

    for provider in overlay.llm.providers:
        assert isinstance(provider, ModelSODelegationProviderBinding), (
            f"{overlay_name} provider {provider.provider_id} is not a delegation binding"
        )
        assert provider.backend_id == "local-coder-mlx"
        assert provider.source == "external-client"
        # Identity preservation: the pinned backend must serve the very model
        # string this overlay names. This is the assertion that distinguishes
        # a real migration from a silent model swap.
        assert provider.model in _PROVEN_DELEGATION_MODELS


@pytest.mark.unit
def test_batch_1_task_type_is_a_member_of_the_closed_literal() -> None:
    # ModelSODelegationProviderBinding.task_type is a closed Literal; this
    # asserts the chosen value is still a member, so a later narrowing of the
    # platform's task_type set fails here rather than at dispatch time.
    for overlay_name in sorted(_MIGRATED_BATCH_1):
        overlay = load_application_overlay(_OVERLAY_DIR / overlay_name)
        for provider in overlay.llm.providers:
            assert isinstance(provider, ModelSODelegationProviderBinding)
            assert provider.task_type == "agent_delegation"


# ---------------------------------------------------------------------------
# AC5 -- no published science is touched by this batch
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("overlay_name", sorted(_MIGRATED_BATCH_1))
def test_batch_1_overlays_carry_no_published_battery_evidence(overlay_name: str) -> None:
    """A migrated overlay must have no published result to invalidate.

    Batch 1 landed BEFORE OMN-15482, under the temperature-dropped /
    prompt-shape-collapsed deltas, so it was only safe on a lane whose numbers
    were never published. That constraint is retained deliberately even though
    those two deltas are now closed: a migrated overlay still changes the
    serving path (delegation node, escalation ladder, quality gate) relative to
    the direct HTTP binding its published numbers were measured under, and
    equivalence of three request fields is not equivalence of the whole system.
    """
    referencing = [
        doc.relative_to(_ROOT).as_posix()
        for doc in sorted(_DOCS_DIR.rglob("*.md"))
        if overlay_name in doc.read_text(encoding="utf-8")
    ]
    assert referencing == [], (
        f"{overlay_name} is referenced by published docs {referencing}; migrating it "
        "would confound results recorded under the openai_compatible binding"
    )


@pytest.mark.unit
def test_preregistered_overlays_are_not_in_any_migration_batch() -> None:
    assert _PREREGISTERED_DELEGATION.isdisjoint(_MIGRATED_BATCH_1)


# ---------------------------------------------------------------------------
# AC4 -- blocking reasons are falsifiable, not prose
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_image_bearing_overlays_are_blocked_for_the_image_reason() -> None:
    image_blocked = {p.name for p in _overlay_paths() if _classify(p) == ("blocked", _REASON_IMAGE)}
    assert image_blocked == _IMAGE_BLOCKED


@pytest.mark.unit
def test_delegation_client_actually_rejects_an_image_request() -> None:
    """The image blocking reason must be a real behaviour, not a claim.

    Proves ``LlmBusDelegationClient`` raises rather than silently dropping
    the attachment -- silent dropping would make the 4 vision overlays
    migrate "successfully" while measuring a blank prompt.
    """
    binding = ModelSODelegationProviderBinding(
        kind="onex_delegation",
        provider_id="probe",
        backend_id="local-coder-mlx",
        task_type="agent_delegation",
        model="mlx-community/Qwen3.6-35B-A3B-8bit",
        max_tokens=128,
        timeout_seconds=30.0,
        omnibase_infra_path=Path("../omnibase_infra"),
        state_root=Path(".onex_state/probe"),
    )

    def _never_called(argv: tuple[str, ...], *, timeout_seconds: float) -> str:
        raise AssertionError("the CLI must never be reached for an image request")

    client = LlmBusDelegationClient(
        config=binding,
        new_correlation_id=lambda: __import__("uuid").UUID(int=1),
        runner=type("R", (), {"run": staticmethod(_never_called)})(),
    )

    request = ModelSOLlmCompletionRequest(
        system_prompt="you are a mech pilot",
        user_prompt="what do you do",
        persona="berserker",
        temperature=0.4,
        json_mode=False,
        evidence_context=None,
        image_attachment=ModelSOLlmImageAttachment(png_bytes=b"\x89PNG", sha256_hex="0" * 64),
    )

    with pytest.raises(ValueError, match="does not support image_attachment"):
        client.complete(request)


@pytest.mark.unit
def test_no_unmigrated_overlay_names_a_proven_delegation_model() -> None:
    """The load-bearing reason batch 1 is one overlay and not fifteen.

    If this ever fails, a delegation-servable overlay is sitting unmigrated
    and belongs in the next batch -- which is exactly the signal this census
    should surface.
    """
    servable = [
        p.name
        for p in _overlay_paths()
        if _classify(p)[0] == "blocked" and set(_provider_models(p)) <= _PROVEN_DELEGATION_MODELS
    ]
    assert servable == []


@pytest.mark.unit
def test_unmigrated_overlays_still_use_the_supported_openai_compatible_binding() -> None:
    """OpenAICompatibleClient stays supported for non-migrated arms.

    Plan §3 P2 / hostile finding #9: the unmigrated remainder is an owned
    decision, not an unowned gap. This asserts the remainder is still a
    loadable, typed openai_compatible binding rather than something broken.
    """
    for path in _overlay_paths():
        if _classify(path)[0] != "blocked":
            continue
        overlay = load_application_overlay(path)
        for provider in overlay.llm.providers:
            assert isinstance(provider, ModelSOOpenAICompatibleProviderBinding), (
                f"{path.name} is unmigrated but does not carry a supported "
                "openai_compatible binding"
            )
