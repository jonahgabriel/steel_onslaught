"""Cross-architecture (Zhipu/GLM) combined utility+asym overlay + secret injection.

Guards the FOURTH-lineage (Zhipu GLM over the z.ai CODING plan) arm — the GLM
twin of ``test_ogate_objectives_battery_gemma_driver.py`` with the thinking-off
wiring the GLM hybrid-reasoning model requires:

- the NEW combined glm overlay
  ``tactical_split_overdeal_utility_asym_v1_glm.yaml`` parses and carries the
  asym objective arena (``foundry_60_asym_v1`` — objectives + vp_threshold), the
  utility pile (per-seat ``utility`` quota + ``utility_deck_id`` +
  ``utility_handler_pack``), an ``injected`` secret resolver, and the GLM-over-
  z.ai provider deltas (endpoint ``api.z.ai/api/coding/paas/v4``, model pinned
  EXACTLY to ``glm-4.5``, secret_ref present, max_tokens 4096, timeout 120,
  ``thinking: {type: disabled}``, single fail-loud attempt) with the glm pilots
  + registry;
- the driver ``--red-loadout`` / ``--blue-loadout`` flags select the glm
  loadouts, and ``_lane_overlay`` repoints its state surfaces cleanly;
- the battery driver's ``_select_secret_resolver`` maps ``secret://llm/glm``
  from the environment / ~/.omnibase/.env WITHOUT a hardcoded key, fails closed
  when the key is absent, and leaves the keyless AND openrouter arms
  byte-identical (no new key lookup, no forwarded request extension);
- the SO OpenAI-compatible client forwards the overlay's ``thinking`` control
  verbatim as a top-level ``thinking`` object on the request body, proven
  end-to-end against the glm provider config — and forwards NOTHING (the wire
  body stays byte-identical) for a provider that omits ``thinking``.

Every test is OFFLINE/structural: no live battery, no real key. The mapping
tests inject a FAKE key via monkeypatch (never a real credential), so CI — which
has no GLM key — runs them green.
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
    ModelSOThinkingBinding,
)
from steel_onslaught.contracts.pilot import ModelSOLlmPilotParams
from steel_onslaught.llm.client_http import (
    NoSecretResolver,
    OpenAICompatibleClient,
)
from steel_onslaught.llm.schemas import (
    ModelSOLlmCompletionRequest,
    ModelSOOpenAIChatRequest,
    ModelSOOpenAIChatResponse,
    SecretResolutionError,
)
from steel_onslaught.match.composition import (
    load_application_overlay,
    load_loadout,
    load_pilot_registry,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_OVERLAYS_DIR = _REPO_ROOT / "contracts_data/overlays"
_GLM_OVERLAY = _OVERLAYS_DIR / "tactical_split_overdeal_utility_asym_v1_glm.yaml"
_GLM_RED_LOADOUT = _REPO_ROOT / "contracts_data/loadouts/glm/berserker_scout.yaml"
_GLM_BLUE_LOADOUT = _REPO_ROOT / "contracts_data/loadouts/glm/sniper_ironclad.yaml"
_GEMMA_OVERLAY = _OVERLAYS_DIR / "tactical_split_overdeal_utility_asym_v1_gemma.yaml"
_QWEN_OVERLAY = _OVERLAYS_DIR / "tactical_split_overdeal_asym_v1_qwen.yaml"
_DEEPSEEK_OVERLAY = _OVERLAYS_DIR / "tactical_split_overdeal_utility_asym_v1_deepseek.yaml"

_PINNED_MODEL = "glm-4.5"
_GLM_ENDPOINT = "https://api.z.ai/api/coding/paas/v4/chat/completions"
_GLM_REF = "secret://llm/glm"
_GLM_ENV = "LLM_GLM_API_KEY"

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Driver --red-loadout / --blue-loadout: glm loadouts selectable
# ---------------------------------------------------------------------------


def test_loadout_args_select_the_glm_loadouts() -> None:
    args = _build_parser().parse_args(
        [
            "--overlay",
            str(_GLM_OVERLAY),
            "--red-loadout",
            str(_GLM_RED_LOADOUT),
            "--blue-loadout",
            str(_GLM_BLUE_LOADOUT),
        ]
    )
    assert args.overlay == _GLM_OVERLAY
    assert args.red_loadout == _GLM_RED_LOADOUT
    assert args.blue_loadout == _GLM_BLUE_LOADOUT


# ---------------------------------------------------------------------------
# Combined glm overlay shape: asym objective arena AND utility pile
# ---------------------------------------------------------------------------


def test_glm_overlay_binds_the_asym_objective_arena() -> None:
    from steel_onslaught.match.composition import load_match_contract_catalog

    overlay = load_application_overlay(_GLM_OVERLAY)
    assert overlay.contracts.arena_id == "foundry_60_asym_v1"
    catalog = load_match_contract_catalog(_REPO_ROOT / "contracts_data")
    arena = catalog.arenas[overlay.contracts.arena_id]
    assert arena.vp_threshold == 15
    assert {o.objective_id for o in arena.objectives} == {
        "objective.west_yard",
        "objective.north_works",
        "objective.east_gate",
    }


def test_glm_overlay_deals_a_utility_pile_that_competes_for_the_registers() -> None:
    overlay = load_application_overlay(_GLM_OVERLAY)
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


def test_glm_overlay_names_the_full_utility_handler_pack() -> None:
    overlay = load_application_overlay(_GLM_OVERLAY)
    pack = overlay.contracts.utility_handler_pack
    assert pack is not None
    assert pack.pack_id == "utility.resolution.v1"
    assert tuple(pack.handler_ids) == (
        "utility.smoke.v1",
        "utility.chaff.v1",
        "utility.flares.v1",
    )


# ---------------------------------------------------------------------------
# GLM-over-z.ai provider deltas: exact pinned model + injected secret + thinking
# ---------------------------------------------------------------------------


def test_glm_overlay_pins_the_lowpower_glm_model_over_zai() -> None:
    overlay = load_application_overlay(_GLM_OVERLAY)
    assert overlay.llm.secret_resolver.kind == "injected"
    (provider,) = overlay.llm.providers
    assert isinstance(provider, ModelSOOpenAICompatibleProviderBinding)
    assert provider.provider_id == "glm"
    # Exact pinned lower-power tier — NOT air/flash (unavailable on this
    # account; Air silently upgrades and misattributes).
    assert provider.model == _PINNED_MODEL
    assert provider.endpoint_url == _GLM_ENDPOINT
    # Authenticated arm: an opaque secret ref is present, never a raw key.
    assert provider.secret_ref is not None
    assert str(provider.secret_ref.ref) == _GLM_REF
    assert provider.max_tokens == 4096
    # Shortened so an intermittent z.ai coding-pool stall fails FAST and is
    # retried below, instead of blocking the whole match for 120 s then aborting.
    assert provider.timeout_seconds == 45.0
    # Flat-rate plan: the bounded retry absorbs intermittent transport STALLS
    # (not rate limits) so one pool stall no longer aborts the match.
    assert provider.retry.max_attempts == 4
    assert provider.retry.initial_backoff_seconds == 1.0
    assert provider.retry.backoff_multiplier == 2.0
    assert overlay.llm.model_identities[0].model_identity_id == "model_identity.glm"
    assert overlay.llm.model_identities[0].provider_binding_id == "glm"


def test_glm_overlay_declares_thinking_disabled() -> None:
    """The overlay carries the thinking-off control GLM needs to emit clean JSON.

    Without it, the GLM hybrid-reasoning model narrates chain-of-thought into
    ``content`` and overflows the register JSON (the DeepSeek failure mode).
    """

    overlay = load_application_overlay(_GLM_OVERLAY)
    (provider,) = overlay.llm.providers
    assert isinstance(provider, ModelSOOpenAICompatibleProviderBinding)
    assert isinstance(provider.thinking, ModelSOThinkingBinding)
    assert provider.thinking.type == "disabled"


def test_glm_overlay_programs_the_glm_pilots_and_registry() -> None:
    overlay = load_application_overlay(_GLM_OVERLAY)
    catalog = overlay.contracts.card_catalog
    assert catalog is not None
    assert tuple(p.pilot_spec_id for p in catalog.programmers) == (
        "pilot.llm.glm_berserker",
        "pilot.llm.glm_sniper",
    )
    assert (
        overlay.contracts.pilot_registry_dir
        == (_REPO_ROOT / "contracts_data/pilots/fire_dense_glm").resolve()
    )
    registry = load_pilot_registry(overlay.contracts.pilot_registry_dir)
    for pilot_id, persona in (
        ("pilot.llm.glm_berserker", "berserker"),
        ("pilot.llm.glm_sniper", "sniper"),
    ):
        spec = registry.get(pilot_id)
        assert spec is not None
        assert isinstance(spec.parameters, ModelSOLlmPilotParams)
        assert spec.parameters.provider == "glm"
        assert spec.parameters.persona == persona


def test_glm_loadouts_bind_the_glm_pilots() -> None:
    red = load_loadout(_GLM_RED_LOADOUT)
    blue = load_loadout(_GLM_BLUE_LOADOUT)
    assert red.id == "loadout.llm.glm_berserker"
    assert red.pilot_id == "pilot.llm.glm_berserker"
    assert blue.id == "loadout.llm.glm_sniper_ironclad"
    assert blue.pilot_id == "pilot.llm.glm_sniper"


def test_lane_overlay_repoints_surfaces_for_the_glm_overlay(tmp_path: Path) -> None:
    overlay = _lane_overlay(tmp_path, _GLM_OVERLAY)
    assert overlay.contracts.arena_id == _ARENA_ID
    assert overlay.llm.secret_resolver.kind == "injected"
    assert overlay.event_ledger.path == tmp_path / "events.sqlite3"
    assert overlay.leaderboard.path == tmp_path / "leaderboard.sqlite3"
    assert overlay.learning_artifacts.lineage_root == tmp_path / "lineage"
    assert overlay.evaluation_storage.root == tmp_path / "evaluation_storage"


# ---------------------------------------------------------------------------
# Secret injection: env-backed resolver, no hardcoded key, fail-closed
# ---------------------------------------------------------------------------


def test_no_credential_material_is_committed_in_the_glm_arm_files() -> None:
    """The overlay/loadout/pilot files carry only the opaque secret ref."""

    for path in (
        _GLM_OVERLAY,
        _GLM_RED_LOADOUT,
        _GLM_BLUE_LOADOUT,
        _REPO_ROOT / "contracts_data/pilots/fire_dense_glm/llm_glm_berserker.yaml",
        _REPO_ROOT / "contracts_data/pilots/fire_dense_glm/llm_glm_sniper.yaml",
    ):
        lowered = path.read_text(encoding="utf-8").lower()
        assert "bearer sk" not in lowered
        assert "authorization: bearer" not in lowered
        # No populated key value for the GLM env var appears in any file.
        assert f"{_GLM_ENV.lower()}=" not in lowered
        assert f"{_GLM_ENV.lower()}:" not in lowered
    # The overlay references the credential only by its opaque name.
    assert _GLM_REF in _GLM_OVERLAY.read_text(encoding="utf-8")


def test_env_backed_resolver_maps_the_glm_ref_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A FAKE key via the process env (which wins over ~/.omnibase/.env); the
    # real key is never needed and the dotenv is neutralized for determinism.
    monkeypatch.setattr("scripts.run_ogate_objectives_battery._load_omnibase_dotenv", lambda: {})
    monkeypatch.setenv(_GLM_ENV, "glm-FAKE-TEST-VALUE")
    resolver = _EnvBackedSecretResolver.for_references((_GLM_REF,))
    resolved = resolver.resolve(ModelSOSecretRef(kind="opaque", ref=_GLM_REF))
    assert resolved == "glm-FAKE-TEST-VALUE"


def test_env_backed_resolver_reads_glm_from_the_dotenv_when_env_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(_GLM_ENV, raising=False)
    monkeypatch.setattr(
        "scripts.run_ogate_objectives_battery._load_omnibase_dotenv",
        lambda: {_GLM_ENV: "glm-FAKE-DOTENV"},
    )
    resolver = _EnvBackedSecretResolver.for_references((_GLM_REF,))
    assert resolver.resolve(ModelSOSecretRef(kind="opaque", ref=_GLM_REF)) == "glm-FAKE-DOTENV"


def test_env_backed_resolver_fails_closed_when_the_glm_key_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("scripts.run_ogate_objectives_battery._load_omnibase_dotenv", lambda: {})
    monkeypatch.delenv(_GLM_ENV, raising=False)
    with pytest.raises(SecretResolutionError):
        _EnvBackedSecretResolver.for_references((_GLM_REF,))


def test_select_secret_resolver_binds_the_env_resolver_for_the_glm_overlay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("scripts.run_ogate_objectives_battery._load_omnibase_dotenv", lambda: {})
    monkeypatch.setenv(_GLM_ENV, "glm-FAKE-SELECT")
    overlay = load_application_overlay(_GLM_OVERLAY)
    resolver = _select_secret_resolver(overlay)
    assert isinstance(resolver, _EnvBackedSecretResolver)
    assert resolver.resolve(ModelSOSecretRef(kind="opaque", ref=_GLM_REF)) == "glm-FAKE-SELECT"


def test_select_secret_resolver_leaves_keyless_and_openrouter_arms_byte_identical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Keyless-but-injected (qwen, secret_ref null) -> never-consulted resolver.
    qwen = load_application_overlay(_QWEN_OVERLAY)
    assert qwen.llm.secret_resolver.kind == "injected"
    assert isinstance(_select_secret_resolver(qwen), NoSecretResolver)
    # Keyless ``none`` (deepseek) -> composition builds its own; driver passes None.
    deepseek = load_application_overlay(_DEEPSEEK_OVERLAY)
    assert deepseek.llm.secret_resolver.kind == "none"
    assert _select_secret_resolver(deepseek) is None
    # The openrouter (gemma) arm still resolves via its OWN ref, untouched by the
    # new glm mapping — the GLM env var is never consulted for it.
    monkeypatch.setattr("scripts.run_ogate_objectives_battery._load_omnibase_dotenv", lambda: {})
    monkeypatch.setenv("OPEN_ROUTER_API_KEY", "sk-or-FAKE-GEMMA")
    monkeypatch.delenv(_GLM_ENV, raising=False)
    gemma = load_application_overlay(_GEMMA_OVERLAY)
    resolver = _select_secret_resolver(gemma)
    assert isinstance(resolver, _EnvBackedSecretResolver)
    assert (
        resolver.resolve(ModelSOSecretRef(kind="opaque", ref="secret://llm/openrouter"))
        == "sk-or-FAKE-GEMMA"
    )


# ---------------------------------------------------------------------------
# Thinking-off wiring: request body carries thinking:{type:disabled}; else absent
# ---------------------------------------------------------------------------


class _CapturingTransport:
    """Records the exact serialized request body the client sends."""

    def __init__(self) -> None:
        self.body: dict[str, object] | None = None

    def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        request: ModelSOOpenAIChatRequest,
        timeout_seconds: float,
    ) -> ModelSOOpenAIChatResponse:
        # The exact bytes every concrete transport (httpx / urllib) posts.
        self.body = request.model_dump(mode="json", exclude_none=True)
        return _ok_response()


class _StaticKeyResolver:
    def resolve(self, reference: ModelSOSecretRef) -> str:
        return "glm-FAKE"


class _NullSleeper:
    def sleep(self, seconds: float) -> None:  # pragma: no cover - never sleeps here
        pass


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
            "model": _PINNED_MODEL,
        }
    )


def _completion_request() -> ModelSOLlmCompletionRequest:
    return ModelSOLlmCompletionRequest(
        system_prompt="s",
        user_prompt="u",
        persona="sniper",
        temperature=0.7,
        json_mode=True,
        evidence_context=None,
    )


def test_client_emits_thinking_disabled_in_the_glm_request_body() -> None:
    overlay = load_application_overlay(_GLM_OVERLAY)
    (provider,) = overlay.llm.providers
    assert isinstance(provider, ModelSOOpenAICompatibleProviderBinding)
    transport = _CapturingTransport()
    client = OpenAICompatibleClient(
        config=provider,
        transport=transport,
        secret_resolver=_StaticKeyResolver(),
        sleeper=_NullSleeper(),
    )
    response = client.complete(_completion_request())
    assert response.text == "{}"
    # The thinking control travels as a top-level object on the posted body.
    assert transport.body is not None
    assert transport.body["thinking"] == {"type": "disabled"}
    assert transport.body["model"] == _PINNED_MODEL


def test_client_omits_thinking_when_the_provider_does_not_declare_it() -> None:
    """A keyless/openrouter provider (no ``thinking``) posts a byte-identical body.

    ``model_dump(exclude_none=True)`` drops the ``thinking`` field entirely, so
    the openrouter (gemma) arm's request body is unchanged by this feature.
    """

    gemma = load_application_overlay(_GEMMA_OVERLAY)
    (provider,) = gemma.llm.providers
    assert isinstance(provider, ModelSOOpenAICompatibleProviderBinding)
    assert provider.thinking is None
    transport = _CapturingTransport()
    client = OpenAICompatibleClient(
        config=provider,
        transport=transport,
        secret_resolver=_StaticKeyResolver(),
        sleeper=_NullSleeper(),
    )
    response = client.complete(_completion_request())
    assert response.text == "{}"
    assert transport.body is not None
    assert "thinking" not in transport.body
