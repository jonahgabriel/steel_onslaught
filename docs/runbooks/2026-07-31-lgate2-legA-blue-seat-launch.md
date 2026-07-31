# OMN-15488 leg (a) — blue-seat endpoint-contrast battery: launch procedure

> **THIS DOCUMENT AUTHORIZES NO RUN.** It is the mechanical procedure for a launch
> that an operator has already said to start, in a session that does the launch as
> its own named, visible act. Landing it starts nothing.

Pre-registration of record: the header of
`contracts_data/overlays/tactical_split_overdeal_v1_delegation_learning_blue.yaml`,
which embeds §2–§7 of
`docs/evidence/2026-07-31-lgate2-legA-blue-seat-endpoint-contrast-prereg.md`
verbatim. Where this runbook and that header disagree, the header wins and the
disagreement is a reportable defect (prereg §12).

---

## 0. What this procedure exists to prevent

The leg-(a) pre-registration is complete as a design and was, until this
procedure landed, **not executable as written**. Three concrete gaps, each of
which would have surfaced only after a session had already committed to a
~5.5-hour endpoint reservation:

1. **The pre-registered seed blocks could not be flown.** §2.1 FD3 and §3
   pre-register 6001–6030 / 6101–6115 / 6201–6230, and AC2 asserts them exactly.
   `scripts/run_lgate2_adaptation_battery.py` wrote the base as the literal
   `4000` three times inline with no flag to move it. The driver now takes
   `--seed-base`.
2. **`--expected-rows 61` was wrong for 14 of the 15 possible clean outcomes.**
   See §5 below.
3. **The §6.3 canary decisiveness clause had no checker.** It is the clause that
   bounds the never-flown sniper-mirror stalemate risk, and it was prose.
   `scripts/check_canary_decisiveness.py` now decides it.

## 1. Preconditions — verify, do not assume

- [ ] The overlay's pre-registration commit is landed on `main` **before** any
      match. AC1 reads that commit's author timestamp (§4 below re-checks it
      against the executed lane).
- [ ] **FD5 pin re-assessment.** The prereg assessed every commit between
      `a3b0d8a` and `d78094a`. If the executing pin is later than `d78094a`,
      re-run that assessment over the intervening commits and record it as a
      dated amendment **appended to the overlay header** before launch. A pin
      carrying an unassessed change to the card path is a comparability defect
      (prereg §2.2 FD5).
- [ ] **§9 cadence re-verification, from the executing tree.** Confirm the
      executing overlay declares `card_cadence: paced` **and** that every
      terminal `CARDS_DISCARDED` close path in `src/steel_onslaught/match/runner.py`
      is still gated on `paced` at the executing pin. The OMN-15591 disposition
      is cadence-conditional and **void** otherwise; a leg (a) run on atomic
      cadence is not authorized by the pre-registration.
- [ ] At least one notification channel is exported (§4). `so battery-watch`
      refuses to launch without one, which is the point.

## 2. Environment — the hermetic snapshot

Build it per `docs/runbooks/2026-07-28-hermetic-battery-snapshot-recipe.md`
§1–§3. **§3 is mandatory and is not optional hygiene**: it cost the red lane two
failed launch attempts (OMN-15582). The gate is the verification, not the exit
code — assert `direct_url.json` shows `vcs_info.vcs == "git"` **and**
`vcs_info.commit_id == <pin>`.

Run everything below from `$SNAP/steel_onslaught` with `OMNI_HOME="$SNAP"`, and
never point `scripts/check-omnimarket-venv-drift.sh` (or anything doing a live
fetch) at the snapshot — it false-positives by design.

```bash
SNAP="<hermetic snapshot root>"
OVERLAY=contracts_data/overlays/tactical_split_overdeal_v1_delegation_learning_blue.yaml
BLUE=contracts_data/loadouts/qwen35/sniper_ironclad_lega_blue.yaml
RED=contracts_data/loadouts/qwen35/sniper_ironclad_lega_mirror_red.yaml
CANARY_ROOT="$SNAP/battery_state/omn15488_legA_canary"
BATTERY_ROOT="$SNAP/battery_state/omn15488_legA_blue"
```

## 3. Canary first — the ~20-minute decisiveness gate (§6.3)

Quarantined, throwaway state-root, `--fresh`, **never battery evidence in either
direction**. `--seed-base 9100 --n 2` flies exactly the pre-registered canary
seeds 9101 and 9102. `--promote-attempts 0` holds the canary to **exactly those
two matches**: the promote phase flies an empty seed list, so the driver stops
with its "L-GATE-2 not exercised" FINDING and never reaches the post phase. That
also means the canary cannot create a policy lineage or promote anything — a
quarantined canary must not touch the chain, and the baseline cap
(`max_value == genesis == 0.5`) already makes promotion impossible.

```bash
cd "$SNAP/steel_onslaught"
env -u PYTHONPATH OMNI_HOME="$SNAP" uv run python scripts/run_lgate2_adaptation_battery.py \
  --mode battery --seat blue --genesis 0.5 --step 2.0 --n 2 \
  --promote-attempts 0 --seed-base 9100 \
  --overlay "$OVERLAY" --blue-loadout "$BLUE" --red-loadout "$RED" \
  --state-root "$CANARY_ROOT" --fresh </dev/null
```

The canary's own exit code is **not** the gate — with a zero promote budget the
driver exits 1 by construction, which says nothing about the three clauses. The
gate is:

```bash
env -u PYTHONPATH uv run python scripts/check_canary_decisiveness.py \
  --state-root "$CANARY_ROOT" --overlay "$OVERLAY"
```

Exit 0 = all three clauses hold, the battery may be launched. Exit 1 = **do not
launch**. In particular, a clause-3 failure (neither match ended with a mech
destroyed) is reported as an execution-infrastructure finding — the sniper
mirror is stalemate-dominated at this arena/loadout — and leg (a) returns for
redesign under a NEW pre-registration. It is not a hypothesis result and it is
not grounds for quietly re-pairing.

## 4. The battery — supervised launch (§10.1)

```bash
export STEEL_BATTERY_NOTIFY_COMMAND="<argv that reaches the operator; outcome JSON on stdin>"
# and/or: export STEEL_BATTERY_NOTIFY_WEBHOOK="<chat-compatible webhook URL>"

pgrep -f "run_lgate2_adaptation_battery.py"   # MUST be empty before launching

cd "$SNAP/steel_onslaught"
nohup env -u PYTHONPATH OMNI_HOME="$SNAP" uv run so battery-watch \
  --run-id omn15488-legA-blue \
  --raw-path "$BATTERY_ROOT/battery_raw.jsonl" \
  --log-path "$SNAP/battery_state/omn15488_legA_blue.log" \
  --expected-rows 61 --expected-rows-max 75 \
  --stall-deadline-seconds 3600 \
  -- \
  uv run python scripts/run_lgate2_adaptation_battery.py \
    --mode battery --seat blue --genesis 0.5 --step 2.0 --n 30 \
    --promote-attempts 15 --seed-base 6000 \
    --overlay "$OVERLAY" --blue-loadout "$BLUE" --red-loadout "$RED" \
    --state-root "$BATTERY_ROOT" --fresh \
  </dev/null > "$SNAP/battery_state/omn15488_legA_watchdog.log" 2>&1 &
disown
```

`--overlay`, `--blue-loadout`, and `--red-loadout` are **mandatory and
explicit**: the driver's argparse defaults resolve to
`tactical_split_overdeal_v1_qwen.yaml` and a sniper-vs-berserker pairing — the
silent-wrong-condition failure OMN-15166 warns about.

`</dev/null` is load-bearing (an inherited terminal stdin has repeatedly caused
double-launch races), as is the `pgrep` above: a relaunch onto a `--state-root`
a live process still owns is a silent data race on
`battery_raw.jsonl`/`events.sqlite3`.

Record the watchdog's terminal state verbatim in the evidence — `COMPLETED` /
`INCOMPLETE` / `CRASHED` / `STALLED`, plus exit 3 if no channel accepted the
outcome. AC7 rejects a run that cannot show one.

## 5. Why `--expected-rows 61 --expected-rows-max 75`, and not the pre-registered `61`

§10.1 pins `--expected-rows 61`, copied from the red battery. That literal is
correct only for a run that promotes on its FIRST promote attempt, which is what
the red battery happened to do.

The driver writes one row per flown match and the promote phase **stops at the
first promotion** (`stop_on_promotion=True`), so a clean leg-(a) run writes
`30 + k + 30` rows for an unknown `k` in `1..15`:

| k (promote attempts flown) | rows | old `--expected-rows 61` verdict |
|---|---|---|
| 1 | 61 | COMPLETED |
| 2 | 62 | **INCOMPLETE — wrong** |
| … | … | **INCOMPLETE — wrong** |
| 15 | 75 | **INCOMPLETE — wrong** |

The watchdog compared with a strict `!=`, so 14 of the 15 clean outcomes would
have been reported INCOMPLETE and had their `--on-complete-exec` chain withheld.
`so battery-watch --expected-rows-max` makes the contract an inclusive range;
the bounds are derived by `expected_row_bounds(n=30, promote_attempts=15)` in
the driver rather than restated as literals, and
`tests/contracts/test_lgate2_lega_blue_overlay_omn15488.py` pins this runbook's
numbers against that derivation so the two cannot drift.

Dropping `--expected-rows` entirely was the other available answer and is
strictly worse: it disarms the short-clean-exit check OMN-15588 exists for, so a
battery that wrote 27 rows and exited 0 would read COMPLETED.

**The §6.1 NO-PROMOTION escape does not hide inside this range.** A no-promotion
run exits nonzero (the driver returns 1 with its "L-GATE-2 not exercised"
FINDING), so the watchdog reports CRASHED, never a short COMPLETED.

## 6. After the run — the acceptance gates (§8)

Run read-only, by an agent independent of the scoring assembler; the recompute
verifier must not review the assembler's draft (three-agent separation).

```bash
# AC1 — pre-registration timing. Cross-check against the overlay's FULL commit
# ancestry, not just this script's single-commit output.
env -u PYTHONPATH uv run python scripts/check_preregistration_timing.py \
  --state-root "$BATTERY_ROOT" --overlay "$OVERLAY"
git log --format='%H %aI %s' -- "$OVERLAY"

# AC2 — contamination / bijection. The gate is single-block by construction, so
# run it PER BLOCK and re-derive the union check explicitly, disclosing the
# interface limitation rather than force-fitting it.
for spec in "6000 30" "6100 15" "6200 30"; do
  set -- $spec
  env -u PYTHONPATH uv run python scripts/check_contamination_gate.py \
    --state-root "$BATTERY_ROOT" --seed-base "$1" --n "$2"
done
```

The promote block is a **budget, not a count** — `--n 15` on the 6100 block is
the upper bound, and the gate must be read against the `k` matches actually
flown (`battery_summary.json`'s promote phase names them). `battery_summary.json`
also publishes `seed_base` and `expected_row_bounds`, so the executed seed lane
and row contract are falsifiable from the artifact alone.

AC3–AC9 are computed in the acceptance/scoring documents from
`$BATTERY_ROOT/battery_raw.jsonl`, cross-checked against
`$BATTERY_ROOT/events.sqlite3` opened read-only (`immutable=1`).
`battery_summary.json` is **not** a source for any scored figure (§4.4).
