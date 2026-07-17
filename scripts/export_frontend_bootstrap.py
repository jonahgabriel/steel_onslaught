#!/usr/bin/env python
"""Atomically generate Vite's validated public binding from an application overlay."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

from steel_onslaught.cli.serve import build_frontend_bootstrap
from steel_onslaught.contracts.application import ModelSOFrontendBootstrap
from steel_onslaught.match.composition import load_application_overlay


def export_frontend_bootstrap(overlay_path: Path, out_path: Path) -> ModelSOFrontendBootstrap:
    """Validate *overlay_path* and atomically write its public bootstrap projection."""
    bootstrap = build_frontend_bootstrap(load_application_overlay(overlay_path))
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
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    bootstrap = export_frontend_bootstrap(args.overlay, args.out)
    print(f"wrote {bootstrap.overlay_sha256} -> {args.out}")


if __name__ == "__main__":
    main()
