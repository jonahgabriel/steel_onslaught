#!/usr/bin/env python
"""Atomically generate Vite's validated public binding from an application overlay."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from steel_onslaught.cli.serve import build_frontend_bootstrap
from steel_onslaught.contracts.application import ModelSOFrontendBootstrap
from steel_onslaught.contracts.model_catalog import ModelSOModelCatalog
from steel_onslaught.contracts.player_selection import (
    ModelSOPlayerRosterBinding,
    validate_player_roster_against_overlay,
)
from steel_onslaught.match.composition import (
    load_application_overlay,
    load_model_catalog,
    load_pilot_registry,
)


def export_frontend_bootstrap(
    overlay_path: Path,
    out_path: Path,
    *,
    roster_path: Path | None = None,
    catalog_path: Path | None = None,
    catalog_index_path: Path | None = None,
) -> ModelSOFrontendBootstrap:
    """Atomically export safe overlay and optional explicit roster authority.

    Omitting both selection inputs emits an explicit null roster.  The
    exporter never discovers providers or player options from ambient
    configuration.
    """

    overlay = load_application_overlay(overlay_path)
    if catalog_path is not None and catalog_index_path is not None:
        raise ValueError("catalog_path and catalog_index_path are mutually exclusive")
    catalog = None
    if catalog_index_path is not None:
        catalog = load_model_catalog(catalog_index_path)
    elif catalog_path is not None:
        catalog = ModelSOModelCatalog.model_validate_json(
            json.dumps(yaml.safe_load(catalog_path.read_text(encoding="utf-8")))
        )
    bootstrap = build_frontend_bootstrap(overlay, model_catalog=catalog)
    if roster_path is not None:
        roster = ModelSOPlayerRosterBinding.model_validate_json(
            json.dumps(yaml.safe_load(roster_path.read_text(encoding="utf-8")))
        )
        validate_player_roster_against_overlay(
            roster=roster,
            overlay=overlay,
            pilot_registry=load_pilot_registry(overlay.contracts.pilot_registry_dir),
        )
        bootstrap = build_frontend_bootstrap(
            overlay,
            roster=roster,
            model_catalog=catalog,
        )
    document = f"{bootstrap.model_dump_json()}\n"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=out_path.parent,
        prefix=f".{out_path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(document)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, out_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return bootstrap


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overlay", required=True, type=Path)
    parser.add_argument(
        "--roster",
        type=Path,
        help="explicit validated player-roster authority; omission exports null",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        help="explicit validated multi-provider model catalog; omission exports no catalog",
    )
    parser.add_argument(
        "--catalog-index",
        type=Path,
        help="explicit catalog source index that merges configured overlays and rosters",
    )
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    bootstrap = export_frontend_bootstrap(
        args.overlay,
        args.out,
        roster_path=args.roster,
        catalog_path=args.catalog,
        catalog_index_path=args.catalog_index,
    )
    print(f"wrote {bootstrap.overlay_sha256} -> {args.out}")


if __name__ == "__main__":
    main()
