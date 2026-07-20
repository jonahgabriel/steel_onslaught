# Foundry Terrain Slice

This slice ports the authoritative Foundry arena data from the historical
terrain revision into a new `foundry_60` strict arena contract: a 60x60 grid,
spawns at `(4,4)` and `(55,55)`, and sparse symmetric rect terrain covering
about 9% of the board. Contract tests pin the dimensions, spawn separation,
coverage band, symmetry, cluster sizes, spawn-safe pockets, and the new
100-tick sudden-death horizon.

The legacy `foundry` contract remains unchanged at 40x40 so historical
`MATCH_STARTED` snapshots and replay ledgers continue to validate. Live
overlays select `foundry_60` explicitly. The current runtime intentionally
keeps its existing wall/blocking semantics:
terrain cells remain impassable to movement and block line of sight. The map
data is therefore useful immediately without changing event or reducer APIs.

Deferred cover slice:

- allow entering terrain cells with an explicit clamber cost and speed budget;
- replace binary line-of-sight blocking with graduated cover penalties;
- carry cover-aware confidence/penalty fields through sensor and weapon events;
- expose those fields to pilot observations and the UI, with replay tests for
  the resulting ledger.

Those behaviors should land as a separate contract/versioned rules change so
this terrain data port remains compatible with existing matches and replays.
