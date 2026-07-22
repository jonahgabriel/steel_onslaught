"""The frontend bootstrap carries the operator prompt/rule workbench projections.

Mounting the browser workbench requires the pre-match effective-prompt
provenance and rule catalog to be reachable without the CLI.  These assert that
``build_frontend_bootstrap`` embeds the SAME typed projections
``so prompts show --json`` / ``so rules list --json`` emit (so a browser edit
derives the identical overlay fragment), while omitting them keeps replay-only
and older bundles byte-for-byte unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

from steel_onslaught.cli.serve import build_frontend_bootstrap
from steel_onslaught.contracts.application import ModelSOFrontendBootstrap
from steel_onslaught.match.composition import load_application_overlay
from steel_onslaught.pilots.inspection import (
    project_effective_prompts,
    project_rule_catalog,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_OVERLAY = _REPO_ROOT / "contracts_data/overlays/standard_v1_qwen.yaml"


def test_bootstrap_embeds_the_inspection_projections() -> None:
    overlay = load_application_overlay(_OVERLAY)
    provenance = project_effective_prompts(overlay)
    catalog = project_rule_catalog(overlay)

    bootstrap = build_frontend_bootstrap(
        overlay,
        prompt_provenance=provenance,
        rule_catalog=catalog,
    )

    # The browser gets exactly what the CLI --json surfaces emit, so the derived
    # overlay fragment and effective-prompt digests are identical across surfaces.
    assert bootstrap.prompt_provenance == provenance
    assert bootstrap.rule_catalog == catalog
    assert bootstrap.prompt_provenance is not None
    assert len(bootstrap.prompt_provenance.prompts) >= 1

    document = json.loads(bootstrap.model_dump_json())
    assert document["prompt_provenance"]["kind"] == "steel_onslaught.match_prompt_provenance"
    assert document["rule_catalog"]["kind"] == "steel_onslaught.card_rule_catalog"

    # A full round-trip through the closed contract preserves both projections.
    restored = ModelSOFrontendBootstrap.model_validate_json(bootstrap.model_dump_json())
    assert restored.prompt_provenance == provenance
    assert restored.rule_catalog == catalog


def test_bootstrap_omits_projections_when_not_supplied() -> None:
    overlay = load_application_overlay(_OVERLAY)
    bootstrap = build_frontend_bootstrap(overlay)

    assert bootstrap.prompt_provenance is None
    assert bootstrap.rule_catalog is None
    document = json.loads(bootstrap.model_dump_json())
    assert "prompt_provenance" not in document
    assert "rule_catalog" not in document
