"""OMN-15166 quarantined smoke match -- proves the display-salience mechanism
RENDERS through a real match, on the real delegation-bound provider.

Explicitly NOT battery evidence. This is the ONE smoke match this ticket's
own instructions permit ("a single smoke match to prove the mechanism
renders is allowed ONLY after the prereg commit, and its data is
quarantined"). It proves the plumbing end to end -- the REAL, committed
``pilot.llm.delegation_salience_prominent_berserker`` spec, resolved
through the REAL ``ApplicationPilotFactory.from_spec`` seam into a real
``LLMPilot`` wired to a real ``LlmBusDelegationClient`` -- reaches the real
``node_delegate_skill_orchestrator`` -> the real ``.200:8401`` MLX endpoint,
by capturing the ACTUAL wire request text the client sent and asserting it
carries the prominent-only markers.
``tests/llm/test_llm_pilot.py``'s unit suite already proves the serializer
function in isolation with a fake client; this is the live re-confirmation
that the composition wiring is correct end to end, on real infra -- not a
second copy of that unit proof.

Driven through the SAME hermetic test harness as the whole objectives-arm
family (``tests.runtime.match_runner`` + ``pilots_override``, per
``tests/contracts/test_objmask_overlay.py``'s own ``_prompt_stream``
pattern) rather than the full ``ApplicationOverlay``/``so run`` launch path
-- this needs no ``pilot_registry_dir``/loadout-pairing setup at all,
because the pilot under test is injected directly.

Explicit non-goals: no seed/statistics claim (n=1, one match, quarantined by
design), no battery-lane contamination/pre-registration-timing checker run
against it (there is no battery ledger for those checkers to read -- this is
a single ad hoc match, not a driver-launched lane), no Kafka forwarding
(unrelated to what this test proves; OMN-15170's own live driver test
covers that separately). The battery itself (n=30 per lane, through the
platform node path) is OMN-15172's acceptance run.

Gating (two independent layers):

1. ``pytest.mark.live`` -- the one category CI excludes, via its
   ``-m "not live"`` selection (``.github/workflows/ci.yml``), same as every
   other test in this package.
2. An explicit ``STEEL_LIVE_SALIENCE_SMOKE=1`` environment opt-in, separate
   from OMN-15170's own ``STEEL_LIVE_DRIVER`` (different scope: this test
   needs no Kafka/``confluent_kafka`` extra at all, so it should never be
   accidentally gated together with the Kafka-dependent driver test).
"""

from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import yaml  # type: ignore[import-untyped]

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.contracts.application import ModelSODelegationProviderBinding
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.contracts.pilot import (
    ModelSOLlmPilotParams,
    ModelSOPilotSpec,
    SODisplaySalience,
)
from steel_onslaught.llm.client_delegation import LlmBusDelegationClient
from steel_onslaught.llm.personas import PersonaRegistry
from steel_onslaught.llm.pilot import LLMPilot
from steel_onslaught.llm.schemas import LlmResponse, ModelSOLlmCompletionRequest, ProtocolLlmClient
from steel_onslaught.match.composition import load_match_contract_catalog
from steel_onslaught.pilots.schemas import (
    ModelSOConsideredAction,
    ModelSOPilotDecision,
    ModelSOPilotObservation,
    SOPilotAction,
    SOPilotReasonCode,
)
from tests.runtime import match_runner

pytestmark = pytest.mark.live

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CATALOG_DIR = _REPO_ROOT / "contracts_data"
_PROMINENT_PILOT_SPEC = (
    _CATALOG_DIR / "pilots" / "delegation_salience" / "llm_delegation_berserker_prominent.yaml"
)
_LOADOUT = _CATALOG_DIR / "loadouts" / "example_aggressive_light.yaml"
_ARENA_ID = "foundry_60_asym_v1"
_ENV_OPT_IN = "STEEL_LIVE_SALIENCE_SMOKE"
_PINNED_MODEL = "mlx-community/Qwen3.6-35B-A3B-8bit"
_MAX_TICKS = 3
_DELEGATION_MAX_TOKENS = 96
_DELEGATION_TIMEOUT_SECONDS = 180.0


def _require_live_opt_in() -> None:
    if os.environ.get(_ENV_OPT_IN) != "1":
        pytest.skip(
            f"set {_ENV_OPT_IN}=1 to run the OMN-15166 quarantined smoke match against "
            "real infra (the .200 MLX server via the delegation chain)"
        )


class _HoldPilot:
    """Deterministic pilot that stands its ground -- no LLM call, blue seat."""

    def decide(self, observation: ModelSOPilotObservation) -> ModelSOPilotDecision:
        return ModelSOPilotDecision(
            action=SOPilotAction.REMAIN,
            reason_code=SOPilotReasonCode.NO_VIABLE_ACTION,
            confidence=1.0,
            considered_actions=(ModelSOConsideredAction(action=SOPilotAction.REMAIN, score=1.0),),
        )


class _RecordingDelegationClient:
    """Wraps the REAL ``LlmBusDelegationClient`` and records every request/
    response verbatim -- the delegation call itself is never faked; only the
    request/response pair is additionally captured for assertion."""

    def __init__(self, inner: ProtocolLlmClient) -> None:
        self._inner = inner
        self.requests: list[ModelSOLlmCompletionRequest] = []
        self.responses: list[LlmResponse] = []

    def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
        self.requests.append(request)
        response = self._inner.complete(request)
        self.responses.append(response)
        return response


def _fixed_correlation_id() -> UUID:
    return uuid4()


@pytest.mark.live
def test_prominent_salience_renders_in_a_real_match_via_the_delegation_chain(
    tmp_path: Path,
) -> None:
    """QUARANTINED SMOKE MATCH -- not battery evidence, n=1, one match.

    Loads the REAL committed pilot spec
    (``contracts_data/pilots/delegation_salience/
    llm_delegation_berserker_prominent.yaml``), constructs an ``LLMPilot``
    from it exactly as ``ApplicationPilotFactory.llm_pilot`` would (same
    constructor kwargs, same ``display_salience`` threading), drives a real
    match on ``foundry_60_asym_v1`` (real objectives, real vp_threshold),
    and asserts the wire request the REAL delegation client sent carries
    the prominent-only markers -- then asserts a real completion came back.
    """
    _require_live_opt_in()

    spec = ModelSOPilotSpec.model_validate(
        yaml.safe_load(_PROMINENT_PILOT_SPEC.read_text(encoding="utf-8"))
    )
    assert isinstance(spec.parameters, ModelSOLlmPilotParams)
    assert spec.parameters.display_salience is SODisplaySalience.PROMINENT

    omnibase_infra_path = Path(os.environ["OMNI_HOME"]) / "omnibase_infra"
    provider = ModelSODelegationProviderBinding(
        kind="onex_delegation",
        provider_id="onex-local-coder-mlx",
        backend_id="local-coder-mlx",
        task_type="agent_delegation",
        model=_PINNED_MODEL,
        max_tokens=_DELEGATION_MAX_TOKENS,
        timeout_seconds=_DELEGATION_TIMEOUT_SECONDS,
        omnibase_infra_path=omnibase_infra_path,
        state_root=tmp_path / "delegation_state",
    )
    real_client = LlmBusDelegationClient(config=provider, new_correlation_id=_fixed_correlation_id)
    recording_client = _RecordingDelegationClient(real_client)

    personas = PersonaRegistry.load(_CATALOG_DIR / "pilots" / "personas")
    pilot = LLMPilot(
        client=recording_client,
        persona=personas.require(spec.parameters.persona),
        failure_policy="raise",
        display_salience=spec.parameters.display_salience,
    )

    catalog = load_match_contract_catalog(_CATALOG_DIR)
    loadout = ModelSOLoadout.model_validate(yaml.safe_load(_LOADOUT.read_text(encoding="utf-8")))
    bus = InProcessEventBus()
    runner, _ = match_runner(
        bus=bus,
        match_id="match.smoke.omn15166-salience",
        seed=11,
        loadout_a=loadout,
        loadout_b=loadout,
        max_ticks=_MAX_TICKS,
        arena_override=catalog.arenas[_ARENA_ID],
        pilots_override={"mech.a.01": pilot, "mech.b.01": _HoldPilot()},
    )
    runner.run()

    assert recording_client.requests, (
        "the delegation-bound prominent-salience pilot was never asked to decide -- "
        "the smoke match produced zero completion requests"
    )
    prompt = recording_client.requests[0].user_prompt
    assert "!!! OBJECTIVES -- SCORING NOW" in prompt
    assert "REMINDER: capturing objectives is how this match is won." in prompt
    assert "--- OBJECTIVES" not in prompt

    served_models = [response.model for response in recording_client.responses]
    assert served_models, "no completion response was ever returned by the real delegation call"

    print(
        "\nOMN-15166 quarantined smoke-match proof (NOT battery evidence, n=1, one match):\n"
        f"  requests_sent={len(recording_client.requests)}\n"
        f"  served_models={served_models}\n"
        f"  first_prompt_carries_prominent_marker="
        f"{'!!! OBJECTIVES -- SCORING NOW' in prompt}\n"
        f"  first_response_text={recording_client.responses[0].text[:200]!r}\n"
    )
