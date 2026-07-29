# Display-salience arm #1 — acceptance battery (OMN-15172): artifact acceptance report — 2026-07-29

**Verdict: ACCEPT.** Both corners are complete at n=30, uncontaminated, provenance-intact, and fit to score. An
independent adversarial verifier (verifier ≠ assembler) attempted to refute the acceptance across five checks,
gathered its own evidence, and could not — verdict recorded verbatim in §8.

**Scope, stated first because it is the most misreadable thing about this document.** This is an *artifact
acceptance* report: are there exactly the expected rows, are they real matches, is the lane uncontaminated, is the
provenance intact, is the ledger fit to be scored. It is **not** the arm's analysis. It does **not** compute,
publish or narrate the pre-registered primary statistic `s = PROMINENT_total / DEFAULT_total`, the SEAT-SPLIT
clause, or the arm's verdict. Those belong to the arm's own scoring document, which is a separate deliverable and
does not exist yet. One acceptance-relevant fact about the *denominator* is flagged in §7.1, because suppressing it
would be worse than stating it.

**Artifacts.** `SNAP` = `~/.omnibase/battery_envs/omn15172-hermetic-20260727` (frozen hermetic snapshot);
`ROOT` = `$SNAP/battery_state/omn15172_acceptance_rerun2`. Both corners' `battery_raw.jsonl`, `events.sqlite3`,
`leaderboard.sqlite3`, per-invocation summaries and run logs are retained on disk under `ROOT`.

**Model:** live Qwen3.6-35B-A3B-8bit via `onex-local-coder-mlx`, both seats, per-seed isolated process invocation.
n = 30 per corner, seeds 5001–5030.

---

## 0. Verdict table

| Check | prominent | default |
|---|---|---|
| Rows in `battery_raw.jsonl` | **30** | **30** |
| Seeds present | **5001–5030 exactly**, 0 duplicates, 0 gaps, 0 out-of-range | same |
| Duplicate `match_id` collisions | 0 | 0 |
| `replay_validity == 1` on every seat | **true** (60/60 player-entries) | **true** (60/60) |
| All 4 terminal event types Kafka-forwarded, every row | **true** (30/30) | **true** (30/30) |
| Kafka topic, every row | `onex.evt.steel-onslaught.match-terminal.v1` | same |
| Draws | 0 | 0 |
| Matches truncated by the `--max-ticks 1000` failsafe | 0 | 0 |
| `check_contamination_gate.py` exit code | **1** — reconciled and discharged in §4 | **0** |
| `NEEDS_ATTENTION` sentinel | absent | absent |

**One condition attaches: §4 must travel with any citation of the prominent lane.** The contamination gate exits 1
on that lane. The reason is documented, benign, and discharged here — but a downstream consumer who runs the gate
cold and sees `exit 1` without §4 in hand will read a clean lane as contaminated.

---

## 1. Battery design

**The manipulation is one field.** `display_salience: prominent`, set in the pilot registry entries
(`contracts_data/pilots/delegation_salience/llm_delegation_{berserker,sniper}_prominent.yaml`); the `_default` pair
omits it. It changes only the free-text rendering of the per-tick OBJECTIVES/VP block — how prominently the
objective and victory-point state is displayed to the pilot — and nothing about the arena, the payout, the
loadouts, the decks, or the persona system prompts.

| | prominent corner | default corner |
|---|---|---|
| Overlay | `contracts_data/overlays/foundry_60_asym_v1_salience_prominent_delegation.yaml` | `…_salience_default_delegation.yaml` |
| Pilots | `…/llm_delegation_{berserker,sniper}_prominent.yaml` (`display_salience: prominent`) | `…_default.yaml` (field omitted) |
| Loadouts | `contracts_data/loadouts/delegation_salience/{red,blue}_prominent.yaml` | `{red,blue}_default.yaml` |
| Seats (both corners) | red = `chassis.light.scout_mk1` + berserker · blue = `chassis.heavy.ironclad_mk1` + sniper | same |
| Arena | `foundry_60_asym_v1`, `arena_contract_hash b693c2e0…`, `max_ticks 1000` | same hash |
| Seeds | 5001–5030 | 5001–5030 |

Seats are **asymmetric by design** — this is the `foundry_60_asym_v1` arena, read from `match_started.mechs`,
uniform across all 62 matches in the two ledgers.

**Why this arm exists.** It is the display-salience lever: prior arms in this program established that drafting
follows live incentive rather than narrative context (SO-OBJ-DECOY, `docs/evidence/2026-07-25-objdecoy-asym-battery.md`).
This arm holds the payout fixed and moves only its *display prominence*, testing whether salience alone moves
behaviour.

**Execution path.** Delegation-routed and bus-forwarded end-to-end: steel engine → `onex` delegation CLI →
MLX endpoint on `.200` → four terminal events per match produced onto
`onex.evt.steel-onslaught.match-terminal.v1` on `.201` stability-test redpanda, broker-acked, landing in
`omnibase_infra.public.event_ledger`. This is the arm that OMN-15172 names as leg (c) of its acceptance gate.

**Launch command (verbatim, from `chain_prominent.sh`):**

```
nohup env -u PYTHONPATH OMNI_HOME="$SNAP" uv run python scripts/run_display_salience_battery.py \
  --corner prominent --n 30 --seed-base 5000 --max-ticks 1000 --fresh \
  --state-root "$ROOT/prominent" </dev/null > "$ROOT/prominent.log" 2>&1 &
```

**The corner chaining was a disk watcher, not an agent.** `chain_prominent.sh` refuses to launch the prominent
corner unless the default corner produced a clean 30 (`if [ "$lines" = "30" ]` … else `touch NEEDS_ATTENTION`).
`chain.log`, verbatim:

```
2026-07-27T21:54:41Z chain watcher started
2026-07-28T05:34:45Z default process exited
2026-07-28T05:35:00Z default battery_raw rows=30 (30 = fully clean)
2026-07-28T05:35:00Z default CLEAN - launching prominent corner
2026-07-28T05:35:00Z prominent launched
```

**Neither ledger carries residue from the earlier abandoned attempts.** Both `events.sqlite3` files' birth times
coincide with their own first `match_started` (default 2026-07-27T20:49:16Z; prominent 2026-07-28T05:35:07Z), and
the prominent lane was launched `--fresh`. The abandoned attempts (`omn15171_display_salience_battery/`,
`omn15172_acceptance_rerun/`) are preserved elsewhere and contribute nothing here.

---

## 2. Per-corner results — recomputed from raw, independently, twice

Every figure below was recomputed by re-parsing the two `battery_raw.jsonl` files line by line — once by the
assembler and once by the adversarial verifier, working separately. **No figure comes from any
`battery_summary.json`** (see §7.2 for why that matters).

### 2.1 Outcomes

| | prominent (n=30) | default (n=30) |
|---|---|---|
| `player.red` wins | **28** | **15** |
| `player.blue` wins | **2** | **15** |
| draws | 0 | 0 |
| `terminal_class` = `elimination` | **29** | **30** |
| `terminal_class` = `vp_threshold` | **1** (seed 5006) | 0 |
| `end_reason` | `last_mech_standing` 29 / `vp_threshold` 1 | `last_mech_standing` 30 |

### 2.2 Duration (`duration_ticks`)

| | n | min | Q1 | median | mean | Q3 | max | sd |
|---|---|---|---|---|---|---|---|---|
| prominent | 30 | **79** | 96.25 | **107.5** | **126.47** | 123.75 | **300** | 56.43 |
| default | 30 | 21 | 40.25 | **59.5** | 57.27 | 69.0 | 93 | 20.98 |

Prominent, sorted: `79, 86, 87, 87, 88, 93, 94, 96, 97, 104, 106, 106, 106, 107, 107, 108, 113, 118, 119, 120, 120, 123, 124, 127, 129, 133, 165, 265, 287, 300`
Default, sorted: `21, 23, 25, 27, 28, 38, 40, 40, 41, 41, 55, 57, 58, 59, 59, 60, 61, 62, 65, 66, 66, 66, 70, 71, 79, 82, 85, 89, 91, 93`

By winner — prominent: red n=28 median 107.0 / mean 115.8; blue n=2 median 276.0. Default: red n=15 median 66 /
mean 71.7; blue n=15 median 40 / mean 42.8.

No match reached the `--max-ticks 1000` failsafe. The single 300-tick row (seed 5020) ended `last_mech_standing`,
not by clock.

### 2.3 Other per-row fields

| Field | prominent | default |
|---|---|---|
| `total_awards` (sum) | **34** — `{0: 26, 4: 1, 6: 2, 18: 1}` | **0** (all rows) |
| `vp_margin` | `{0: 27, 2: 1, 4: 1, 12: 1}` | `{0: 30}` |
| rows with any nonzero `vp_totals` | 4 (seeds 5004, 5006, 5020, 5029) | 0 |
| `replay_validity` values observed | `{1}` only | `{1}` only |
| `kafka_forwarded_event_types` | one distinct set on all 30 rows: `match_ended, match_scored, match_started, victory_declared` | same |
| `failed_completions` (sum) | **12** — `{0: 18, 1: 12}`, max 1 | **37** — `{0: 9, 1: 9, 2: 10, 3: 1, 5: 1}`, max 5 |

### 2.4 `failed_completions` is a per-tick LLM decode counter, not an award counter — correcting a live mis-read

Verified against both ledgers: for **all 60 rows in both corners**, a row's `failed_completions` equals *exactly*
the count of `llm_completion_failed` events for that `match_id` — zero mismatches. It counts per-tick decode
failures where the model returned a syntactically complete but semantically invalid pilot action, which the engine
rejected. The award counter is the adjacent field `total_awards`, which likewise equals each match's
`objective_scored` event count exactly (30/30, both corners).

**It is not a run error.** The accounting closes: `requested = resolved + failed` (prominent 8121 = 8108 + 13;
default 3473 = 3436 + 37), and all 60 matches reached a valid terminal state with `replay_validity == 1` on both
seats and all four events forwarded. Failure counts do not degrade a row.

**It is also not noise, and this correction is load-bearing:** `llm_completion_failed` rate is this arm's
pre-declared SECONDARY metric (H_SALIENCE_DISRUPTS_COMPLIANCE — "a compliance-shape regression showing up as an
increase in `llm_completion_failed` on the PROMINENT lane"). Scored-rows-only rates: prominent **12 / 7598 =
0.158 %**, default **37 / 3473 = 1.065 %** — prominent roughly **6.7× lower**, i.e. the observed direction is the
*opposite* of the disruption reading. That is the arm's finding to narrate and qualify, not this report's. It is
recorded here only because a report that had mis-defined the field would have mis-stated the arm's own safety check.

---

## 3. The 5018/5019 skip and makeup — the mandatory record

**Two seeds were skipped mid-run and re-run in a second invocation. This is the single most important disclosure in
this document and must travel with any citation of the prominent corner.**

### 3.1 What happened, in order

| # | Time (UTC) | Event |
|---|---|---|
| 1 | 2026-07-28T05:35:07Z | prominent main run starts (seed 5001) |
| 2 | 14:05:59Z → 14:39:14Z | **seed 5018** runs to completion — `match.01KYMGQVF450DZNKH3BWJEW6HC`, 124 ticks, all terminal events persisted to the ledger |
| 3 | 14:26:02Z | Kafka transport to `.201:39092` starts failing (first `REQTMOUT`) |
| 4 | 14:26:21Z – 15:01:51Z | **144 rdkafka `FAIL` lines** — `Operation timed out` / `Connection setup timed out` / `Connection refused` at 15:01:45Z. Consistent with the `.201` reboot window. |
| 5 | ~14:39:44Z | seed 5018's post-match forward flush times out → seed **SKIPPED**, no row written |
| 6 | 14:39:45Z → 15:29:11Z | **seed 5019** runs to completion — `match.01KYMJNP2R28BSH4ZDFEZD0PVB`, 137 ticks, all terminal events persisted |
| 7 | ~15:29:11Z | seed 5019's forward reports delivery failures (carrying 5018's three orphaned messages plus its own) → seed **SKIPPED**, no row written |
| 8 | 15:29:12Z | seed 5020 starts — transport already recovered; seeds 5020–5030 all complete normally |
| 9 | 2026-07-29T02:15:03Z | main run ends: 28 rows, `BATTERY FAILED: 2 seed(s) skipped, no row written (seeds: 5018, 5019)` |
| 10 | 02:17:03Z | `battery_summary.json` **copied to `battery_summary_main_run.json`** — skip record preserved, 20 s before the makeup's first event |
| 11 | 02:17:23Z → 03:20:37Z | makeup run: seeds 5018, 5019 re-run, appended to the same raw file and the same ledger |
| 12 | 03:20:38Z | runner exits clean; `battery_raw.jsonl` = 30 rows |

### 3.2 The skip records, quoted verbatim from `battery_summary_main_run.json`

```json
"skipped_seeds": [
  {
    "error": "RuntimeError: seed 5018: 3 Kafka message(s) still undelivered after 30.0s flush timeout",
    "seed": "5018"
  },
  {
    "error": "RuntimeError: seed 5019: Kafka producer reported delivery failures: ['KafkaError{code=_MSG_TIMED_OUT,...} (topic='onex.evt.steel-onslaught.match-terminal.v1' key=b'match.01KYMGQVF450DZNKH3BWJEW6HC')', ... ×3 ..., 'KafkaError{code=_MSG_TIMED_OUT,...} (key=b'match.01KYMJNP2R28BSH4ZDFEZD0PVB')']",
    "seed": "5019"
  }
]
```

Same text, unelided, in `prominent.log` at lines 74, 165 and 193–202, and the file is preserved at
`$ROOT/prominent/battery_summary_main_run.json` (sha256 `39e0598bb4393e6a3ef939661b7b67d462cb3d83869283ac699b0652ed5104cd`,
1509 B).

**Read the record precisely.** Both orphan `match_id`s appear inside **seed 5019's** record — three
`_MSG_TIMED_OUT` entries keyed `…01KYMGQVF4…` (5018's, still in the shared producer's queue when 5019 flushed) and
one keyed `…01KYMJNP2R…` (5019's own). Seed 5018's own record names a count but no `match_id`. So the orphan → seed
*pairing* is not read off the skip text alone; §4.2 gives the decisive, non-inferential source.

### 3.3 The failure was strictly post-match — the withheld matches were real, finished matches

Read directly from the prominent ledger, for both orphans: `match_started` 1, `match_ended` 1, `match_scored` 1,
`victory_declared` 1, `mech_destroyed` 1. Both terminated by elimination with `winner_player_id = player.red`.
Nothing about the match failed. The only thing that failed was the post-match forward of the four terminal events
onto the bus — *after* the match had ended and its events were durably in the ledger. Per the driver's
contamination-safety contract (a dead seed is skipped loudly, never silently, and force-fails the process exit
code), no row was written. **The rows were withheld correctly.**

### 3.4 The makeup rows are real results, not backfill

| seed | match_id | correlation_id | class | winner | ticks | `failed_completions` | `total_awards` | Kafka forwarded | replay_validity |
|---|---|---|---|---|---|---|---|---|---|
| 5018 | `match.01KYNTK3DKP9A3YBGE6KRHKQ87` | `883e209b-106d-4cdc-8f00-453b0db4edbd` | elimination | player.red | 106 | 0 | 0 | all 4 | red 1 / blue 1 |
| 5019 | `match.01KYNW63ZMJNQN8391C7N252F4` | `1e113217-f132-47d0-b1de-45d1da0038de` | elimination | player.red | 133 | 1 | 0 | all 4 | red 1 / blue 1 |

Mechanics that make this an append, not a rewrite: the driver opens `battery_raw.jsonl` with `raw_path.open("a")`
and was re-invoked against the same `--state-root` **without** `--fresh`. The rows land at file lines **29 and 30**
— file order is `5001…5017, 5020…5030, 5018, 5019` — which is itself the on-disk fingerprint of an append rather
than a regenerated file. Both makeup matches carry the `_prominent` pilots, confirming the makeup ran the correct
corner.

**No outcome-based selection.** The withheld matches' outcomes are permanently on record in the append-only ledger
(both `player.red` / elimination), and the replacements are also both `player.red` / elimination. The re-run did
not change win attribution for either seed. No match was selected, dropped or re-run on the basis of any result it
produced — the re-run set was fixed by the skip record before any makeup result existed.

### 3.5 Re-running a seed is a fresh sample, not a replay — a genuine, unclosable residual

The withheld seed-5018 match ran 124 ticks; its makeup ran **106**. Seed 5019: 137 → **133**. Same seed, same
overlay, same frozen environment, different match. The engine is seeded but the LLM pilot is not deterministic
(personas run at temperature 0.7 / 0.2 against a live MLX endpoint), so a seed fixes the arena and the initial
state, not the trajectory.

Consequences the analysis must own:

- **(a)** The two makeup rows are fresh draws, not recoveries of the specific matches that were withheld. The arm is
  30 draws from the corner's distribution — which is what the pre-registration asks for — but "seed 5018" does not
  name one canonical match.
- **(b)** Those two draws were taken ~11–13 h after the other 28, on the same frozen software but not the same
  continuous provider process. §5.2 shows provider identity was unchanged, which is the strongest available
  control, but it cannot rule out endpoint-side variation (model-server restart, KV-cache/batching state, thermal
  or load differences) across an 11-hour gap.

**This is a real residual and it is not closable from disk.** It is small — 2 of 30 rows — and it is disclosed
rather than smoothed.

---

## 4. Contamination-gate reconciliation — recorded, not suppressed

Precedent for recording rather than suppressing an orphan class: `docs/evidence/2026-07-25-objdecoy-asym-battery.md`
§0b, which states the program's practice in its own words — "SO-COMP-CA scored a lane holding 34 `match_started`
for 30 completed rows, and `scripts/check_contamination_gate.py` was merged in #207 precisely to treat those 4
orphans as retry residue."

### 4.1 The gate output, run read-only against both lanes

```
$ python3 $SNAP/steel_onslaught/scripts/check_contamination_gate.py \
    --state-root $ROOT/prominent --seed-base 5000 --n 30
battery_raw.jsonl rows:       30
Distinct seeds:               30      Duplicate seeds: 0    Missing seeds (gaps): 0
Out-of-range seeds:           0       Duplicate match_id collisions: 0
Unfiltered ledger match_started: 32
Unfiltered ledger match_ended:   32
INFO -- orphaned match_started (retry residue, no match_ended): 0
Ledger match_ended vs battery_raw match_id sets bijective: NO
  CONTAMINATION: ledger shows COMPLETED matches with no battery_raw row:
    ['match.01KYMGQVF450DZNKH3BWJEW6HC', 'match.01KYMJNP2R28BSH4ZDFEZD0PVB']
CONTAMINATION GATE FAILED: see CONTAMINATION lines above.
EXIT=1
```

The default lane is bijective — 30 `match_started` / 30 `match_ended` / 30 rows — and exits **0**.

**The delta on the prominent lane is 32 / 32 / 30:** 32 `match_started`, 32 `match_ended`, 30 raw rows.
Independently re-derived by the verifier against the same ledger opened `?immutable=1`:
`ended − raw` = exactly the two named orphans; `raw − ended` = 0; `started − ended` = 0; `ended − started` = 0.

### 4.2 The two orphans, named, and tied to the skip record

| Orphan `match_id` | Ledger `match_started.payload.seed` | Window | Ticks | Ended |
|---|---|---|---|---|
| `match.01KYMGQVF450DZNKH3BWJEW6HC` | **5018** | main run | 124 | 2026-07-28T14:39:14.407320Z |
| `match.01KYMJNP2R28BSH4ZDFEZD0PVB` | **5019** | main run | 137 | 2026-07-28T15:29:11.356977Z |

Three independent bindings, strongest first:

1. **The ledger's own `match_started` payload carries a `seed` field.** Read directly, it says `5018` and `5019`.
   Not inferred from ordering or from the log — the engine's own record. The same read confirms the makeup matches
   `01KYNTK3…` / `01KYNW63…` carry seeds 5018 / 5019.
2. **Both orphan `match_id`s appear verbatim in the preserved skip-record error text** (§3.2) — the discharging
   evidence the gate cannot see, because the gate reads only `battery_raw.jsonl` + the ledger, never the summary
   files. The 3-and-1 split of `_MSG_TIMED_OUT` entries in that text matches the two orphans' partial-forward
   counts measured independently on the broker (§6.2).
3. **Sequential position.** Ordered by first event, the orphans are matches #18 and #19 of 32, immediately after
   seed 5017's match ends (14:05:58Z) and immediately before seed 5020's starts (15:29:12Z).

### 4.3 Why the gate is wrong here — a third orphan class it does not model

`check_contamination_gate.py` models exactly two orphan classes:

- `orphaned_match_started` = `match_started − match_ended` — "retry residue", printed as **INFO**, never fails the
  gate. (Here: **0**.)
- `orphaned_match_ended` = `match_ended − match_started` — printed as **ANOMALY**, "should be structurally
  impossible". (Here: **0**.)

Its pass condition is `clean = not (ended_not_in_raw or raw_not_in_ended)`. Our two orphans are `ended_not_in_raw`:
**completed matches, deliberately withheld from `battery_raw.jsonl` because a post-match, post-persistence bus
forward failed.** That class does not exist in the gate's model, and it is the exact inverse of the residue the
gate was written for — the gate assumes a match with a `match_ended` must have produced a row, whereas the driver's
own contamination-safety contract *guarantees* it will not write a row when the forward fails. **The gate and the
driver disagree by construction. This is a false positive: a real gap in the gate, not in the lane.**

Every future battery that loses a seed to a transport blip after the match completes will reproduce it. Filed as
**OMN-15377** — the fix is a third class, *ended-but-withheld-on-post-match-forward-failure*, discharged by
cross-referencing the preserved `skipped_seeds` record, so the gate can pass on evidence rather than on a human's
say-so in a report like this one.

### 4.4 The orphans must not be cleaned up, and cannot be

The `events` table carries append-only triggers — `events_no_update` and `events_no_delete`, both
`RAISE(ABORT, 'events table is append-only')`, plus a third, `events_require_canonical_envelope`, found by the
verifier and recorded here because it strengthens the immutability claim. Deleting the orphan events is
mechanically impossible without dropping the triggers, and doing so would destroy the very evidence that
discharges the gate. **Leave them.** Apply the exclusion rule below instead.

### 4.5 Exclusion rule for anyone computing a pooled statistic from the prominent ledger

The prominent ledger holds **32** matches' events; only **30** are scored rows. Any pooled event count read
naively — e.g. `SELECT count(*) FROM events WHERE event_type = 'X'` — over-counts the scored lane by the two
withheld matches. **Restrict to the 30 `match_id`s in `battery_raw.jsonl`.** Measured over-count if the rule is not
applied:

| Metric | scored rows (30) | orphans (2) | unfiltered ledger (32) |
|---|---|---|---|
| `llm_completion_requested` | 7598 | +523 | 8121 |
| `llm_completion_failed` | 12 | +1 | 13 |
| `objective_scored` | 34 | **+0** | 34 |

The two orphans contribute **zero** `objective_scored` events, so the arm's primary-statistic numerator happens to
be unaffected. The SECONDARY metric (`llm_completion_failed` rate) **is** affected and must be filtered.

---

## 5. Split-window provenance

### 5.1 Two runner invocations, not two environments

| Window | Invocation | Wall clock (UTC) | Seeds | Rows |
|---|---|---|---|---|
| **Main run** | `--corner prominent --n 30 --seed-base 5000 --max-ticks 1000 --fresh` | 2026-07-28T05:35:07Z → 2026-07-29T02:15:03Z | 5001–5030 attempted; 5018/5019 skipped | 28 |
| **Makeup** | same driver, same `--state-root`, **no** `--fresh`, n=2 | 2026-07-29T02:17:23Z → 03:20:37Z | 5018, 5019 | 2 |

**Correction to a framing worth stating plainly:** the two makeup rows are **not** "the only matches run after the
`.201` reboot." The reboot window (rdkafka failures 14:26:02Z → 15:01:51Z) sits *inside* the main-run invocation.
Eleven main-run seeds — 5020 through 5030, from 15:29:12Z — also ran after the transport recovered, in the same
process. The true split is a **process/invocation boundary**, not pre-/post-reboot: 28 rows from one long-lived
process, 2 rows from a second process started ~2 min 20 s after the first exited. The environment was frozen and
identical across both (§6); nothing was reinstalled, rebuilt or repointed between them.

### 5.2 Delegation-provider identity across the two windows — UNCHANGED

Read from the prominent ledger's own `llm_completion_*` payloads, partitioned by window:

| Window | `provider_id` | requested | resolved | failed |
|---|---|---|---|---|
| Main run (30 matches incl. 2 orphans) | `onex-local-coder-mlx` | 7642 | 7630 | 12 |
| Makeup (2 matches) | `onex-local-coder-mlx` | 479 | 478 | 1 |

**Exactly one `provider_id` appears in each window, and it is the same one.** The default corner's ledger carries
the same single provider, so provider identity is constant across all three windows and both corners.

**Precision correction, found by the verifier and recorded rather than smoothed:** an earlier draft claimed
"exactly one `(provider_id, model)` pair appears in each window." That is imprecise — `llm_completion_requested`
payloads carry `provider_id` but **no** `model` key (`model` is null on all 8121 requested events). The single
non-null pair `(onex-local-coder-mlx, mlx-community/Qwen3.6-35B-A3B-8bit)` holds on the `resolved` and `failed`
events. Provider-identity constancy across windows is unaffected and confirmed; the claim's *scope* was overstated
and is narrowed here.

### 5.3 Configuration held constant across windows and corners

| Attestation | Value | Coverage |
|---|---|---|
| `arena_contract_hash` | `b693c2e02ef3d37d29bc0ab28c4fa9c22ec1bfa9fc0e2d13ef710dbc29f333a7` | one single value across **all 62** `match_started` (32 prominent + 30 default) |
| `max_ticks` | `1000` | all 62 |
| prompt content sha256 | `be94a141bb62ad01991a1f95cc01aa48854f1aa2d4d0ebb515bd462a20fc2a11` | all 62 |
| programming-instructions sha256 | `afb0ea8772a5a1b37ff4bfeaadaddf7641b916fd95e0c9f0382e0e7bd93675dc` | all 62 |
| persona prompt sha256 ×4 | berserker `a5cb0cec…`, card_opportunist `4fa6ad25…`, opportunist `2cdc3107…`, sniper `f91d5a34…` | all 62 |
| corner identity (`pilot_id` / `loadout_id`) | prominent `…_salience_prominent_{berserker,sniper}`; default `…_default_…` | uniform within each corner, **including both makeup matches** |
| event `schema_version` | `0.1.0` | all events, both ledgers |

The identical prompt/persona hashes across corners are **expected, not a defect**: the manipulated field lives in
the pilot registry entry and changes only the free-text rendering of the per-tick OBJECTIVES/VP block, not the
persona system prompt. The corner *is* machine-readable from the ledger, via `pilot_id`/`loadout_id`.

### 5.4 Pre-registration precedes the first match

| Event | Commit / source | Timestamp (UTC) |
|---|---|---|
| Overlay pair pre-registered (#223, OMN-15166) | `f9b11aea61e48cbddc40ddaac844c25814375127` | 2026-07-26T22:24:21Z |
| Dated amendment (#225, OMN-15239 bounded semantic retry) | `23a88d09051565270f76cade8bc7b685cd790f38` | 2026-07-27T13:58:25Z |
| First `match_started`, default corner | ledger | 2026-07-27T20:49:16.700827Z |
| First `match_started`, prominent corner | ledger | 2026-07-28T05:35:07.747716Z |

Both commits precede both corners' first match — by 6 h 51 m (amendment → default) and longer for prominent. The
ordering is checkable from two sources that cannot be back-dated together: commit timestamps on the remote, and the
ledger's own `emitted_at`. **Disclosed limitation:** `scripts/check_preregistration_timing.py` was **not** run as
part of this assembly; the ordering above is established from those two sources directly. Run the checker before
the arm's scoring document is written.

---

## 6. Pins attestation and environment fingerprint

### 6.1 Pins — recorded at battery start, re-verified after the run

`docs/tracking/ROLLING_WORK_LEDGER.md`, entry `2026-07-27T20:45Z · session fable-steel-0727`, recorded the pins
*before* the battery ran: "omnimarket@f6979df8 · infra@b1bda596 · steel@985ca70c".

Re-verified against the frozen snapshot on disk, independently by both the assembler and the verifier:

| Repo | HEAD in `$SNAP` | Subject | Matches ledger pin |
|---|---|---|---|
| `steel_onslaught` | `985ca70c6c42d64b24848e19e4d86764f8ec6260` | OMN-15250: configurable-loadout points program design doc (#227) | **yes** |
| `omnimarket` | `f6979df8a57190b82c1512802129df44da9a558d` | fix(OMN-15251): content-reachability classifier (#1921) | **yes** |
| `omnibase_infra` | `b1bda5967c04f5ab719657d109cfa88a811616ac` | fix(OMN-15263): supply DEV_REDPANDA_ADVERTISE_HOST (#2504) | **yes** |

All three working trees detached at those SHAs and **clean** (`git status --porcelain` empty), before and after the
run, and again after adversarial verification. **Zero drift.**

### 6.2 The anti-drift property, verified

The failure this snapshot exists to prevent (OMN-15240 / OMN-15265: the `omnibase_infra` venv's co-installed
`omnimarket` drifting from the canonical clone mid-run, which burned 58 dead seeds on 2026-07-27) is closed **by
construction**. `$SNAP/omnibase_infra/.venv/.../omnimarket-0.4.3.dist-info/direct_url.json` records `vcs: git`
with **both** `requested_revision` and `commit_id` set to the full 40-char SHA
`f6979df8a57190b82c1512802129df44da9a558d` — an immutable commit id, not a branch or tag, identical to the
snapshot clone's HEAD. The co-installed `omnimarket` cannot drift. Both venvs are Python **3.12.9**.

**Honest note on belt coverage this run did not have.** `scripts/run_display_salience_battery.py` at
`steel@985ca70c` contains **no** `_drift_recheck` — the mid-run drift belt (OMN-15265, steel #229) merged
2026-07-28, *after* this snapshot was frozen. Benign here, because the hazard it guards cannot arise against an
immutable commit-id pin. Recorded so nobody claims belt coverage this run did not have. The OMN-15240 pre-flight
probe **is** present and did run.

### 6.3 Bus-crossing proven on the broker, not just producer-side

The verifier read `.201` stability-test directly (read-only: `psql` SELECT, `rpk topic describe`/`group describe`).
Topic `onex.evt.steel-onslaught.match-terminal.v1`, table `omnibase_infra.public.event_ledger`:

- **376 rows** for that topic, partition 0, offsets **38–413**, 376 distinct offsets — perfectly contiguous, zero
  gaps, zero duplicates.
- Battery window offsets **170–413** = 244 rows over 62 distinct match keys = 60 published × 4, **+1** (orphan 5018
  partial) **+3** (orphan 5019 partial) — exact arithmetic closure. The 1/3 partial split independently
  corroborates the skip record from the broker side: 5018 lost 3 of its 4 forwards, 5019 lost 1 of 4.
- All 60 published `match_id`s cross-checked: **0 missing, 0 with ≠ 4 events**.
- `rpk topic describe -p`: HIGH-WATERMARK **414**, LOG-START 359; ledger max offset 413 = HW − 1 (fully consumed).
- Consumer group `stability-test.…node_ledger_projection_compute.…match-terminal.v1`: STATE **Stable**, MEMBERS 1,
  CURRENT-OFFSET 414 = LOG-END-OFFSET 414, **LAG 0**.

This closes the gap an earlier draft correctly flagged as unclosable from disk alone: `kafka_forwarded_event_types`
is producer-side delivery confirmation, and the broker-side read-back above is the independent confirmation. **The
`event_ledger` row that OMN-15172 names as terminal proof is present and reconciles exactly.**

*Correction to a prior imprecise reading, stated because it was checked and found wrong:* a session note recalled
"HW 403 at 01:49Z with ~3 matches remaining." The broker/ledger data says the last main-run match (seed 5030) sat
at offsets 402–405 written 01:43:41Z, so HW at 01:49Z was ≥ 406 and exactly **2** matches remained (makeup 5018 →
406–409, 5019 → 410–413), landing at 414. `414 − 403 = 11` is not a whole number of 4-event matches. The remembered
figure was an imprecise prior reading; the live broker data is internally exact and self-consistent.

---

## 7. Anomalies and limitations, plainly

### 7.1 The primary statistic's denominator is zero — the pre-declared escape branch applies

Not scored here, but flagged because it is an acceptance-relevant property of the artifacts: the `default` lane's
ledger contains **zero** `objective_scored` events across all 30 matches (every row's `total_awards` is 0), while
`prominent` has **34** across its 30 scored rows. The pre-registered primary statistic is
`s = PROMINENT_total / DEFAULT_total`, so `s` is **undefined** and the overlay's own pre-declared escape governs:

> "OUT-OF-INTERVAL ESCAPE (pre-declared, unclamped, for the degenerate denominator DEFAULT_total = 0 …):
> DEFAULT_total = 0 AND PROMINENT_total > 0 => SALIENCE-EMERGENT (qualitative escape, NOT folded into the 0-Inf
> ratio scale — reported with the raw PROMINENT_total and both lanes' full context)."

This states only *which pre-registered path the data lands on* — an acceptance fact. The verdict, the SEAT-SPLIT
clause, the n=30 power caveats and the narration are the arm's scoring document's job, and this report does not
attempt them.

### 7.2 The per-invocation summary file is a live footgun — do not read it

`prominent/battery_summary.json` reports `"n": 2, "requested_n": 2` — a 2-row summary of a 30-row lane. This is the
standing program shape, not a defect: `battery_raw.jsonl` is opened `"a"` (append) while the summary is written
with `summary_path.write_text(...)` (**destructive overwrite**), so a second invocation against the same
`--state-root` appends rows and *replaces* the summary. The main run's summary was preserved as
`battery_summary_main_run.json` at 02:17:03Z — **20 seconds** before the makeup's first event — giving a clean
chain of custody on the skip record.

**The hazard is downstream:** any consumer reading `battery_summary.json` instead of recomputing from
`battery_raw.jsonl` silently gets a 2-row summary of a 30-row lane, with no error. It argues for a per-invocation
summary filename rather than a fixed one. **Recompute from `battery_raw.jsonl`. Always.** Every figure in §2 was,
twice.

### 7.3 Large between-corner differences in outcomes the arm did not pre-register on

Reported as descriptives, not scored: prominent is **28–2** to red where default is **15–15**, and prominent's
median match runs **107.5** ticks against default's **59.5**. Both gaps are large. Neither win-rate nor duration is
this arm's pre-registered metric, and this report does not test them — but an arm whose *unmeasured* outcomes
diverge this sharply between corners deserves an explicit paragraph in the scoring document explaining why, rather
than a table that reports only the pre-registered statistic. The honest reading: **the two lanes are not close to
each other on any axis measured here.**

### 7.4 Read-only access left SQLite sidecars — disclosed

`events.sqlite3-shm` (32 KB) and `events.sqlite3-wal` (**0 bytes**) exist alongside both ledgers, created by
read-only opens, not by writes. Every database open by this assembly used a `file:…?mode=ro` URI (including the
`check_contamination_gate.py` run); the verifier used `?immutable=1`, which creates nothing. Evidence nothing was
mutated: both `events.sqlite3` files retain their run-end mtimes and sizes; both `-wal` files are zero length (no
frames); the append-only triggers `RAISE(ABORT)` on any attempt; and raw-file and summary sha256s are identical
before and after verification. Stated rather than omitted, because "I touched nothing" would have been false at the
directory level.

### 7.5 Smaller items

- **`omnibase_spi` version skew between the two venvs** (0.22.0 steel / 0.23.1 infra). Pre-existing shape of the
  two-venv split (steel shells out to the infra venv's `onex` CLI rather than importing it), constant across both
  corners and both windows, therefore not a between-condition confound. Recorded.
- **`check_preregistration_timing.py` was not run** — see §5.4.

---

## 8. Independent adversarial verification

An adversarial verifier (verifier ≠ battery runner ≠ report assembler) was tasked to **refute** this acceptance,
gathering its own evidence rather than reviewing the assembler's. Verdict, recorded verbatim:

> "I attempted to refute and could not. All five checks pass on evidence I gathered myself. Nothing was mutated
> anywhere (verified post-hoc)."

| # | Check | Result | What was independently established |
|---|---|---|---|
| 1 | **Artifact integrity** | PASS | 30/30 rows re-parsed as JSON; one 16-key schema per file, no drift; prominent file order `5001…5017, 5020…5030, 5018, 5019` (28 main + 2 makeup appended, at lines 29–30); seed set equality with `range(5001,5031)` on both corners; 0 duplicate seeds, 0 duplicate `match_id`s; both makeup rows complete and field-for-field consistent with §3.4; `battery_summary_main_run.json` sha256 exact match with both skip records verbatim, and its n=28/red 26/blue 2/elim 27/vp 1/fc 11 plus the makeup summary sums exactly to the 30-row recount. |
| 2 | **Contamination reconciliation** | PASS | Ledger opened `?immutable=1` (no sidecar creation; `-wal`/`-shm` mtimes byte-identical before and after). Re-derived 32 `match_started` / 32 `match_ended` / 30 raw rows; `ended − raw` = exactly the two named orphans; `raw − ended`, `started − ended`, `ended − started` all 0. Both orphans' `match_started.payload.seed` read as 5018 / 5019 carrying `_prominent` pilots; both ids appear verbatim in the preserved skip text with the exact 3+1 split. Default lane bijective 30/30/30. Confirmed the report does not hide the delta — it is in §0, §4.1 and §4.5. |
| 3 | **`.201` stability-lane `event_ledger`** | PASS | Topic derived from the artifacts first, then read live read-only. 376 rows, offsets 38–413 contiguous; battery window 170–413 = 244 rows over 62 match keys = 60×4 + 1 + 3, exact closure, with the 1/3 partial split independently corroborating the skip record; all 60 published ids present with exactly 4 events each; HW 414, ledger max 413 = HW−1; consumer group **Stable**, LAG **0**. |
| 4 | **Pins unchanged** | PASS | All three `$SNAP` HEADs identical to the battery-start pin record in the rolling ledger; all detached, all `git status --porcelain` empty before and after; co-installed `omnimarket` `direct_url.json` `commit_id` and `requested_revision` both the immutable pin matching clone HEAD; both venvs Python 3.12.9. **Zero drift.** |
| 5 | **Report-vs-raw fidelity** | PASS | Full independent recompute reproduces every figure in §2 exactly, including the full sorted duration vectors, per-winner splits, `total_awards`/`vp_margin`/`failed_completions` distributions and the nonzero-`vp_totals` seed set. Ledger-derived claims also reproduce: the §4.5 over-count table, the `requested = resolved + failed` closure, `failed_completions == llm_completion_failed` on 60/60 matches, `total_awards == objective_scored` on 60/60, the §5.2 window counts, the §5.3 single `arena_contract_hash` across all 62 `match_started`, the §5.4 pre-registration commit timestamps, and the default corner's `objective_scored = 0`. Seven individual raw rows spot-checked against the tables. |

**Two immaterial imprecisions the verifier found, both corrected in this document rather than left standing:**

1. The `(provider_id, model)` pair claim was over-scoped — `model` is null on `llm_completion_requested`. Narrowed
   in §5.2.
2. A third append-only trigger, `events_require_canonical_envelope`, exists beyond the two named. Added in §4.4; it
   strengthens the immutability claim.

Neither is a defeater and neither touches acceptance.

**Mutation check, post-hoc:** raw-file and summary sha256s identical after verification; both `events.sqlite3`
sizes and mtimes unchanged; both `-wal`/`-shm` mtimes unchanged; no new files in either artifact directory;
snapshot worktrees still clean. All `.201` access was read-only.

---

## 9. What this does and does not close on OMN-15172

OMN-15172's acceptance gate has three legs: **(a)** infra-side golden chain green (topic → dispatch →
`event_ledger` row on stability-test), **(b)** steel-side driver test green (steel code provably produced the bus
message), **(c)** the live display-salience arm #1 run end-to-end through the delegation-routed, bus-forwarded path
with an `event_ledger` row as terminal proof. Declared `proof_class: replay-proven`.

**This document is the artifact-acceptance evidence for leg (c), and it also carries the live `event_ledger`
read-back that leg (c) names as its terminal proof (§6.3).** It does not adjudicate legs (a) or (b) — those are
OMN-15169 and OMN-15170 respectively — and it does not score the arm.

**No Done-flip is claimed or authorized by this document.** `dod_verify` was run for OMN-15172 on 2026-07-29 and
returned `status: skipped` — no DoD contract exists for the ticket on `onex_change_control` `main` or `dev`, so
zero checks were verified (run `66d7a41a-7817-49ae-8ab9-cd72b4cd378b`). Under the standing rule that Done-flips
route only through `dod_verify` with durable evidence, the ticket stays where it is until a contract exists and
verifies. The blocker is recorded on the ticket.

---

## 10. Reproduction commands

```bash
SNAP="$HOME/.omnibase/battery_envs/omn15172-hermetic-20260727"
ROOT="$SNAP/battery_state/omn15172_acceptance_rerun2"

# §2 row counts + hashes
wc -l "$ROOT"/{prominent,default}/battery_raw.jsonl
shasum -a 256 "$ROOT"/{prominent,default}/battery_raw.jsonl \
               "$ROOT"/prominent/battery_summary{,_main_run}.json

# §4 contamination gate (read-only; expect exit 1 on prominent, 0 on default)
python3 "$SNAP/steel_onslaught/scripts/check_contamination_gate.py" \
  --state-root "$ROOT/prominent" --seed-base 5000 --n 30
python3 "$SNAP/steel_onslaught/scripts/check_contamination_gate.py" \
  --state-root "$ROOT/default"   --seed-base 5000 --n 30

# §4.2 orphan -> seed binding, straight from the ledger (non-inferential)
python3 - <<'PY'
import sqlite3, json, os
ROOT=os.path.expanduser("~/.omnibase/battery_envs/omn15172-hermetic-20260727/battery_state/omn15172_acceptance_rerun2")
con=sqlite3.connect(f"file:{ROOT}/prominent/events.sqlite3?immutable=1", uri=True)
raw={json.loads(l)["match_id"] for l in open(f"{ROOT}/prominent/battery_raw.jsonl")}
for mid,pj in con.execute("select match_id,payload_json from events where event_type='match_started'"):
    if mid not in raw:
        print("ORPHAN", mid, "seed:", json.loads(pj)["seed"])
PY

# §6 pins
for r in steel_onslaught omnimarket omnibase_infra; do
  git -C "$SNAP/$r" log -1 --format="$r %H %cI %s"; git -C "$SNAP/$r" status --porcelain
done
cat "$SNAP/omnibase_infra/.venv/lib/python3.12/site-packages/omnimarket-0.4.3.dist-info/direct_url.json"

# §6.3 broker + ledger read-back (read-only)
ssh omni-201-ts "rpk topic describe -p onex.evt.steel-onslaught.match-terminal.v1"
```

---

## Citations

- Artifacts: `$ROOT/{prominent,default}/{battery_raw.jsonl,events.sqlite3,leaderboard.sqlite3}`,
  `$ROOT/prominent/battery_summary_main_run.json`, `$ROOT/{prominent,prominent_makeup,default,chain}.log`
- Pre-registration: PR #223 (`f9b11aea`, OMN-15166), amendment PR #225 (`23a88d09`, OMN-15239)
- Precedent for orphan disclosure: `docs/evidence/2026-07-25-objdecoy-asym-battery.md` §0b
- Gate defect filed: OMN-15377
- Snapshot rationale: OMN-15240, OMN-15265; drift auto-repair OMN-15242
- Pin record: `omni_home/docs/tracking/ROLLING_WORK_LEDGER.md`, entry 2026-07-27T20:45Z

*Every figure in this document is traceable to a named file, a named ledger query, or a quoted log line. No claim
rests on an agent self-report.*
