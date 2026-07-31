# OMN-15488 L-GATE-2 decisive learning-effect battery — acceptance gates — 2026-07-31

**Verdict: ACCEPT. All four acceptance criteria (AC1, AC2, AC3, AC6) PASS.** Gates were run read-only by an
independent gates agent (agent ≠ the scoring assembler ≠ the scoring recompute verifier — see §5) against the
completed `_r2` state-root. This document is the artifact-acceptance evidence only: contamination/bijection,
provenance/lineage, timing, and receipt accounting. It does **not** compute or narrate the pre-registered primary
or vent statistics — that is `docs/evidence/2026-07-31-lgate2-decisive-battery-scoring.md`, a separate deliverable.

**Artifacts.** `SNAP` = `~/.omnibase/battery_envs/omn15488-hermetic-20260730`; `ROOT` =
`$SNAP/battery_state/omn15488_learning_battery_r2` (the executing, non-abandoned state-root). Steel pinned at
`a3b0d8aa7f7392942f6d78c47bf7f98247c63d09` (#240, OMN-15566). 61 rows: 30 baseline seeds 4001–4030, 1 promote seed
4101, 30 post seeds 4201–4230.

---

## 0. Verdict table

| AC | Check | Result |
|---|---|---|
| AC1 | Pre-registration precedes first scored match | **PASS** — margin +10m 43s |
| AC2 | Contamination-clean / bijective / zero casualties | **PASS** — 61/61 bijective, zero orphans |
| AC3 | Audit chain: provenance → promotion → lineage → post generation, byte-equal | **PASS** — 0 mismatches across 60 checked rows |
| AC6 | Delegation-node receipts: provider literals + accounting closure | **PASS** — requested = resolved + failed at every granularity |

---

## 1. AC1 — pre-registration timing

Ran verbatim, against the executing state-root:

```
$ uv run python scripts/check_preregistration_timing.py \
    --state-root $ROOT \
    --overlay contracts_data/overlays/tactical_split_overdeal_v1_delegation_learning.yaml
Pre-registration commit:    a3b0d8aa7f7392942f6d78c47bf7f98247c63d09
  author timestamp:         2026-07-31T03:39:43-04:00   (load-bearing)
First match_started:        2026-07-31T07:50:26.322742+00:00
Gap (match_started - author date): 0:10:43.322742
OK: pre-registration commit's author timestamp precedes the first match_started.
EXIT=0
```

**The margin is thin — 10m 43s** — because `a3b0d8a` is Amendment 3 (per-seed containment, the fix that let the
`_r2` run complete at all), landed the same morning as the run.

**Cross-checked independently against the full commit ancestry, not just the script's single-commit output.**
`git log --format='%H %aI %s' -- contracts_data/overlays/tactical_split_overdeal_v1_delegation_learning.yaml` shows
exactly three commits touching this overlay, all with author timestamps preceding the first `match_started`
(2026-07-31T07:50:26Z):

| Commit | Author timestamp | Content |
|---|---|---|
| `ff5df34` | 2026-07-30T14:56:39-04:00 | original pre-registration (already carried Amendment 1: client contract-selection fix) — #235 |
| `4bae73e` | 2026-07-30T15:59:14-04:00 | Amendment 2 — send programming response contract on delegation wire — #239 |
| `a3b0d8a` | 2026-07-31T03:39:43-04:00 | Amendment 3 — semantic-retry parity + per-seed battery containment — #240 |

The script's own design (checks the LATEST touch only, per its docstring) is correct here: `a3b0d8a` is genuinely
the most recent commit AND all three are chronologically ordered before the first match. `git rev-parse HEAD` on
the executing steel_onslaught snapshot equals `a3b0d8aa7f7392942f6d78c47bf7f98247c63d09`, matching the stated pin
exactly; working tree clean (`git status --short` empty). Independently queried `$ROOT/events.sqlite3`
(`?mode=ro&immutable=1`) and confirmed `MIN(emitted_at)` over `match_started` = `2026-07-31T07:50:26.322742+00:00`
with 61 distinct `match_started` `match_id`s — matching the script's number exactly.

---

## 2. AC2 — contamination / bijection / casualty accounting

`check_contamination_gate.py`'s interface genuinely cannot express this lane, confirmed both empirically and by
reading its source: `load_battery_rows` reads the entire unfiltered `battery_raw.jsonl` and `check_seed_coverage`
compares ALL actual seeds against a single expected block. Any single-block invocation (`--n 30 --seed-base 4000`,
`--n 1 --seed-base 4100`, `--n 30 --seed-base 4200`) reports every row from the OTHER two blocks as "Out-of-range
seeds" and exits 1 — **a fail-closed interface limitation, not real contamination.** This is stated plainly rather
than silently worked around or force-fit: in every one of the three per-block runs, the script's own genuine
indicators are clean — `Duplicate seeds: 0`, `Missing seeds (gaps): 0`, `Duplicate match_id collisions: 0`,
`Ledger match_ended vs battery_raw match_id sets bijective: yes`, `orphaned match_started (retry residue): 0`.

**Re-derived directly** (the script's exact logic, generalized to a 3-block union expected-seed set, via a
disposable re-derivation script — no repo file mutated): `battery_raw.jsonl` holds exactly 61 rows — 30 baseline
seeds {4001..4030} exact/no-dupes, 1 promote seed {4101} (within the pre-registered 15-attempt budget window
4101–4115, promoted on the first attempt), 30 post seeds {4201..4230} exact/no-dupes; 0 duplicate seeds anywhere, 0
duplicate `match_id`s, 0 seeds outside the declared union.

**Ledger bijection.** `match_started` = 61, `match_ended` = 61, `battery_raw` rows = 61 — all three sets are the
SAME 61 `match_id`s (`started − ended = ∅`, `ended − started = ∅`, `ended_not_in_raw = ∅`, `raw_not_in_ended = ∅`)
— fully bijective with **zero orphans of any class**. `battery_summary.json` independently confirms
`skipped_seeds: []` in baseline/promote/post/top-level — **zero casualties, zero makeup runs in `_r2`**, so the
OMN-15377 ended-but-withheld reconciliation class has nothing to discharge here. `replay_validity == 1` for both
`player.red` and `player.blue` on all 61/61 rows (0 exceptions). Phase counts from `battery_raw`: baseline=30,
promote=1, post=30 — 30/30 achieved in both measured phases; 0 rows excluded for zero-total-planned-cards or
zero-dealt-vent (both endpoints fully defined for every baseline/post row).

**The stale `NEEDS_ATTENTION` sentinel — disposed, not this lane's.** `battery_state/logs/NEEDS_ATTENTION` (0
bytes, mtime Jul 30 17:39 local) lives in the SHARED `battery_state/logs/` directory, not inside
`omn15488_learning_battery_r2/`. `runner.log` shows two distinct launches: the abandoned attempt (state-root
`.../omn15488_learning_battery`, launched 2026-07-30T20:29:32Z — matches Amendment 3 §1's account of a crash at
baseline seed 4028) and `_r2` itself (state-root `.../omn15488_learning_battery_r2`, launched
2026-07-31T07:50:25Z, ~7h later). The sentinel's mtime falls in that gap — it is the abandoned attempt's residue.
`_r2` produced its OWN clean-completion sentinel, `battery_state/logs/BATTERY_DONE` (mtime Jul 31 06:03–06:05
local), confirming this lane completed cleanly and the `NEEDS_ATTENTION` marker is not `_r2`'s.

### 2.1 The abandoned first attempt — disposed, contributes nothing

The originally-launched run (state-root `omn15488_learning_battery`, no `_r2` suffix) crashed at baseline seed 4028
after 27 clean rows: one completion returned syntactically malformed JSON on all 3 delegation-node internal
retries (`quality_gates_failed "MALFORMED: response is not valid JSON"`, correlation `738867fd`), the client raised
it as a TRANSPORT error, and the driver — which at that point had no per-seed containment — died with the match.
Independently confirmed here: `wc -l` on that state-root's `battery_raw.jsonl` returns **27**, seeds 4001–4027, no
seed 4028 or beyond. That lane is preserved untouched and **zero rows from it are read by this document or by the
scoring document.** Per Amendment 3, this disposal is on-record verbatim in the pre-registration overlay itself,
not reconstructed after the fact.

---

## 3. AC3 — audit chain: provenance → promotion → lineage → post generation

Re-derived entirely from raw ledger/file artifacts, not the driver's `battery_summary.json` assertions.

All 30 baseline rows: `policy_provenance.generation == 0` and `source_lineage_digest == null` — 0 exceptions,
checked programmatically against every row.

**Promotion event.** Ledger `policy_promoted` event count = exactly 1 (from the full event-type distribution query
over 46,052 total lane events), on `match_id` `match.01KYVV5F4C19QVPBQE61GZ3YGN`, `emitted_at`
2026-07-31T10:29:13.523794+00:00. Its ledger payload is **byte-identical** to the `policy_promoted` field embedded
in `battery_raw.jsonl`'s single promote-phase row (same `match_id`, seed 4101): `generation=1`,
`policy_id="policy.aggressive.31d9f8ceb1e3a5b6"`, `spec_hash="31d9f8ceb1e3a5b626efdf17442b3632896ad06721a5a08aca532b2ee8a5da97"`,
`parent_spec_hash="0b6bd757141e60df46e63aad6d1c64255b18b800c3a8985bba2b36fd20cee364"` (= the baseline generation's
spec_hash), `source_lineage_digest="39e46ac3617c5794790f91d68dab53796de10c06be57ce746f377179191e9891"`.

**All 30 post rows:** `policy_provenance.generation == 1` and `policy_id`/`spec_hash`/`source_lineage_digest`
byte-equal to the promotion payload above — 0 mismatches across all 30 rows and all 4 fields checked.

**Lineage record on disk.** The derived-path lineage file exists at
`battery_state/omn15488_learning_battery_r2/lineage/aggressive/31d9f8ceb1e3a5b626efdf17442b3632896ad06721a5a08aca532b2ee8a5da97/39e46ac3617c5794790f91d68dab53796de10c06be57ce746f377179191e9891.yaml`.
Content: `promotion.status: promoted`, `spec_hash` matches, `parent_hash: 0b6bd757...` (matches baseline's genesis
spec_hash), `generator.selection_reason: "live win by player.red with damage differential +15 in match
match.01KYVV5F4C19QVPBQE61GZ3YGN"`.

**Genesis/step arithmetic.** The lineage record's `parameters.aggression: 2.5` matches
`battery_summary.json`'s `genesis: 0.5` + `step: 2.0` = **2.5** exactly — both the driver's declared arithmetic and
the materialized lineage record agree.

---

## 4. AC6 — delegation-node receipts and provider accounting

**Provider literals.** Distinct `provider_id` values across all `llm_completion_requested` / `llm_completion_resolved`
/ `llm_completion_failed` payloads (queried directly from the ledger, not asserted) = exactly `{qwen35,
qwen35_mirror_blue}` in every one of the three event types — a subset of (in fact equal to) the amended AC6 set,
consistent with the overlay header's Amendment note 3 ("the lane ledger's `llm_completion_*` payloads carry the
PILOT SPECS' `provider_id` strings — `qwen35` and `qwen35_mirror_blue`").

**Accounting closure.** `requested = resolved + failed`, exact, at every granularity checked:

| Granularity | requested | resolved | failed |
|---|---:|---:|---:|
| lane-wide | 1499 | 1488 | 11 |
| qwen35 | 750 | 744 | 6 |
| qwen35_mirror_blue | 749 | 744 | 5 |
| baseline | 750 | 746 | 4 |
| promote | 30 | 30 | 0 |
| post | 719 | 712 | 7 |

No leaked or orphaned completions at any granularity.

**Delegation-node receipts, spot-verified against the provider's own state** (not the battery_state lane dir — the
provider's `state_root` config key is fixed in the overlay, independent of the driver's `--state-root` override):
`steel_onslaught/.onex_state/steel_onslaught/tactical_split_overdeal_v1_delegation_learning/delegation_state/{qwen35,qwen35_mirror_blue}/`
each contain populated `captures/` (1147 `node_delegate_skill_orchestrator-*.log` files each), `artifacts/`
(4588 for qwen35), `emit_spool/`, `tmp/`, and a live `workflow_result.json` (mtime Jul 31 06:03, i.e. end of the
`_r2` run). Capture-log mtimes span 2026-07-30T19:06:43Z .. 2026-07-31T13:03:18Z (cumulative across canary attempts
+ the abandoned attempt + `_r2`, since this directory is not lane-scoped), which fully covers the `_r2` battery's
own `match_started` window (2026-07-31T07:50:26Z .. 12:58:04Z) with plausible post-match completion latency.

**Targeted spot-check on the single highest-stakes row** — the promote match, ledger window 10:22:52Z–10:29:13Z:
18 `qwen35` capture logs and 17 `qwen35_mirror_blue` capture logs land inside that exact ~6.4-minute window —
concrete proof delegation-node receipts exist for a specific battery-window completion, not just directory
presence.

---

## 5. Verifier independence

Three separate agents, no self-verification anywhere in this chain:

1. **Gates agent** (this document's evidence) — read-only against the completed `_r2` state-root; ran AC1's script
   verbatim, hand-verified AC2/AC3/AC6 against raw ledger + file artifacts.
2. **Scoring assembler** — computed the pre-registered primary and confirmatory-secondary statistics from
   `battery_raw.jsonl`, independently of the gates agent's work (`docs/evidence/2026-07-31-lgate2-decisive-battery-scoring.md`).
3. **Scoring recompute verifier** — did not review the assembler's draft; independently re-parsed
   `battery_raw.jsonl` and re-implemented the Welch/Welch–Satterthwaite statistics from scratch, then diffed its own
   figures against the draft's. Verdict and findings recorded in the scoring document; two blocking findings (a
   phantom `battery_summary.json` corroboration claim, and a mislabeled one-sided/two-sided comparison column) and
   two minor findings (an Amendment-1 provenance miscite, a self-contradictory sentence) were raised against the
   first draft and remediated before this evidence pair was landed — see the scoring document's own text, which
   carries the corrected versions, not the original defects.

No agent in this chain authored or verified its own claim.

---

## 6. Reproduction commands

```bash
SNAP="$HOME/.omnibase/battery_envs/omn15488-hermetic-20260730"
ROOT="$SNAP/battery_state/omn15488_learning_battery_r2"

# AC1 — pre-registration timing gate
cd "$SNAP/steel_onslaught"
python3 scripts/check_preregistration_timing.py \
  --state-root "$ROOT" \
  --overlay contracts_data/overlays/tactical_split_overdeal_v1_delegation_learning.yaml

# AC2 — per-block contamination checks (each individually fails closed by design; see §2)
python3 scripts/check_contamination_gate.py --state-root "$ROOT" --n 30 --seed-base 4000
python3 scripts/check_contamination_gate.py --state-root "$ROOT" --n 1  --seed-base 4100
python3 scripts/check_contamination_gate.py --state-root "$ROOT" --n 30 --seed-base 4200

# AC2 — abandoned first attempt row count (disposed, not scored)
wc -l "$SNAP/battery_state/omn15488_learning_battery/battery_raw.jsonl"

# AC3 — direct ledger query for the single policy_promoted event
python3 - <<'PY'
import sqlite3, json, os
ROOT = os.path.expanduser("~/.omnibase/battery_envs/omn15488-hermetic-20260730/battery_state/omn15488_learning_battery_r2")
con = sqlite3.connect(f"file:{ROOT}/events.sqlite3?mode=ro&immutable=1", uri=True)
for row in con.execute("select event_type, count(*) from events group by event_type having event_type='policy_promoted'"):
    print(row)
PY

# AC6 — provider_id accounting closure
python3 - <<'PY'
import sqlite3, json, os
from collections import Counter
ROOT = os.path.expanduser("~/.omnibase/battery_envs/omn15488-hermetic-20260730/battery_state/omn15488_learning_battery_r2")
con = sqlite3.connect(f"file:{ROOT}/events.sqlite3?mode=ro&immutable=1", uri=True)
for et in ("llm_completion_requested", "llm_completion_resolved", "llm_completion_failed"):
    c = Counter()
    for (pj,) in con.execute("select payload_json from events where event_type=?", (et,)):
        c[json.loads(pj)["provider_id"]] += 1
    print(et, dict(c))
PY
```

---

## 7. Fix history — three landed defects between the pre-registration and the clean run

**Five canary/launch attempts ran against this overlay before the clean `_r2` run; the first four each failed on a
distinct root-caused class, and each fix landed before the next attempt was launched.**

1. **Composition-level failure** (pre-`ff5df34`): the overlay's `secret_resolver.kind: none` (copied from the
   display-salience delegation overlays' convention) unconditionally rejected the driver's injected
   `NoSecretResolver()` — `ValueError: llm.secret_resolver kind 'none' rejects an injected resolver` — aborting
   before any LLM call. Fixed to `kind: injected`.
2. **Schema-violation canary failure** (2/2 seeds, 4/4 completion attempts): the served model returned a
   registers-shaped whole-round program instead of the required per-tick tactical decision shape. Root-caused (not
   at the time of this failure, but before Amendment 1 landed) as a contract mis-selection defect:
   `LlmBusDelegationClient` hardcoded `_TACTICAL_RESPONSE_CONTRACT` on every request regardless of call site. Fixed
   by caller-selected response contracts — Amendment 1, baked into the pre-registration commit **`ff5df34` (#235,
   OMN-15488, "remediation round 3")**.
3. **Third canary attempt** (2026-07-30T19:06Z, pinned at `ff5df34`/#235): failed closed, initially masked by a
   diagnostic-dropping defect in the delegation CLI runner (stdout — where the receipt diagnostic lands — was
   dropped on nonzero exit). Once unmasked, the real cause was the platform delegation node's DEFAULT schema set
   rejecting the correctly-shaped registers program because the caller supplied no contract for programming
   completions. Fixed by sending an explicit `_PROGRAMMING_RESPONSE_CONTRACT` on the wire and surfacing the
   stdout tail in CLI transport errors — **Amendment 2, `4bae73e` (#239, OMN-15522 / OMN-15535)**.
4. **Fourth attempt** (canary PASS at 2026-07-30T20:29:32Z, then a battery-launch failure): the battery ran 27
   clean baseline rows and then crashed at seed 4028 — a delegation-node quality-gate rejection
   (`MALFORMED: response is not valid JSON`) was raised as a TRANSPORT error rather than a semantic one, and the
   driver had no per-seed containment, so the process died with the match. Fixed by reclassifying quality-gate
   rejections as semantic errors (recoverable by the existing bounded reprompt loop) and adding per-seed casualty
   containment to the driver — **Amendment 3, `a3b0d8a` (#240, OMN-15566)**. The abandoned 27-row lane is disposed
   per §2.1 and Amendment 3 §1; zero rows from it are scored.
5. **Fifth attempt** (canary PASS at 2026-07-31T07:50:25Z, state-root `omn15488_learning_battery_r2`): completed
   cleanly, 61/61 rows, `BATTERY_DONE` sentinel — the run scored throughout this document and the scoring document.

---

## Citations

- Pre-registration overlay: `contracts_data/overlays/tactical_split_overdeal_v1_delegation_learning.yaml`
  (commits `ff5df34` #235, `4bae73e` #239, `a3b0d8a` #240)
- Driver: `scripts/run_lgate2_adaptation_battery.py`
- Gates: `scripts/check_preregistration_timing.py`, `scripts/check_contamination_gate.py`
- Raw data: `$ROOT/battery_raw.jsonl` (61 rows), `$ROOT/events.sqlite3` (opened `?mode=ro&immutable=1` throughout)
- Lineage record: `$ROOT/lineage/aggressive/31d9f8ceb1e3a5b6.../39e46ac3617c5794....yaml`
- Delegation-node state: `.onex_state/steel_onslaught/tactical_split_overdeal_v1_delegation_learning/delegation_state/{qwen35,qwen35_mirror_blue}/`
- Tickets: OMN-15488 (this battery), OMN-15522 / OMN-15535 (programming response contract + diagnostic masking),
  OMN-15566 (semantic-retry parity / per-seed containment), OMN-15377 (contamination-gate orphan-class gap, not
  reproduced here — this run has zero orphans)
- Scoring document (companion, separate deliverable): `docs/evidence/2026-07-31-lgate2-decisive-battery-scoring.md`

*All commands were run read-only (sqlite opened `?mode=ro&immutable=1` or plain `mode=ro`; no writes anywhere;
`git status --short` on the executing steel_onslaught clone was empty throughout). No claim in this document rests
on an agent self-report.*
