"""Loadout pilot_id -> pilot spec resolution — tunable-pilots Task 5.

``PilotSpecRegistry`` scans ``contracts_data/pilots/*.yaml`` once and resolves
a loadout's pilot to a validated ``ModelSOPilotSpec`` per Architectural
Decision #5 (addendum §7):

1. ``loadout.pilot_spec_path`` — a player-supplied spec YAML, resolved
   relative to the loadout file's directory.  The loaded spec's ``id`` MUST
   equal ``loadout.pilot_id`` and the spec MUST name a non-null
   ``lineage.parent`` (§8: only the three shipped templates are parentless).
2. The registry, keyed by spec ``id``.
3. The MVP archetype fallback: the first archetype name appearing as a
   substring of ``pilot_id`` (fixed order: aggressive, defensive,
   predictive) resolves to that archetype's canonical template spec.  This
   reproduces the merged MVP ``match.runner._pilot_for`` mapping exactly,
   keeping the PoL loadout YAMLs and tests byte-unchanged.

``PilotResolutionError`` subclasses ``ValueError`` so callers that caught the
MVP fallback's ``ValueError`` keep working.
"""

from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]

from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.contracts.pilot import ModelSOPilotSpec

DEFAULT_PILOTS_DIR = Path(__file__).parent.parent.parent.parent / "contracts_data" / "pilots"

# Characterization order from the MVP `_pilot_for` (Task 5 step 0): substring
# checks ran aggressive -> defensive -> predictive; first match wins.
_ARCHETYPE_FALLBACK_ORDER: tuple[str, ...] = ("aggressive", "defensive", "predictive")

_TEMPLATE_ID_FORMAT = "pilot.template.{archetype}"


class PilotResolutionError(ValueError):
    """A loadout's pilot could not be resolved to a valid pilot spec."""


def load_pilot_spec(path: Path) -> ModelSOPilotSpec:
    """Load and validate one pilot spec contract YAML."""
    return ModelSOPilotSpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


class PilotSpecRegistry:
    """Index of shipped pilot specs, keyed by spec ``id``."""

    def __init__(self, specs: dict[str, ModelSOPilotSpec]) -> None:
        self._specs = dict(specs)

    @classmethod
    def load(cls, pilots_dir: Path | None = None) -> PilotSpecRegistry:
        """Scan *pilots_dir* (default: ``contracts_data/pilots/``) for spec YAMLs."""
        data_dir = pilots_dir if pilots_dir is not None else DEFAULT_PILOTS_DIR
        specs: dict[str, ModelSOPilotSpec] = {}
        for path in sorted(data_dir.glob("*.yaml")):
            spec = load_pilot_spec(path)
            if spec.id in specs:
                raise PilotResolutionError(
                    f"duplicate_spec_id: {spec.id!r} declared more than once under {data_dir}"
                )
            specs[spec.id] = spec
        return cls(specs)

    def get(self, spec_id: str) -> ModelSOPilotSpec | None:
        """Return the registered spec for *spec_id*, or None."""
        return self._specs.get(spec_id)

    def resolve(self, loadout: ModelSOLoadout, *, base_dir: Path | None = None) -> ModelSOPilotSpec:
        """Resolve *loadout*'s pilot to a spec per Architectural Decision #5.

        *base_dir* is the loadout file's directory; it is required whenever
        ``loadout.pilot_spec_path`` is a relative path (addendum §7 rule 1).
        """
        # Step 1: player-supplied spec path.
        if loadout.pilot_spec_path is not None:
            spec_path = Path(loadout.pilot_spec_path)
            if not spec_path.is_absolute():
                if base_dir is None:
                    raise PilotResolutionError(
                        f"relative pilot_spec_path {loadout.pilot_spec_path!r} requires the "
                        f"loadout's base_dir (loadout {loadout.id!r})"
                    )
                spec_path = base_dir / spec_path
            spec = load_pilot_spec(spec_path)
            if spec.id != loadout.pilot_id:
                raise PilotResolutionError(
                    f"spec_id_mismatch: spec at {spec_path} declares id {spec.id!r} but "
                    f"loadout {loadout.id!r} declares pilot_id {loadout.pilot_id!r}"
                )
            if spec.lineage.parent is None:
                raise PilotResolutionError(
                    f"player_spec_requires_parent: spec {spec.id!r} loaded via "
                    f"pilot_spec_path must name a non-null lineage.parent"
                )
            return spec

        # Step 2: registry by pilot_id.
        registered = self._specs.get(loadout.pilot_id)
        if registered is not None:
            return registered

        # Step 3: MVP archetype fallback (characterization baseline).
        for archetype in _ARCHETYPE_FALLBACK_ORDER:
            if archetype in loadout.pilot_id:
                template_id = _TEMPLATE_ID_FORMAT.format(archetype=archetype)
                template = self._specs.get(template_id)
                if template is None:
                    raise PilotResolutionError(
                        f"missing_template: archetype fallback for {loadout.pilot_id!r} "
                        f"requires {template_id!r} in the registry"
                    )
                return template
        raise PilotResolutionError(f"unknown pilot archetype in pilot_id {loadout.pilot_id!r}")
