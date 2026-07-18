"""Contract proof for the varied default browser duel."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from steel_onslaught.contracts.player_selection import (
    ModelSOModelPlayerOptionBinding,
    ModelSOPlayerRosterBinding,
)
from steel_onslaught.match.composition import load_loadout, load_match_contract_catalog
from steel_onslaught.match.runner import _require_valid_budgets

_ROOT = Path(__file__).resolve().parents[2]
_ROSTER = _ROOT / "contracts_data/rosters/live_glm_varied.yaml"


def test_live_varied_roster_binds_distinct_roles_to_seat_loadouts() -> None:
    roster = ModelSOPlayerRosterBinding.model_validate_json(
        json.dumps(yaml.safe_load(_ROSTER.read_text(encoding="utf-8")))
    )
    options = {option.option_id: option for option in roster.options}
    red, blue = roster.seats
    assert red.loadout_id == "loadout.live.glm_sniper_ironclad"
    assert blue.loadout_id == "loadout.live.glm_opportunist_hunter"
    red_model = options["player_option.glm_sniper"]
    blue_model = options["player_option.glm_opportunist"]
    assert isinstance(red_model, ModelSOModelPlayerOptionBinding)
    assert isinstance(blue_model, ModelSOModelPlayerOptionBinding)
    assert red_model.model_identity_id == blue_model.model_identity_id == "model_identity.glm"
    assert red_model.pilot_spec_id != blue_model.pilot_spec_id
    assert red_model.persona_id == "sniper"
    assert blue_model.persona_id == "opportunist"


def test_live_varied_loadouts_pass_authoritative_catalog_budgets() -> None:
    catalog = load_match_contract_catalog(_ROOT / "contracts_data")
    for filename in (
        "live_glm_sniper_ironclad.yaml",
        "live_glm_opportunist_hunter.yaml",
    ):
        loadout = load_loadout(_ROOT / "contracts_data/loadouts" / filename)
        _require_valid_budgets(loadout, catalog)
