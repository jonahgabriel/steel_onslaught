# Steel Onslaught — Determinism Boundaries

> Companion note to `2026-04-30-steel-onslaught-design.md` (§18/§19, R9 /
> Architectural Decision #6) and `2026-06-11-learning-loop-phase2-plan.md`
> (Decision #4 — the determinism chain). This document records *what is and is
> not* reproducible across same-seed runs, so contributors do not assert the
> wrong layer.

## The contract: state-level determinism

Same `(seed, loadouts, max_ticks, geometry)` ⇒ the **canonical
`ModelSOMatchState`** reached at every tick is byte-for-byte identical, whether
produced by the live `MatchRunner` or reconstructed by the `ReplayEngine`.
This is what `reducers/scoring.py::verify_replay_validity` asserts
(`replay.reconstruct_at_tick(final) == live_state`) and what the learning-loop
determinism chain (`tests/integration/test_learn_e2e.py`) proves end-to-end.
**This is the only determinism guarantee the system makes.** It holds because:

- the fold (`match/fold.py`) is the single function from events → state, used
  identically on both paths;
- all stochastic inputs (hit rolls, sensor noise, rupture survival) flow
  through `MatchRng.for_event`, a pure function of `(seed, tick, mech_id, kind)`;
- `emitted_at` is **excluded** from state (it lives on the envelope, not on
  `ModelSOMatchState`), so its non-determinism never reaches the comparison.

## What is NOT reproducible: the `emitted_at` field

Every `ModelSOEventEnvelope` carries `emitted_at = datetime.now(UTC).isoformat()`
(set at `match/runner.py` `_make_match_event`/`_make_subject_event`,
`reducers/pilot_tick.py::_now_iso`, `reducers/failure.py`,
`match/fold.py::_on_flag_drop`). This is **wall-clock metadata**:

- It is documented in `events/envelope.py` as "metadata only, not for ordering."
- Ordering is owned by `(tick, sequence_in_tick)`, which the bus re-stamps.
- Replay validity compares `ModelSOMatchState`, **not** the raw envelope stream.

**Consequence:** the persisted ledger is *not* byte-identical across two
`run_match` calls with the same seed. The events have identical `event_type`,
`tick`, `sequence_in_tick`, `producer_node`, `subject`, and `payload`, but
differ in `event_id` (a fresh ULID each run) and `emitted_at` (wall-clock).

### Do / Don't

- **DO** assert state-level equality: `verify_replay_validity(...)`, or
  `replay.reconstruct_at_tick(t) == live_state_at_t`. This is the contract.
- **DO** assert byte-identical *stdout* from `so run`/`so replay` across same-seed
  runs (the CLI deliberately routes `match_id` to stderr so stdout is stable —
  see `tests/cli/test_main.py::test_run_same_seed_byte_identical_stdout`). The
  renderer projects state, not raw envelopes, so `emitted_at` never reaches it.
- **DO NOT** assert ledger byte-equality, or envelope-sequence equality, across
  same-seed `run_match` calls. It will fail on `event_id` and `emitted_at`.
- **DO NOT** add `emitted_at` (or any wall-clock-derived field) to
  `ModelSOMatchState` or any value folded into it. Doing so would silently
  break `verify_replay_validity`.

## Where wall-clock is allowed

Wall-clock is permitted only outside the determinism surface:

1. `emitted_at` on envelopes (metadata, excluded from state — see above).
2. The single `recorded_at` injection point for lineage records
   (`cli/learn.py`, learning-loop Decision #4), which is excluded from record
   identity (the digest is taken over the inner record *without* `recorded_at`),
   so re-runs are idempotent (first-write-wins).

Both are verified by source-scan purity tests
(`tests/learning/test_loop.py`, `tests/cli/test_learn.py`) that confine
`datetime.now` to exactly these boundary sites.
