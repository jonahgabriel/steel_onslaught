"""Contract proofs for the local_200 provider (OMN-15160 pilots/ migration).

Migrates the untracked top-level ``pilots/llm_local_200.yaml`` scratch config
into the tracked ``contracts_data`` provider-reference shape: a dedicated
pilot registry dir (``contracts_data/pilots/local_200``) plus an overlay
(``contracts_data/overlays/local_200_v1.yaml``) carrying the endpoint/model
facts on ``llm.providers[]``, exactly like ``standard_v1_qwen.yaml`` carries
``endpoint_url``/``model`` for ``provider_id: qwen35``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from steel_onslaught.contracts.application import ModelSOOpenAICompatibleProviderBinding
from steel_onslaught.contracts.pilot import ModelSOLlmPilotParams
from steel_onslaught.match.composition import load_application_overlay, load_pilot_registry

_ROOT = Path(__file__).resolve().parents[2]
_OVERLAY = _ROOT / "contracts_data/overlays/local_200_v1.yaml"

# The exact complete chat-completions path this provider must carry.
# ModelSOOpenAICompatibleProviderBinding._complete_http_endpoint only checks
# that endpoint_url is a well-formed http(s) URL with no query/fragment/user
# info -- it does NOT check for a "/chat/completions" (or any) path suffix,
# so a bare-base regression (e.g. "http://stickybeatz-studio:8401/v1") would
# pass that validator silently. This test is the guard the validator does not
# provide.
_EXPECTED_ENDPOINT_URL = "http://stickybeatz-studio:8401/v1/chat/completions"


@pytest.mark.unit
def test_local_200_overlay_binds_exact_endpoint_and_model() -> None:
    overlay = load_application_overlay(_OVERLAY)

    assert len(overlay.llm.providers) == 1
    provider = overlay.llm.providers[0]
    assert isinstance(provider, ModelSOOpenAICompatibleProviderBinding)
    assert provider.provider_id == "local_200"
    assert provider.model == "mlx-community/Qwen3.6-35B-A3B-8bit"
    assert provider.secret_ref is None
    assert overlay.llm.secret_resolver.kind == "none"

    # The suffix assertion: the validator accepts a bare base URL, so this
    # test is what actually proves the complete chat-completions path.
    assert provider.endpoint_url == _EXPECTED_ENDPOINT_URL
    assert provider.endpoint_url.endswith("/v1/chat/completions"), (
        "local_200 endpoint_url must carry the complete chat-completions path; "
        "ModelSOOpenAICompatibleProviderBinding._complete_http_endpoint does not "
        "catch a bare-base regression"
    )

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
