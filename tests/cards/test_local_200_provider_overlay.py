"""Contract proofs for the local_200 provider.

OMN-15160 migrated the untracked top-level ``pilots/llm_local_200.yaml``
scratch config into the tracked ``contracts_data`` provider-reference shape:
a dedicated pilot registry dir (``contracts_data/pilots/local_200``) plus an
overlay (``contracts_data/overlays/local_200_v1.yaml``).

OMN-15174 (batch 1) then migrated that overlay's provider binding from
``kind: openai_compatible`` to ``kind: onex_delegation``, pinning
``backend_id: local-coder-mlx``. The endpoint fact this module used to guard
(a complete ``/v1/chat/completions`` suffix on ``endpoint_url``) no longer
lives on the binding at all -- ``ModelSODelegationProviderBinding`` has no
``endpoint_url``; the endpoint is resolved platform-side from ``backend_id``.
The equivalent guard on the delegation shape is the backend/model identity
assertion below: ``local-coder-mlx``'s ``model_name`` in omnimarket's
``bifrost_delegation.yaml`` is ``mlx-community/Qwen3.6-35B-A3B-8bit``, the
byte-identical string this overlay carried before migration, which is what
makes this particular migration identity-preserving rather than a silent
model swap. See ``tests/contracts/test_overlay_delegation_migration_omn15174
.py`` for the corpus-wide census and the per-overlay blocking reasons.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from steel_onslaught.contracts.application import ModelSODelegationProviderBinding
from steel_onslaught.contracts.pilot import ModelSOLlmPilotParams
from steel_onslaught.match.composition import load_application_overlay, load_pilot_registry

_ROOT = Path(__file__).resolve().parents[2]
_OVERLAY = _ROOT / "contracts_data/overlays/local_200_v1.yaml"

# The model string this overlay carried under its pre-OMN-15174
# ``openai_compatible`` binding, and which ``local-coder-mlx`` serves. Pinned
# verbatim: if these ever diverge, the migration stopped being
# identity-preserving and this lane is measuring a different model than the
# one it is named for.
_EXPECTED_MODEL = "mlx-community/Qwen3.6-35B-A3B-8bit"


@pytest.mark.unit
def test_local_200_overlay_binds_exact_backend_and_model() -> None:
    overlay = load_application_overlay(_OVERLAY)

    assert len(overlay.llm.providers) == 1
    provider = overlay.llm.providers[0]
    assert isinstance(provider, ModelSODelegationProviderBinding)
    assert provider.provider_id == "local_200"
    assert provider.model == _EXPECTED_MODEL
    assert overlay.llm.secret_resolver.kind == "none"

    # The identity assertion that replaces the old bare-base-URL guard: the
    # pinned backend is what decides which server actually answers, so a
    # regression to any other backend_id (or a model string drift away from
    # what that backend serves) is what this test exists to catch.
    assert provider.backend_id == "local-coder-mlx"
    assert provider.task_type == "agent_delegation"
    assert provider.source == "external-client"

    assert len(overlay.llm.model_identities) == 1
    assert overlay.llm.model_identities[0].model_identity_id == "model_identity.local_200"
    assert overlay.llm.model_identities[0].provider_binding_id == "local_200"
    assert overlay.contracts.arena_id == "foundry_60"
    assert overlay.contracts.card_catalog is None
    assert (
        overlay.contracts.pilot_registry_dir
        == (_ROOT / "contracts_data/pilots/local_200").resolve()
    )


@pytest.mark.unit
def test_local_200_pilot_registry_resolves_the_migrated_spec() -> None:
    overlay = load_application_overlay(_OVERLAY)
    registry = load_pilot_registry(overlay.contracts.pilot_registry_dir)

    spec = registry.get("pilot.llm.local_200")
    assert spec is not None
    assert spec.archetype == "llm"
    assert isinstance(spec.parameters, ModelSOLlmPilotParams)
    assert spec.parameters.provider == "local_200"
    assert spec.parameters.persona == "berserker"
    assert spec.lineage.parent == "pilot.template.llm"
