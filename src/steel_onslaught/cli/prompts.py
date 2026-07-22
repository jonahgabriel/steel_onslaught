"""``so prompts`` and ``so rules`` — operator surfaces for the two experiment
knobs that do not require editing code: the mech's system prompt and the
plug-in rule handlers.

``so prompts show``   renders the effective (post-override) system prompt for
                      each persona an overlay binds, plus its digest, so an
                      operator can read exactly what a match would fly with.
``so prompts set``    writes a NEW overlay whose ``llm.persona_overrides``
                      replaces one persona's doctrine from a text file — the
                      human-editable path.  The edited prompt is recorded in
                      MATCH_STARTED provenance by composition, so an edit can
                      never escape the ledger.
``so rules list``     enumerates every installed rule handler with its human
                      description and marks which the overlay enables.
``so rules set``      writes a NEW overlay whose ``contracts.balance_rule_pack``
                      selects an explicit, order-significant handler list,
                      failing closed on an unknown handler id.

Every ``set`` command emits a new overlay file rather than mutating the input:
the launch path stays declarative (composition reads the overlay), and the
operator keeps a durable record of the experiment they ran.
"""

from __future__ import annotations

import json
from pathlib import Path

import click
import yaml  # type: ignore[import-untyped]

from steel_onslaught.cards.rules import default_rule_registry
from steel_onslaught.contracts.application import (
    ModelSOApplicationOverlay,
    ModelSOBalanceRulePackBinding,
)
from steel_onslaught.match.composition import load_application_overlay
from steel_onslaught.pilots.inspection import (
    project_effective_prompts,
    project_rule_catalog,
)
from steel_onslaught.pilots.persona_prompts import ModelSOPersonaPromptOverride

_OVERLAY_IN = click.Path(exists=True, dir_okay=False, path_type=Path)
_OVERLAY_OUT = click.Path(dir_okay=False, path_type=Path)


def _write_overlay(overlay: ModelSOApplicationOverlay, out_path: Path) -> None:
    """Serialize a validated overlay model with portable absolute paths.

    ``load_application_overlay`` resolves every filesystem root to an absolute
    path relative to the source overlay, so dumping the resolved model yields
    an overlay that loads correctly from any output directory — an edited
    overlay written elsewhere never breaks its persona/card/ledger roots.
    """

    document = overlay.model_dump(mode="json")
    out_path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


@click.group(name="prompts")
def prompts_command() -> None:
    """Read and edit the human-editable mech system prompts."""


@prompts_command.command(name="show")
@click.option("--overlay", "overlay_path", type=_OVERLAY_IN, required=True)
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit the typed projection.")
@click.option(
    "--full",
    is_flag=True,
    default=False,
    help="Print the entire effective prompt text, not a preview.",
)
def prompts_show(overlay_path: Path, as_json: bool, full: bool) -> None:
    """Show the effective system prompt for every persona this overlay binds."""

    overlay = load_application_overlay(overlay_path)
    provenance = project_effective_prompts(overlay)
    if as_json:
        click.echo(json.dumps(provenance.model_dump(mode="json"), indent=2, sort_keys=True))
        return
    if not provenance.prompts:
        click.echo("no personas bound by this overlay")
        return
    for prompt in provenance.prompts:
        marker = "EDITED" if prompt.source == "operator_override" else "contract"
        click.echo(f"=== {prompt.persona_id} ({prompt.display_name}) [{marker}] ===")
        click.echo(f"temperature: {prompt.temperature}")
        click.echo(f"sha256:      {prompt.prompt_sha256}")
        # The inspection projection always carries text; guard defensively so a
        # redacted (ledger) provenance would degrade to hash-only, not crash.
        text = prompt.prompt_text
        if text is None:
            click.echo("prompt:      (redacted; hash only)")
        elif full:
            click.echo(text)
        else:
            preview = " ".join(line.strip() for line in text.strip().splitlines())[:240]
            click.echo(f"preview:     {preview}...")
        click.echo("")


@prompts_command.command(name="set")
@click.option("--overlay", "overlay_path", type=_OVERLAY_IN, required=True)
@click.option("--persona", "persona_id", required=True, help="Persona id to override.")
@click.option(
    "--doctrine-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Text file whose contents become the new persona doctrine.",
)
@click.option("--temperature", type=click.FloatRange(0.0, 2.0), default=None)
@click.option("--out", "out_path", type=_OVERLAY_OUT, required=True)
def prompts_set(
    overlay_path: Path,
    persona_id: str,
    doctrine_file: Path,
    temperature: float | None,
    out_path: Path,
) -> None:
    """Write a new overlay overriding one persona's editable doctrine."""

    overlay = load_application_overlay(overlay_path)
    known = {prompt.persona_id for prompt in project_effective_prompts(overlay).prompts}
    if persona_id not in known:
        raise click.ClickException(
            f"persona {persona_id!r} is not bound by this overlay; known: {sorted(known)}"
        )
    doctrine = doctrine_file.read_text(encoding="utf-8").strip()
    # Validate the edit through the closed contract before touching the file.
    override = ModelSOPersonaPromptOverride(
        persona_id=persona_id, doctrine=doctrine, temperature=temperature
    )
    # Replace any prior override for this persona; keep the rest in order.
    overrides = (
        *(
            existing
            for existing in overlay.llm.persona_overrides
            if existing.persona_id != persona_id
        ),
        override,
    )
    edited = overlay.model_copy(
        update={"llm": overlay.llm.model_copy(update={"persona_overrides": overrides})}
    )
    _write_overlay(edited, out_path)
    click.echo(f"wrote {out_path} with edited doctrine for {persona_id}", err=True)


@click.group(name="rules")
def rules_command() -> None:
    """Discover and select the plug-in card-programming rule handlers."""


@rules_command.command(name="list")
@click.option(
    "--overlay",
    "overlay_path",
    type=_OVERLAY_IN,
    default=None,
    help="Optional overlay; when given, marks which handlers it enables.",
)
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit the typed catalog.")
def rules_list(overlay_path: Path | None, as_json: bool) -> None:
    """List every installed rule handler and the overlay's enabled selection."""

    if overlay_path is None:
        catalog = default_rule_registry().catalog(())
    else:
        catalog = project_rule_catalog(load_application_overlay(overlay_path))
    if as_json:
        click.echo(json.dumps(catalog.model_dump(mode="json"), indent=2, sort_keys=True))
        return
    enabled = set(catalog.enabled_handler_ids)
    click.echo(f"pack: {catalog.pack_id}")
    for descriptor in catalog.available:
        mark = "[x]" if descriptor.handler_id in enabled else "[ ]"
        click.echo(f"{mark} {descriptor.handler_id}  ({descriptor.display_name})")
        click.echo(f"      {descriptor.description}")
    if catalog.enabled_handler_ids:
        click.echo(f"enabled order: {', '.join(catalog.enabled_handler_ids)}")
    else:
        click.echo("enabled order: (none)")


@rules_command.command(name="set")
@click.option("--overlay", "overlay_path", type=_OVERLAY_IN, required=True)
@click.option(
    "--handler",
    "handler_ids",
    multiple=True,
    required=True,
    help="Handler id to enable; repeat for an ordered selection.",
)
@click.option("--out", "out_path", type=_OVERLAY_OUT, required=True)
def rules_set(overlay_path: Path, handler_ids: tuple[str, ...], out_path: Path) -> None:
    """Write a new overlay enabling an explicit, ordered rule selection."""

    registry = default_rule_registry()
    # Fail closed here, before writing, on any unknown or duplicate id.
    try:
        registry.select(handler_ids)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    overlay = load_application_overlay(overlay_path)
    if (
        overlay.contracts.card_catalog is None
        or not overlay.contracts.card_catalog.card_mode_enabled
    ):
        raise click.ClickException(
            "balance_rule_pack requires an overlay with an enabled card catalog"
        )
    binding = ModelSOBalanceRulePackBinding(
        kind="card_programming_rules",
        pack_id=registry.pack_id,
        handler_ids=handler_ids,
    )
    edited = overlay.model_copy(
        update={"contracts": overlay.contracts.model_copy(update={"balance_rule_pack": binding})}
    )
    _write_overlay(edited, out_path)
    click.echo(f"wrote {out_path} enabling {', '.join(handler_ids)}", err=True)


__all__ = ["prompts_command", "rules_command"]
