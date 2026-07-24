"""Cross-architecture B: Gemma-over-OpenRouter combined utility+asym overlay.

Guards the CROSS-ARCHITECTURE (Google Gemma, lineage-independent from Qwen and
DeepSeek) arm prerequisites — the Gemma twin of
``test_ogate_objectives_battery_deepseek_driver.py`` with the added secret-
injection surface the free OpenRouter arm requires:

- the NEW combined gemma overlay
  ``tactical_split_overdeal_utility_asym_v1_gemma.yaml`` parses and carries the
  asym objective arena (``foundry_60_asym_v1`` — objectives + vp_threshold), the
  utility pile (per-seat ``utility`` quota + ``utility_deck_id`` +
  ``utility_handler_pack``), an ``injected`` secret resolver, and the Gemma-over-
  OpenRouter provider deltas (endpoint openrouter.ai, model pinned EXACTLY to
  ``google/gemma-4-26b-a4b-it:free``, secret_ref present, max_tokens 2048,
  timeout 120, bounded 429-retry) with the gemma pilots + registry;
- the driver ``--red-loadout`` / ``--blue-loadout`` flags select the gemma
  loadouts, and ``_lane_overlay`` repoints its state surfaces cleanly;
- the battery driver's ``_select_secret_resolver`` maps ``secret://llm/openrouter``
  from the environment / ~/.omnibase/.env WITHOUT a hardcoded key, fails closed
  when the key is absent, and leaves the keyless arms byte-identical;
- the SO OpenAI-compatible client retries transient HTTP 429 with the overlay's
  declared bounded exponential backoff (the free-pool 429 robustness the arm
  needs), proven end-to-end against the gemma provider config.

Every test is OFFLINE/structural: no live battery, no real key. The mapping
tests inject a FAKE key via monkeypatch (never a real credential), so CI — which
has no OpenRouter key — runs them green.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.run_ogate_objectives_battery import (
    _ARENA_ID,
    _build_parser,
    _EnvBackedSecretResolver,
    _lane_overlay,
    _select_secret_resolver,
)
from steel_onslaught.contracts.application import (
    ModelSOOpenAICompatibleProviderBinding,
    ModelSOSecretRef,
)
from steel_onslaught.contracts.pilot import ModelSOLlmPilotParams
from steel_onslaught.llm.client_http import (
    NoSecretResolver,
    OpenAICompatibleClient,
)
from steel_onslaught.llm.schemas import (
    LlmTransportError,
    ModelSOLlmCompletionRequest,
    ModelSOOpenAIChatRequest,
    ModelSOOpenAIChatResponse,
    SecretResolutionError,
)
from steel_onslaught.match.composition import (
    load_application_overlay,
    load_match_contract_catalog,
    load_pilot_registry,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_OVERLAYS_DIR = _REPO_ROOT / "contracts_data/overlays"
_GEMMA_OVERLAY = _OVERLAYS_DIR / "tactical_split_overdeal_utility_asym_v1_gemma.yaml"
_GEMMA_RED_LOADOUT = _REPO_ROOT / "contracts_data/loadouts/gemma/berserker_scout.yaml"
_GEMMA_BLUE_LOADOUT = _REPO_ROOT / "contracts_data/loadouts/gemma/sniper_ironclad.yaml"
_QWEN_OVERLAY = _OVERLAYS_DIR / "tactical_split_overdeal_asym_v1_qwen.yaml"
_DEEPSEEK_OVERLAY = _OVERLAYS_DIR / "tactical_split_overdeal_utility_asym_v1_deepseek.yaml"

_PINNED_MODEL_SLUG = "google/gemma-4-26b-a4b-it:free"
_OPENROUTER_REF = "secret://llm/openrouter"

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Driver --red-loadout / --blue-loadout: gemma loadouts selectable
# ---------------------------------------------------------------------------


def test_loadout_args_select_the_gemma_loadouts() -> None:
    args = _build_parser().parse_args(
        [
            "--overlay",
            str(_GEMMA_OVERLAY),
            "--red-loadout",
            str(_GEMMA_RED_LOADOUT),
            "--blue-loadout",
            str(_GEMMA_BLUE_LOADOUT),
        ]
    )
    assert args.overlay == _GEMMA_OVERLAY
    assert args.red_loadout == _GEMMA_RED_LOADOUT
    assert args.blue_loadout == _GEMMA_BLUE_LOADOUT


# ---------------------------------------------------------------------------
# Combined gemma overlay shape: asym objective arena AND utility pile
# ---------------------------------------------------------------------------


def test_gemma_overlay_binds_the_asym_objective_arena() -> None:
    overlay = load_application_overlay(_GEMMA_OVERLAY)
    assert overlay.contracts.arena_id == "foundry_60_asym_v1"
    catalog = load_match_contract_catalog(_REPO_ROOT / "contracts_data")
    arena = catalog.arenas[overlay.contracts.arena_id]
    assert arena.vp_threshold == 15
    assert {o.objective_id for o in arena.objectives} == {
        "objective.west_yard",
        "objective.north_works",
        "objective.east_gate",
    }


def test_gemma_overlay_deals_a_utility_pile_that_competes_for_the_registers() -> None:
    overlay = load_application_overlay(_GEMMA_OVERLAY)
    catalog = overlay.contracts.card_catalog
    assert catalog is not None
    assert catalog.deck_policy is not None
    seats = catalog.deck_policy.seats
    assert {s.side for s in seats} == {"red", "blue"}
    for seat in seats:
        assert seat.hand_quota.movement == 4
        assert seat.hand_quota.weapon == 4
        assert seat.hand_quota.utility == 2
        assert seat.register_count == 5
        assert seat.utility_deck_id == "deck.utility.v1"


def test_gemma_overlay_names_the_full_utility_handler_pack() -> None:
    overlay = load_application_overlay(_GEMMA_OVERLAY)
    pack = overlay.contracts.utility_handler_pack
    assert pack is not None
    assert pack.pack_id == "utility.resolution.v1"
    assert tuple(pack.handler_ids) == (
        "utility.smoke.v1",
        "utility.chaff.v1",
        "utility.flares.v1",
    )


# ---------------------------------------------------------------------------
# Gemma-over-OpenRouter provider deltas: exact pinned slug + injected secret
# ---------------------------------------------------------------------------


def test_gemma_overlay_pins_the_exact_free_gemma_slug_over_openrouter() -> None:
    overlay = load_application_overlay(_GEMMA_OVERLAY)
    assert overlay.llm.secret_resolver.kind == "injected"
    (provider,) = overlay.llm.providers
    assert isinstance(provider, ModelSOOpenAICompatibleProviderBinding)
    assert provider.provider_id == "gemma"
    # Exact pinned slug — NOT the openrouter/free auto-router — so attribution
    # is unambiguous and the ``:free`` tier keeps cost at $0.
    assert provider.model == _PINNED_MODEL_SLUG
    assert provider.model != "openrouter/free"
    assert provider.endpoint_url == "https://openrouter.ai/api/v1/chat/completions"
    # Authenticated arm: an opaque secret ref is present, never a raw key.
    assert provider.secret_ref is not None
    assert str(provider.secret_ref.ref) == _OPENROUTER_REF
    assert provider.max_tokens == 2048
    assert provider.timeout_seconds == 120.0
    assert overlay.llm.model_identities[0].model_identity_id == "model_identity.gemma"
    assert overlay.llm.model_identities[0].provider_binding_id == "gemma"


def test_gemma_overlay_declares_bounded_exponential_backoff_429_retry() -> None:
    """The overlay activates the client's 429-retry on the battery path.

    The SO OpenAI-compatible client maps HTTP 429 to a retryable transport
    error and retries retryable errors with exponential backoff up to
    ``retry.max_attempts``. The UNSELECTED battery path honors ``max_attempts``,
    so a value > 1 (with a real backoff schedule) is what turns intermittent
    OpenRouter free-pool 429s into a bounded retry rather than a hard failure.
    """

    overlay = load_application_overlay(_GEMMA_OVERLAY)
    (provider,) = overlay.llm.providers
    assert isinstance(provider, ModelSOOpenAICompatibleProviderBinding)
    assert provider.retry.max_attempts > 1
    assert provider.retry.max_attempts == 4
    assert provider.retry.initial_backoff_seconds == 2.0
    assert provider.retry.backoff_multiplier == 2.0


def test_gemma_overlay_programs_the_gemma_pilots_and_registry() -> None:
    overlay = load_application_overlay(_GEMMA_OVERLAY)
    catalog = overlay.contracts.card_catalog
    assert catalog is not None
    assert tuple(p.pilot_spec_id for p in catalog.programmers) == (
        "pilot.llm.gemma_berserker",
        "pilot.llm.gemma_sniper",
    )
    assert (
        overlay.contracts.pilot_registry_dir
        == (_REPO_ROOT / "contracts_data/pilots/fire_dense_gemma").resolve()
    )
    registry = load_pilot_registry(overlay.contracts.pilot_registry_dir)
    for pilot_id, persona in (
        ("pilot.llm.gemma_berserker", "berserker"),
        ("pilot.llm.gemma_sniper", "sniper"),
    ):
        spec = registry.get(pilot_id)
        assert spec is not None
        assert isinstance(spec.parameters, ModelSOLlmPilotParams)
        assert spec.parameters.provider == "gemma"
        assert spec.parameters.persona == persona


def test_gemma_loadouts_bind_the_gemma_pilots() -> None:
    from steel_onslaught.match.composition import load_loadout

    red = load_loadout(_GEMMA_RED_LOADOUT)
    blue = load_loadout(_GEMMA_BLUE_LOADOUT)
    assert red.id == "loadout.llm.gemma_berserker"
    assert red.pilot_id == "pilot.llm.gemma_berserker"
    assert blue.id == "loadout.llm.gemma_sniper_ironclad"
    assert blue.pilot_id == "pilot.llm.gemma_sniper"


def test_lane_overlay_repoints_surfaces_for_the_gemma_overlay(tmp_path: Path) -> None:
    overlay = _lane_overlay(tmp_path, _GEMMA_OVERLAY)
    assert overlay.contracts.arena_id == _ARENA_ID
    assert overlay.llm.secret_resolver.kind == "injected"
    assert overlay.event_ledger.path == tmp_path / "events.sqlite3"
    assert overlay.leaderboard.path == tmp_path / "leaderboard.sqlite3"
    assert overlay.learning_artifacts.lineage_root == tmp_path / "lineage"
    assert overlay.evaluation_storage.root == tmp_path / "evaluation_storage"


# ---------------------------------------------------------------------------
# Secret injection: env-backed resolver, no hardcoded key, fail-closed
# ---------------------------------------------------------------------------


def test_no_credential_material_is_committed_in_the_gemma_arm_files() -> None:
    """The overlay/loadout/pilot files carry only the opaque secret ref."""

    for path in (
        _GEMMA_OVERLAY,
        _GEMMA_RED_LOADOUT,
        _GEMMA_BLUE_LOADOUT,
        _REPO_ROOT / "contracts_data/pilots/fire_dense_gemma/llm_gemma_berserker.yaml",
        _REPO_ROOT / "contracts_data/pilots/fire_dense_gemma/llm_gemma_sniper.yaml",
    ):
        lowered = path.read_text(encoding="utf-8").lower()
        # OpenRouter keys are prefixed ``sk-or-``; no such token may appear.
        assert "sk-or-" not in lowered
        # No inline Bearer credential (the ``Authorization`` header is only
        # mentioned in prose, never populated with a token here).
        assert "bearer sk" not in lowered
        assert "authorization: bearer" not in lowered
    # The overlay references the credential only by its opaque name.
    assert _OPENROUTER_REF in _GEMMA_OVERLAY.read_text(encoding="utf-8")


def test_env_backed_resolver_maps_the_openrouter_ref_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A FAKE key via the process env (which wins over ~/.omnibase/.env); the
    # real key is never needed and the dotenv is neutralized for determinism.
    monkeypatch.setattr("scripts.run_ogate_objectives_battery._load_omnibase_dotenv", lambda: {})
    monkeypatch.setenv("OPEN_ROUTER_API_KEY", "sk-or-FAKE-TEST-VALUE")
    resolver = _EnvBackedSecretResolver.for_references((_OPENROUTER_REF,))
    resolved = resolver.resolve(ModelSOSecretRef(kind="opaque", ref=_OPENROUTER_REF))
    assert resolved == "sk-or-FAKE-TEST-VALUE"


def test_env_backed_resolver_accepts_the_openrouter_api_key_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("scripts.run_ogate_objectives_battery._load_omnibase_dotenv", lambda: {})
    monkeypatch.delenv("OPEN_ROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-ALIAS-FAKE")
    resolver = _EnvBackedSecretResolver.for_references((_OPENROUTER_REF,))
    assert (
        resolver.resolve(ModelSOSecretRef(kind="opaque", ref=_OPENROUTER_REF)) == "sk-or-ALIAS-FAKE"
    )


def test_env_backed_resolver_fails_closed_when_the_key_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("scripts.run_ogate_objectives_battery._load_omnibase_dotenv", lambda: {})
    monkeypatch.delenv("OPEN_ROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(SecretResolutionError):
        _EnvBackedSecretResolver.for_references((_OPENROUTER_REF,))


def test_env_backed_resolver_rejects_an_unknown_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("scripts.run_ogate_objectives_battery._load_omnibase_dotenv", lambda: {})
    with pytest.raises(SecretResolutionError):
        _EnvBackedSecretResolver.for_references(("secret://llm/unknown",))


def test_select_secret_resolver_binds_the_env_resolver_for_the_gemma_overlay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("scripts.run_ogate_objectives_battery._load_omnibase_dotenv", lambda: {})
    monkeypatch.setenv("OPEN_ROUTER_API_KEY", "sk-or-FAKE-SELECT")
    overlay = load_application_overlay(_GEMMA_OVERLAY)
    resolver = _select_secret_resolver(overlay)
    assert isinstance(resolver, _EnvBackedSecretResolver)
    assert (
        resolver.resolve(ModelSOSecretRef(kind="opaque", ref=_OPENROUTER_REF))
        == "sk-or-FAKE-SELECT"
    )


def test_select_secret_resolver_leaves_the_keyless_arms_byte_identical() -> None:
    # Keyless-but-injected (qwen, secret_ref null) -> never-consulted resolver.
    qwen = load_application_overlay(_QWEN_OVERLAY)
    assert qwen.llm.secret_resolver.kind == "injected"
    assert isinstance(_select_secret_resolver(qwen), NoSecretResolver)
    # Keyless ``none`` (deepseek) -> composition builds its own; driver passes None.
    deepseek = load_application_overlay(_DEEPSEEK_OVERLAY)
    assert deepseek.llm.secret_resolver.kind == "none"
    assert _select_secret_resolver(deepseek) is None


# ---------------------------------------------------------------------------
# 429 robustness: client retries a 429 with the overlay's exact backoff
# ---------------------------------------------------------------------------


class _Sleeper:
    def __init__(self) -> None:
        self.calls: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.calls.append(seconds)


class _StaticKeyResolver:
    def resolve(self, reference: ModelSOSecretRef) -> str:
        return "sk-or-FAKE-RETRY"


class _SequenceTransport:
    """Yields queued outcomes; a 429 is modeled as a retryable transport error."""

    def __init__(self, outcomes: list[ModelSOOpenAIChatResponse | Exception]) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        request: ModelSOOpenAIChatRequest,
        timeout_seconds: float,
    ) -> ModelSOOpenAIChatResponse:
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _ok_response() -> ModelSOOpenAIChatResponse:
    return ModelSOOpenAIChatResponse.model_validate(
        {
            "id": "ok",
            "choices": (
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "{}"},
                    "finish_reason": "stop",
                },
            ),
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            "model": _PINNED_MODEL_SLUG,
        }
    )


def test_client_retries_transient_429_with_the_gemma_overlay_backoff_schedule() -> None:
    """End-to-end: three 429s then success, under the gemma provider config.

    HTTP 429 is classified retryable by the transport (proven separately in
    tests/llm/test_client_http.py); here we drive the OpenAICompatibleClient
    with the gemma overlay's own retry config and assert the bounded
    exponential backoff (2s -> 4s -> 8s) fires and the fourth attempt succeeds.
    """

    overlay = load_application_overlay(_GEMMA_OVERLAY)
    (provider,) = overlay.llm.providers
    assert isinstance(provider, ModelSOOpenAICompatibleProviderBinding)

    rate_limited = LlmTransportError("LLM provider returned HTTP 429", retryable=True)
    transport = _SequenceTransport([rate_limited, rate_limited, rate_limited, _ok_response()])
    sleeper = _Sleeper()
    client = OpenAICompatibleClient(
        config=provider,
        transport=transport,
        secret_resolver=_StaticKeyResolver(),
        sleeper=sleeper,
    )
    response = client.complete(
        ModelSOLlmCompletionRequest(
            system_prompt="s",
            user_prompt="u",
            persona="berserker",
            temperature=0.7,
            json_mode=True,
            evidence_context=None,
        )
    )
    assert response.text == "{}"
    assert transport.calls == 4  # 3 retried 429s + 1 success
    assert sleeper.calls == [2.0, 4.0, 8.0]  # bounded exponential backoff
