"""Golden-chain agent dispatch report contracts (SO-REPORT-CONTRACT).

Background (the failure this module exists to close). On 2026-07-25, seven
dispatched agents completed correct underlying work and then returned bare
acknowledgements -- ``"Done."``, ``"Task complete."``,
``"No further action taken."`` -- in place of any typed result. The worst
class filled a required 4-field schema with the literal string ``"test"`` in
every field, and it VALIDATED, because the schema checked shape only (field
present, field is a string) and never checked content. Shape-only validation
and prose exhortation ("please return a real report") are both proven
insufficient by that data.

**OMN-15162 re-export.** This module originally (PR #213) defined the four
per-role report models, their verdict/role enums, and
``validate_substantive_report_text`` directly. OMN-15161 lifted that same
contract into ``omnibase_core.models.dispatch.report`` as the fleet-generic
wire type (core PR #1510, epic OMN-15154) so every OmniNode repo shares one
canonical model per shape instead of steel carrying a live duplicate
(hostile finding #6). This module is now a THIN RE-EXPORT layer over the
core port -- steel's original public names (``ModelSOImplementerReport``,
``SODispatchRole``, ``SOImplementerVerdict``, ...) are kept as aliases for
the core classes so existing call sites (``scripts/check_report_contract.py``,
``tests/scripts/test_check_report_contract.py``) do not need a mechanical
rename; there is exactly one model definition, not two.

Core made four deliberate improvements over this module's PR #213 original
that ship through the re-export:

1. Fleet-generic naming: ``ModelSO*Report`` -> ``ModelDispatchReport*``,
   ``SODispatchRole`` -> ``EnumDispatchReportRole``, ``SO*Verdict`` ->
   ``EnumDispatchReport*Verdict`` (no steel-specific "SO" prefix on a
   fleet-wide type). Steel's original names remain as aliases below.
2. Role/verdict enums are ``StrEnum`` (this module already used ``StrEnum``;
   core keeps that, so no behavior change here).
3. ``ModelDispatchReportLander.merge_sha`` is now ``GitSha | None``,
   enforced present-iff-``MERGED`` by an ``@model_validator`` -- this
   module's original required ``merge_sha: GitSha`` unconditionally, which
   either forced a fabricated SHA for a ``BLOCKED``/``ABORTED`` land (no
   merge commit exists yet) or made the field pointlessly mandatory for the
   two verdicts where no merge ever occurred. See
   ``test_check_report_contract.py``'s new lander cases for the resulting
   RED/GREEN flip, cited to core PR #1510.
4. ``DispatchReport`` is a proper ``Annotated[..., Field(discriminator=
   "role")]`` discriminated union (pydantic dispatches straight to the
   matching role's model) instead of this module's original bare ``|``
   union.

(A fifth improvement lives beside the models, not in them:
``omnibase_core.validation.validator_dispatch_report_anchors.
check_dispatch_report_content_anchors`` peels ``*_sha`` anchors to
``<sha>^{commit}`` -- rejecting a blob/tree hash that resolves but isn't
actually a commit -- and checks ``*_paths`` artifacts with ``.is_file()``,
rejecting a directory citation that merely exists. ``scripts/
check_report_contract.py`` keeps its own historical ``check_content_anchors``
implementation for now -- out of scope for this ticket, which is the model
re-export -- so this improvement is proven importable here (see the import
probe in the OMN-15162 PR body) but not yet wired into steel's CLI gate.)

This module treats the agent final report as a seam like any other seam in
this program (mirrors ``check_preregistration_timing.py`` /
``check_contamination_gate.py``): every dispatch role gets a closed, typed
contract whose required fields carry CONTENT anchors, not mere shape --

* a git SHA field (name ends ``_sha``) must resolve against a real commit --
  checked by ``scripts/check_report_contract.py`` via ``git cat-file -e`` in
  a caller-supplied ``--git-dir``, never by this module alone (a pydantic
  model has no git access);
* ``pr_number`` must be a positive integer;
* ``verdict`` is drawn from a closed, role-specific enum -- never a free
  string;
* artifact-path fields (name ends ``_paths``) must resolve to files that
  actually exist under a caller-supplied ``--repo-root`` -- again checked by
  the validator script, not this module;
* every free-text field is rejected on placeholder literals (``"test"``,
  ``"todo"``, ``"placeholder"``, ``"lorem"``, ...), on bare-acknowledgement
  literals (``"done"``, ``"task complete"``, ``"no further action taken"``,
  ...), on any report under ``_MIN_SUBSTANTIVE_LENGTH`` characters, and on
  repetitive low-content padding used to defeat the length floor without
  saying anything -- a banned literal repeated with separators past the
  minimum length (``"Done. Done. Done. Done. Done. Done. Done."``) or a
  short unit repeated with no separators at all (keyboard-mash filler like
  ``"asdfasdfasdfasdfasdfasdfasdfasdfasdfasdfasdf"``) are both rejected, not
  just the exact single-literal case.

Four dispatch roles are modeled: ``implementer`` (builds/fixes code and
opens or updates a PR), ``verifier`` (independently re-checks an
implementer's claim against live evidence), ``lander`` (merges/finalizes a
PR), and ``scout`` (investigates/discovers, no PR required). Each role's
model is closed (``extra="forbid"``) and discriminated on its own ``role``
Literal, mirroring ``contracts/commands.py``'s ``PlayerAction`` union.

Field-name-suffix convention (load-bearing for the validator script): any
field ending ``_sha`` is a git-commit content anchor; any field ending
``_paths`` is a list-of-artifact-paths content anchor. New roles/fields that
follow this convention are picked up by ``check_report_contract.py``
automatically -- no per-field wiring needed there.
"""

from __future__ import annotations

from omnibase_core.enums.enum_dispatch_report_role import (
    EnumDispatchReportRole,
)
from omnibase_core.enums.enum_dispatch_report_verdict import (
    EnumDispatchReportImplementerVerdict,
    EnumDispatchReportLanderVerdict,
    EnumDispatchReportScoutVerdict,
    EnumDispatchReportVerifierVerdict,
)
from omnibase_core.models.dispatch.report import (
    ROLE_TO_MODEL,
    DispatchReport,
    ModelDispatchReportImplementer,
    ModelDispatchReportLander,
    ModelDispatchReportScout,
    ModelDispatchReportVerifier,
)
from omnibase_core.models.dispatch.report.model_dispatch_report_types import (
    GitSha,
    PrNumber,
)
from omnibase_core.utils.util_substantive_report_text import (
    validate_substantive_report_text,
)

# --------------------------------------------------------------------------
# Public aliases -- steel's original PR #213 names, kept working.
#
# These are NAME aliases only, never duplicate class/function definitions:
# "one canonical model per shape" (feedback_one_canonical_model_per_shape)
# means the class object itself is core's, imported once above and bound to
# a second name here so `isinstance(x, ModelSOImplementerReport)` and
# `isinstance(x, ModelDispatchReportImplementer)` are the exact same check.
# --------------------------------------------------------------------------

SODispatchRole = EnumDispatchReportRole
SOImplementerVerdict = EnumDispatchReportImplementerVerdict
SOVerifierVerdict = EnumDispatchReportVerifierVerdict
SOLanderVerdict = EnumDispatchReportLanderVerdict
SOScoutVerdict = EnumDispatchReportScoutVerdict

ModelSOImplementerReport = ModelDispatchReportImplementer
ModelSOVerifierReport = ModelDispatchReportVerifier
ModelSOLanderReport = ModelDispatchReportLander
ModelSOScoutReport = ModelDispatchReportScout

# ROLE_TO_MODEL and DispatchReport are re-exported directly above (same
# object, no aliasing needed -- their names were never steel-prefixed).

__all__ = [
    "ROLE_TO_MODEL",
    "DispatchReport",
    "GitSha",
    "ModelSOImplementerReport",
    "ModelSOLanderReport",
    "ModelSOScoutReport",
    "ModelSOVerifierReport",
    "PrNumber",
    "SODispatchRole",
    "SOImplementerVerdict",
    "SOLanderVerdict",
    "SOScoutVerdict",
    "SOVerifierVerdict",
    "validate_substantive_report_text",
]
