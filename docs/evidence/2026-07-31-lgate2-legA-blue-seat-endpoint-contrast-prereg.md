# OMN-15488 leg (a) — BLUE-SEAT ENDPOINT-CONTRAST REPLICATION — PRE-REGISTRATION — 2026-07-31

> **LAUNCH IS A SEPARATE OPERATOR-VISIBLE STEP — THIS DOCUMENT AUTHORIZES NO RUN.**
> Nothing here starts a battery, reserves the MLX endpoint, or pre-approves a launch. Landing this
> document creates a pre-registration of record and nothing else. The run begins only when an
> operator explicitly says so, in a session that does the launch as its own named, visible act.

**Ticket:** OMN-15488 (parent battery lane). **Authoring session:** `fable-steel-0731` wave-2.
**Repo state at authoring:** `jonahgabriel/steel_onslaught@d78094a` (`origin/main`).

---

## 0. What this document is, and what it is not

This is the pre-registered design for **leg (a)** of the Steel scientific fork resolved by **operator
ruling 25 (2026-07-31 ~17:00Z)**:

> the scientific fork runs as a **SERIES** — (a) the blue-seat endpoint-contrast replication FIRST,
> then (b) the non-prompt consumer probe (#128 revisit item (c)) **regardless of (a)'s result**;
> neither leg is terminal alone; a symmetric null is publishable.

**It is:** the hypothesis, the endpoint definitions, the decision bands, the seeds, the escapes, the
interpretation map, the acceptance gates, and the mandatory execution path for leg (a) — fixed before
any data exists.

**It is not:** an executable artifact. The AC1 timing gate
(`scripts/check_preregistration_timing.py`) reads the **executing overlay file's** commit author
timestamp, not this document's. See §12 — the launch session owes an additional obligation this
document creates rather than removes.

**It weakens nothing.** Every gate class that applied to the OMN-15488 red-seat battery applies here
unchanged, and this document adds three (AC7 supervised-launch, AC8 share-denominator legibility, AC9
seat-policy no-op proof). The OMN-15489 duel-gate causal-bypass fix remains a hard gate on any live
`selection_outcome_v1` run and is not touched, relaxed, or routed around by anything below.

---

## 1. Position in the seat × step matrix

Every scored L-GATE-2 behavioral cell this program has produced, with the two axes that ruling 25's
leg (a) exists to separate:

| Battery | learning seat / persona | pairing | genesis → promoted (step) | binding | n | `D_vent` | `d` | one-sided `p` |
|---|---|---|---|---|---:|---:|---:|---:|
| #126 (2026-07-22) | blue / sniper | sniper vs berserker | 1.0 → 1.25 (0.25) | HTTP `OpenAICompatibleClient` | 10 | +8.3pp | (not stated) | (t≈3.15, not converted) |
| #128 (2026-07-22) | blue / sniper | sniper vs berserker | 1.0 → 1.5 (0.5) | HTTP `OpenAICompatibleClient` | 30 | +4.5pp | ~0.51 | 0.027 † |
| #128 red attempt | red / berserker | berserker vs sniper | 1.0 → 1.5 (0.5) | HTTP | 30+5 | **never scored** — 0/35 wins, promotion structurally impossible | — | — |
| OMN-15488 (#241) | red / berserker | **mirror** berserker | 0.5 → 2.5 (2.0) | `onex_delegation` / MLX | 30 | +1.96pp | 0.389 | 0.070 |
| **leg (a) — this prereg** | **blue / sniper** | **mirror** sniper | **0.5 → 2.5 (2.0)** | `onex_delegation` / MLX | 30 | *to be measured* | | |

† #128's source document reports this endpoint two-sided (`t=+1.98, df=51.0, p=0.053`); halved here for
like-for-like comparison against the one-sided pre-registered tests. `d` is sidedness-independent.

**The confound leg (a) exists to break.** The OMN-15488 scoring document's §5.1 states it plainly: the
"bigger step produced a weaker vent effect" observation **crosses seat and persona simultaneously with
step size**, because both prior vent instances were blue/sniper and OMN-15488 was the first scored
red/berserker contrast of any kind. That is not a clean step-size test and was never claimed as one.

Leg (a) supplies the missing cell. Against **OMN-15488** it holds genesis, step, binding, overlay
shape, pairing structure (mirror), phase/seed/cap structure, driver, and instruments constant and
varies **persona only** — the single cleanest contrast this program can construct. Against **#128** it
remains multi-delta (step *and* genesis *and* binding) and is **not** the scored inference; see §7.3.

---

## 2. Design — seat, pairing, and driver knobs, with every forced delta named

### 2.1 Configuration

| Knob | OMN-15488 (red leg, executed) | leg (a) (this prereg) | delta? |
|---|---|---|---|
| `--mode` | `battery` | `battery` | — |
| Evaluator binding | `win_damage_differential_v1` | `win_damage_differential_v1` | — |
| `--seat` (learning seat) | `red` | `blue` | **FD1** |
| Learning-seat loadout | `llm_qwen35_berserker.yaml` | new sniper-ironclad loadout (§2.3) | **FD2** |
| Opponent loadout | `qwen35/llm_qwen35_berserker_mirror_blue.yaml` | new mirror sniper loadout (§2.3) | **FD2** |
| Pairing | mirror (both seats same chassis/persona) | mirror (both seats same chassis/persona) | — |
| `deck_policy` per seat | 4 movement / 4 weapon over-deal, `register_count: 5`, `deck.movement.v1` / `deck.weapon.v1`, both sides | identical, both sides | — |
| `archetype` label per seat | `berserker` / `berserker` | `sniper` / `sniper` | **FD2** (label must equal resolved persona) |
| `card_cadence` | `paced` | `paced` | — (load-bearing, §9) |
| `--genesis` / `--step` | `0.5` / `2.0` | `0.5` / `2.0` | — |
| `--n` | `30` | `30` | — |
| `--promote-attempts` | `15` | `15` | — |
| Seed blocks | 4001–4030 / 4101–4115 / 4201–4230 | **6001–6030 / 6101–6115 / 6201–6230** | **FD3** |
| Provider binding | `kind: onex_delegation`, `backend_id: local-coder-mlx` | identical | — |
| Served model | `mlx-community/Qwen3.6-35B-A3B-8bit` @ `stickybeatz-studio:8401` | identical | — |
| Overlay file | `tactical_split_overdeal_v1_delegation_learning.yaml` | new sibling overlay (§2.3) | **FD4** |
| Steel pin | `a3b0d8a` | `d78094a` or later (§2.5) | **FD5** |
| Launch path | ad-hoc `nohup` + disk sentinels | `so battery-watch` (§10) | **FD6** (strictly stronger) |

### 2.2 Forced deltas, each justified

**FD1 — learning seat `red` → `blue`.** This is the manipulated variable and the point of the leg.

**FD2 — persona `berserker` → `sniper` on BOTH seats (mirror preserved).** In this program's data
"seat" has never been separable from persona: blue has always been the sniper and red the berserker,
and §5.1's confound names them together. A blue-**berserker** cell would be a near-null manipulation —
inside a mirror both sides are functionally identical apart from side identity, spawn, and initiative
tie-break — and would leave the persona confound exactly where it is. The persona is the substantive
axis; swapping it on both seats keeps the pairing a mirror, which is the property being held constant.
Verified: the OMN-15488 overlay's `deck_policy` is already **byte-identical between red and blue**
(4/4 hand quota, `register_count: 5`, same deck ids), and the source overlay
`tactical_split_overdeal_v1_qwen.yaml` uses the same balanced 4/4 over-deal on its sniper blue seat, so
FD2 does **not** change the card partition or the size of the decision space. What it changes is
chassis/weapons (`chassis.heavy.ironclad_mk1` + artillery mortar / harpoon gun, per
`contracts_data/loadouts/qwen35/sniper_ironclad.yaml`) and the persona prompt.

**FD3 — disjoint seed blocks.** 6xxx is unused by any prior steel battery (4xxx = L-GATE-2 lanes,
5xxx = display-salience, 9xxx = canaries). Disjointness keeps the contamination/bijection gate (AC2)
meaningful and makes cross-lane seed collision detectable rather than plausible.

**FD4 — new overlay file, not an edit of the red battery's overlay.** OMN-15488's overlay is the
pre-registration of record for a *merged, published* result. It is immutable. Leg (a) gets a sibling
file whose header carries this document's normative sections verbatim (§12). Every hypothesis clause,
endpoint definition, band, escape, multiplicity note, and interpretation-map row is copied unchanged
except where §4/§7 state a difference explicitly.

**FD5 — steel pin moves forward from `a3b0d8a` to `d78094a` (or later).** Four commits land between
them. Each is assessed against the requirement that leg (a) remain comparable to OMN-15488:

- `e5eab9a` (#242, OMN-15582) — docs only.
- `630ce08` (#243, OMN-15587) — `battery_summary.json` share denominator. **Changes a reported
  artifact, changes no measured behavior.** OMN-15488's scoring read nothing from
  `battery_summary.json`; leg (a)'s scoring will do the same (§4.4).
- `aae56f0` (#245, OMN-15522), `21d58f2` (#244), `428445f` (#246, OMN-15585) — schema/parser residuals
  and UI; no card-selection behavior on this path.
- `f1e6a07` (#248, OMN-15489) — the duel-gate causal-bypass fix. **Verified a behavioral no-op for this
  battery, at source, not from the commit message:**
  `composition.assemble_match_with_dependencies` binds `card_adapter.seat_plan_rules` only from
  `seat_policy_rule_for_spec(...)`, and `cards/pilot_policy.py:304-305` returns `None` for any spec
  whose `archetype` is outside `DETERMINISTIC_ARCHETYPES`. Both leg-(a) seats — like both OMN-15488
  seats — resolve to `archetype: llm` pilot specs, so **no seat rule is bound and the card-programming
  path is unchanged**. The commit's own scope note ("`win_damage_differential_v1` is untouched")
  matches what the source does.
- `d78094a` (#247, OMN-15588) — the watchdog. Additive; supervises the driver, does not alter it.

**A launch-time re-verification is required, not optional:** if the executing pin is later than
`d78094a`, the launch session must re-run this same assessment over the intervening commits and record
it, before launch, in the overlay header as a dated amendment. A pin that carries an unassessed
behavioral change to the card path is a comparability defect, not a detail.

**FD6 — supervised launch path.** Mandatory, §10. Strictly stronger than what OMN-15488 ran under.

### 2.3 Artifacts the launch session must author (before the pre-registration commit)

None of these exist yet. Authoring them is part of the launch session's setup, not of this lane:

1. `contracts_data/overlays/tactical_split_overdeal_v1_delegation_learning_blue.yaml` — sibling of the
   red overlay; `deck_policy` seats both `archetype: sniper`; `programmers` both sniper pilot spec ids;
   `card_cadence: paced` (load-bearing, §9); `pilot_registry_dir` pointing at its own registry dir.
2. `contracts_data/pilots/tactical_split_overdeal_v1_delegation_learning_blue/` — two pilot specs,
   `archetype: llm`, distinct `provider_id`s.
   **Known trap, pre-recorded:** `validate_seat_programmer_identity` unconditionally rejects two seats
   resolving to the same `(provider, persona)` identity — a literal reuse of one sniper spec on both
   sides raises `SeatIdentityError`. The red battery hit this and solved it with a
   distinct-provider-id/identical-persona sibling spec; leg (a) copies that solution.
3. Two sniper loadouts under `contracts_data/loadouts/qwen35/` — learning-seat and mirror — differing
   only in `id` and `pilot_id`, per the red battery's mirror-loadout precedent.
4. A contract test pinning the new overlay's header sha, mirroring
   `tests/contracts/test_lgate2_delegation_overlay_omn15488.py`.

### 2.4 Rejected alternative, recorded so it is not silently revisited

**Pure side swap (`--seat blue` on the unchanged red overlay, berserker mirror retained).** Zero new
artifacts, zero stalemate risk, and a genuine internal replication of OMN-15488 with fresh seeds and a
fresh endpoint-state window. **Rejected** because inside a berserker mirror the two sides are
functionally identical, so it manipulates side identity rather than seat/persona: it does not complete
a seat × step matrix and does not touch §5.1's confound. It remains available as a *separate*
replication battery under its own pre-registration; it is not leg (a).

### 2.5 The executing command (declared before any run)

```
uv run python scripts/run_lgate2_adaptation_battery.py \
  --mode battery --seat blue --genesis 0.5 --step 2.0 --n 30 --promote-attempts 15 \
  --overlay contracts_data/overlays/tactical_split_overdeal_v1_delegation_learning_blue.yaml \
  --blue-loadout contracts_data/loadouts/qwen35/<blue sniper learning loadout>.yaml \
  --red-loadout  contracts_data/loadouts/qwen35/<red sniper mirror loadout>.yaml \
  --state-root "$SNAP/battery_state/omn15488_legA_blue" --fresh
```

Run from the hermetic snapshot's `steel_onslaught` root (§10), wrapped in `so battery-watch` (§10).
`--overlay`, `--red-loadout`, and `--blue-loadout` are **mandatory and explicit**: the driver's argparse
defaults resolve to `tactical_split_overdeal_v1_qwen.yaml` and the sniper-vs-berserker pairing — the
exact silent-wrong-condition failure the red battery's own remediation note records and OMN-15166
warns about.

---

## 3. Phases, seeds, and caps

The isolating manipulation is identical to the red battery's: all three phases run the same overlay,
loadouts, arena, binding, and frozen environment on disjoint seed blocks; the **only** difference
between a baseline row and a post row is the policy generation the learning seat flies, enforced by
the evaluator's `max_value` caps and machine-asserted per row from `MATCH_STARTED` provenance.

| Phase | seeds | n / budget | `max_value` | generation flown |
|---|---|---:|---:|---|
| baseline | 6001–6030 | 30 | `0.5` (= genesis; promotion impossible) | 0, with its guidance block |
| promote | 6101–6115 | budget 15 | `2.5` (= genesis + step) | 0 → fires the first `POLICY_PROMOTED` |
| post | 6201–6230 | 30 | `2.5` (chain frozen at generation 1) | 1 |

Canary (quarantined, throwaway state-root, **never battery evidence in either direction**): seeds
9101–9102, n=2. §6.3 states its gate.

---

## 4. Endpoints

### 4.1 PRIMARY (the declared-direction question)

For the **learning seat (`player.blue`) only**, per match:

```
ws = (planned attack + planned special) / (total planned cards)
```

defined when total planned > 0. A match with zero planned cards is excluded from the primary and
**counted explicitly** in the scoring document (expected occurrences: zero). Then

```
D_ws = mean(ws | post, n=30) - mean(ws | baseline, n=30)
```

tested with a **one-sided Welch t, direction UP, alpha = 0.05**.

**Declared direction and its justification:** UP. The promoted policy moves aggression from 0.5 to
2.5, spanning both named regimes of the guidance sentence
(`steel_onslaught.llm.policy_guidance._KNOWN_PARAMETER_SEMANTICS`: *"At high aggression, fill nearly
every free register with legal attack cards; at low aggression, prefer repositioning and heat
management"*). If the guidance governs selection at all, weapon-commitment share must rise. Direction
is declared identically to the red battery so the two legs are directly comparable.

**Bands (exhaustive, no discretionary region):**

```
SUPPORTED        — D_ws > 0 AND p < 0.05   -> H_POLICY_DOSE_RESPONSIVE at this cell.
DIRECTIONAL-ONLY — D_ws > 0 AND p >= 0.05  -> unresolved at this n; reported as such, NOT as support.
NOT-SUPPORTED    — D_ws <= 0.
```

### 4.2 CONFIRMATORY-SECONDARY — vent keep-rate

Per match, learning-seat vent keep-rate (`planned vent / dealt vent`), defined when dealt vent > 0:

```
D_vent = mean(vent keep | post) - mean(vent keep | baseline)
```

one-sided Welch t, **direction UP** — the twice-replicated paradoxical direction — alpha = 0.05.
Bands: `CONFIRMED (D_vent > 0, p < 0.05)` / `DIRECTIONAL-ONLY` / `NOT-CONFIRMED (D_vent <= 0)`.
A baseline vent floor does not block this endpoint; UP from the floor is its most sensitive
configuration.

**This endpoint carries a stronger prior on leg (a) than it did on the red leg, and that is stated up
front rather than discovered afterward.** Both prior observations of the paradoxical vent signal
(#126 +8.3pp, #128 +4.5pp `d≈0.51`) were measured on **this** seat/persona. Leg (a) is therefore the
first same-seat test of that signal at the endpoint contrast. A NOT-CONFIRMED result here is
substantially more informative against H_POLICY_PARADOXICAL than the red leg's DIRECTIONAL-ONLY was,
and a CONFIRMED result is correspondingly less surprising. Neither reading is upgraded or downgraded
for that reason — the band is scored exactly as measured.

### 4.3 TERTIARY-DESCRIPTIVE — vent PLANNED SHARE, with the OMN-15587 denominator, named explicitly

Per match, learning-seat vent planned share (`planned vent / total planned cards`), reported per phase
as a mean **over every flown match in the phase (n=30), substituting an explicit `0.0` for a match that
planned no vent card** — never over "the matches where the `vent` key happened to be present."

This is a **reported descriptive, never gating**, and it is called out separately because of a live
comparability trap:

> **OMN-15488's published `battery_summary.json` `mean_planned_share.vent` figures are NOT comparable
> to leg (a)'s and must not be placed in a table beside them without recompute.** That artifact used a
> present-key-only denominator (2 of 30 baseline rows, 5 of 30 post rows), publishing `0.0154` /
> `0.0223` where the all-flown-matches values are `0.0010` / `0.0037` — inflated **15.4x** and **6.0x**
> respectively (OMN-15587). No merged OMN-15488 finding moves, because its scoring document reads
> nothing from `battery_summary.json` and computed `0.001026` / `0.003715` from `battery_raw.jsonl`
> (§4.2 of that document) — figures that match OMN-15587's corrected column exactly.

The driver fix landed at `630ce08` (#243), so leg (a)'s `battery_summary.json` will carry the corrected
denominator **and** publish `planned_share_matches` so the denominator is falsifiable from the artifact
alone. Leg (a)'s scoring document still computes every scored figure from `battery_raw.jsonl` (§4.4);
`planned_share_matches` is used only as a cross-check, never as a source.

### 4.4 Source-of-truth discipline

Every scored figure is computed from `$ROOT/battery_raw.jsonl` and cross-checked against
`$ROOT/events.sqlite3` (opened read-only / `immutable=1`). `battery_summary.json` is **not** a source
for any scored figure, matching the red battery's discipline.

### 4.5 MULTIPLICITY, stated plainly

Two pre-registered gating endpoints (§4.1, §4.2), each at alpha 0.05, testing **different** hypotheses
(declared-direction vs paradoxical channel). **No family-wise correction is applied**, and the scoring
document must present both p-values uncorrected and say so.

### 4.6 Pre-declared EXPLORATORY cross-battery contrast (non-gating, pre-specified so it is not post-hoc)

A two-sample Welch t of leg (a)'s per-match vent keep-rate **difference distribution** against
OMN-15488's, i.e. the seat/persona × endpoint-contrast interaction at fixed step, genesis, binding, and
pairing structure. Declared here **only** so that reporting it later is pre-specified rather than
fished. It is **explicitly non-gating**, its p-value is uncorrected and reported as exploratory, and it
is severely underpowered (an interaction test on two n=30 samples has materially less power than either
main effect). It cannot move any band in §4.1, §4.2, or §7.

### 4.7 TERTIARY descriptives (reported, never gating)

Remaining per-category keep-rates and planned shares (movement predicted DOWN under
dose-responsiveness); `llm_completion_failed` rate parity across phases (retry-belt health, not a
hypothesis metric); per-phase win counts (**the mirror pairing makes win rate uninformative about the
hypothesis by construction** — both seats' boards evolve under one seat's policy shift); and, new for
leg (a), the **decisive-vs-draw split per phase**, which §6.3 and §9 both depend on.

---

## 5. Statistical honesty, declared before the run

n=30 per phase with a one-sided Welch t at alpha 0.05 has ~80% power for a standardized effect of
`d ≈ 0.65` per endpoint. **The historically observed vent effect sizes on this exact seat sit below
that floor** (`d ≈ 0.51` at #128; #126's n=10 estimate is larger but far noisier), and the red leg
observed `d = 0.389`. **A DIRECTIONAL-ONLY vent outcome is therefore the modal expectation for leg (a),
not a surprise, and it is a power statement — not evidence of absence.** The scoring document must say
so rather than upgrade or downgrade the band.

n is held at 30 deliberately: matching the red battery's n is what makes the persona contrast in §1
clean. Raising n would improve leg (a)'s own resolution at the cost of the matched design, and that
trade is not made silently here.

---

## 6. Pre-declared escapes (unclamped — reported, never folded in)

### 6.1 NO-PROMOTION

The promote phase exhausts its 15-match budget without a `POLICY_PROMOTED` event → the finding is
reported as **"L-GATE-2 leg (a) not exercised at this pairing/binding."** The primary and
confirmatory-secondary endpoints are **not** scored, and **the battery is not silently re-paired and
re-run under this pre-registration.** A different pairing requires a NEW pre-registration with its own
timing gate. This clause is deliberately fail-closed rather than pre-authorizing a fallback, because a
pre-authorized re-pair is a "run until it promotes" pattern wearing a prereg's clothes.

**Risk assessment, stated in advance:** this is a genuinely elevated risk for leg (a) and higher than
it was for the red leg. A sniper-vs-sniper mirror has never been flown. Both seats are long-range
ironclads; `win_damage_differential_v1` promotes only on a **decisive** learning-seat win with positive
damage differential, so a stalemate-dominated regime (draws at the tick bound) would exhaust the
promote budget. §6.3's canary exists to bound the cost of discovering that from ~5.5 hours to ~20
minutes.

### 6.2 CEILING

Baseline mean `ws >= 0.95` → the primary contrast has no arithmetic headroom: raw distributions are
reported, the primary is **not** scored, and the vent endpoint **is** still scored.

**Note the sniper-specific version of this risk.** #128 recorded blue-sniper attack keep-rate ceilinged
at 0.997–0.998 in both phases at genesis 1.0, and the red leg found attack keep ceilinged at exactly
1.0 in both phases. If attack keep is again ceilinged, the primary's only movement channel is special
traded against movement/vent — a real constraint on what this cell can show even in an
H_POLICY_DOSE_RESPONSIVE-true world. That constraint is **disclosed here in advance** and must be
restated in the scoring document; it does not by itself trigger the CEILING escape, which keys on
combined baseline mean `ws`, not on attack keep alone.

### 6.3 CANARY DECISIVENESS GATE (new for leg (a); an addition, not a relaxation)

Before the battery is launched, a quarantined n=2 canary (seeds 9101–9102, throwaway state-root,
`--fresh`) must satisfy **all** of:

1. Both matches produce a `battery_raw.jsonl` row with `replay_validity == 1` for **both** seats.
2. Providers observed ⊆ the overlay's declared `provider_id` set.
3. **At least one of the two matches terminates DECISIVELY** (a `VICTORY_DECLARED` with a mech
   destroyed), not at the tick bound.

Clause 3 is the new one and it is what makes the §6.1 risk cheap. If clause 3 fails, **the battery is
NOT launched**; the outcome is reported as an execution-infrastructure finding ("the sniper mirror is
stalemate-dominated at this arena/loadout") and leg (a) returns for redesign under a new
pre-registration. A canary result is never battery evidence in either direction.

---

## 7. Pre-declared interpretation map

### 7.1 Within leg (a) — scored bands → reading

| primary | vent | reading at this cell |
|---|---|---|
| SUPPORTED | any | dose-responsiveness at regime contrast **on the blue/sniper seat**; the L-GATE-2 behavioral half PASSES at this operating point; step-size sensitivity becomes the follow-up. |
| NOT-SUPPORTED | CONFIRMED | the guidance block IS causally consumed but the declared **semantics** are the defect (#128 revisit item (a): wording), not the learning chain; the paradoxical channel is proven **on the seat where it was twice observed**. |
| NOT-SUPPORTED | NOT-CONFIRMED | H_POLICY_INERT holds at the mechanism's most favorable operating point **on this seat too**. Combined with the red leg this is a **symmetric null** — see §7.2, and note that ruling 25 makes it publishable and non-terminal. |
| any | DIRECTIONAL-ONLY | reported as **unresolved**; no terminal/non-terminal call is made from an unresolved band. |
| DIRECTIONAL-ONLY | any | same — unresolved. |

### 7.2 Across the matrix — what leg (a) adds, cell by cell

- **Leg (a) NOT-SUPPORTED + red leg NOT-SUPPORTED** → the primary is null on **both** seats at the
  endpoint contrast. This is the symmetric null ruling 25 names as publishable in its own right. It is
  the strongest available evidence for H_POLICY_INERT and it is a **real result, not a failed run.**
- **Leg (a) SUPPORTED + red leg NOT-SUPPORTED** → dose-responsiveness is **persona-specific**: the
  mechanism works on the sniper and not the berserker. §5.1's confound resolves in favor of
  seat/persona, not step size, and the "bigger step didn't help" reading of the red leg is retired.
- **Leg (a) vent CONFIRMED + red leg vent DIRECTIONAL-ONLY** → the paradoxical channel is real and
  **sniper/blue-specific** rather than a general aggression-guidance effect. This is live reading (b) of
  the red scoring document's §5.1 and it becomes the favored one.
- **Leg (a) vent NOT-CONFIRMED** → the twice-replicated signal fails its first same-seat pre-registered
  test at the largest available contrast. #126/#128's replication would then be best read as
  step-size-specific or as an artifact of the HTTP binding, and the post-hoc Fisher `p ≈ 0.003` that
  motivated promoting vent to a pre-registered endpoint would be substantially undercut.

### 7.3 What leg (a) **cannot** conclude — read this before quoting any result

1. **Leg (a) is NOT terminal for the prompt-guidance mechanism, whatever it finds.** Ruling 25 is
   explicit: leg (b) (the non-prompt consumer probe) runs **regardless of (a)'s result**, and neither
   leg is treated as terminal until both report. **A null on leg (a) does not license the TERMINAL
   call**, and a positive on leg (a) does not cancel leg (b). This supersedes, for the series, the red
   overlay's own standalone clause that a third null would be "pre-declared TERMINAL for the
   mechanism."
2. **It is not a clean step-size test against #126/#128.** That comparison additionally crosses genesis
   (1.0 → 0.5) and binding (HTTP `OpenAICompatibleClient` → `onex_delegation`/MLX). Absolute levels are
   not comparable across bindings at all (`LlmBusDelegationClient` does not forward `temperature`,
   collapses the system/user split into one flat prompt, and encodes `json_mode` as prompt text). Only
   within-battery contrasts are scored, and the cross-battery statement leg (a) licenses is a
   **direction** claim, not a magnitude claim.
3. **The clean contrast it does license is persona, against OMN-15488** — same genesis, step, binding,
   overlay shape, pairing structure, phase/seed/cap structure, driver, and instruments.
4. **Win rate says nothing about the hypothesis.** The mirror pairing makes it uninformative by
   construction.
5. **No claim generalizes** beyond `local-coder-mlx` / Qwen3.6-35B-A3B-8bit, this arena/loadout pairing,
   this seed set, this binding, card mode only, one model, one endpoint process.
6. **Phases are sequential, not interleaved**, on one MLX endpoint process. Endpoint-side drift between
   the baseline and post windows (restart, KV-cache/batching state, thermal/load) could shift both
   phases' absolute levels invisibly. Leg (a) has no interleaved-phase control and none is proposed.

---

## 8. Acceptance gates

Equivalent to the red battery's AC set (AC1/AC2/AC3/AC5/AC6), plus three additions. All are run
**read-only** by an agent independent of the scoring assembler, and the recompute verifier must not
review the assembler's draft — the three-agent separation the red battery used (its §5) is required
here, not optional.

| AC | Gate |
|---|---|
| **AC1** | **Pre-registration timing.** `scripts/check_preregistration_timing.py --state-root $ROOT --overlay <leg-a overlay>` exits 0: the overlay's latest commit author timestamp precedes the first `match_started`. Cross-checked against the overlay's **full** commit ancestry (`git log --format='%H %aI %s' -- <overlay>`), not the script's single-commit output, and against `MIN(emitted_at)` over `match_started` queried directly from `events.sqlite3`. |
| **AC2** | **Contamination / bijection / casualties.** `match_started` ↔ `match_ended` ↔ `battery_raw.jsonl` are the same set of `match_id`s (bijective, zero orphans of any class); seeds are exactly 6001–6030 / one or more of 6101–6115 / 6201–6230 with zero duplicates and zero out-of-block seeds; `skipped_seeds` empty in every phase and at top level; `replay_validity == 1` for both seats on every row; excluded-row counts stated explicitly per endpoint. `check_contamination_gate.py` is single-block by construction and cannot express a three-block lane — run it per block and **re-derive the union check explicitly**, disclosing the interface limitation rather than force-fitting or silently skipping it. |
| **AC3** | **Audit chain.** All baseline rows `generation == 0` with `source_lineage_digest == null`; exactly one `policy_promoted` ledger event, byte-identical to the promote row's embedded payload; all post rows `generation == 1` with `policy_id`/`spec_hash`/`source_lineage_digest` byte-equal to it; the lineage record exists on disk; and `genesis 0.5 + step 2.0 = 2.5` agrees between the driver's declared arithmetic and the materialized lineage record. |
| **AC4** | **Manipulation landed.** Every post-phase prompt actually carried the promoted-generation guidance text. *(Deferred at the red battery; required here — it is the one gate that proves the manipulation reached the model at all.)* |
| **AC5** | **Scoring.** Both pre-registered endpoints computed exactly as §4.1/§4.2 define them, from `battery_raw.jsonl`, with the t/p implementation validated against reference values **before** being trusted on the data and cross-checked against an independent implementation. Both p-values reported uncorrected, with §4.5 quoted. |
| **AC6** | **Delegation receipts.** `provider_id` literals ⊆ the overlay's declared set in all three `llm_completion_*` event types; `requested = resolved + failed` exactly at lane, provider, and phase granularity; delegation-node capture logs spot-verified inside a specific named battery-window interval, not merely present as directories. |
| **AC7** | **Supervised launch (new).** The run was launched through `so battery-watch` with at least one active notification channel, and the terminal state it reported (`COMPLETED` / `INCOMPLETE` / `CRASHED` / `STALLED`) is recorded verbatim in the evidence. A run that cannot show its watchdog terminal state is not acceptable evidence. |
| **AC8** | **Share denominator (new).** `battery_summary.json` carries `planned_share_matches`, and its value equals the count of rows that programmed anything in each phase. §4.3's non-comparability statement appears in the scoring document. |
| **AC9** | **Seat-policy no-op (new).** Both seats resolved to `archetype: llm` specs and therefore bound **no** `seat_plan_rules`, proven from the run's own artifacts — so #248 is confirmed a behavioral no-op on this path and the comparability claim in FD5 holds for the executed pin, not just the authored one. |

`python-test`, `frontend-test`, `sanitize-text`, and `evidence-schema` must be green on every PR in
this leg, as for all steel work.

---

## 9. OMN-15591 DISPOSITION — does the card-round replay-validation defect taint leg (a)?

**Verdict: NO for leg (a) as designed, and the reason is mechanical and empirically corroborated, not
an assumption. OMN-15591 is not a gate on this leg. It remains a gate on leg (b).**

The concern is legitimate on its face: OMN-15591 states that a card-mode match ending **decisively**
fails card-round replay validation because the final partial round emits no `CARDS_DISCARDED`, and its
own "why it matters" paragraph says this "bounds what a live `selection_outcome_v1` battery can
collect" — every duel that ends in a kill dies instead of returning a result, which could bias a
battery toward draws and declines. Leg (a) is a `win_damage_differential_v1` battery that **promotes
only on a decisive learning-seat win**, so if that defect reached this path it would be disqualifying.

### 9.1 Mechanism — why the battery path is not affected (file-level)

`src/steel_onslaught/match/runner.py`, at `origin/main` `d78094a`: **every** call site that closes an
in-flight card round with a terminal `CARDS_DISCARDED` is gated on `self._card_cadence == "paced"`:

- `:523` — lifecycle-STOP abort path (`reason="aborted"`)
- `:539` — pre-tick max-ticks close (`reason="max_ticks"`, `emit_match_ended=False`)
- `:551` — post-tick terminal close, with the **atomic** branch at `:553` doing
  `self._card_active_round = None` and emitting nothing
- `:623` — the decisive-death path: `elif self._card_cadence == "paced": self._cancel_active_card_round(tick=next_tick, reason="decisive_death")`
- `:1046` — `_before_fold_emit`, which closes the round before a fold-produced `VICTORY_DECLARED` /
  `MATCH_ENDED`, guarded by `and self._card_cadence == "paced"`

`_cancel_active_card_round` (`:1071`) republishes the round's `CARDS_DISCARDED` specs with
`reason="cancelled:<reason>"`, which is exactly the complete terminal lifecycle batch
`validate_card_round_events` requires. In **atomic** cadence none of that runs — the active round is
dropped — which is precisely OMN-15591.

**The cadence is not incidental, it is declared configuration.** The red battery's overlay declares
`card_cadence: paced` (`tactical_split_overdeal_v1_delegation_learning.yaml:474`), as does every
sibling `tactical_split_overdeal_*` overlay in the tree. **Leg (a) declares `card_cadence: paced` as a
load-bearing, pre-registered requirement (§2.1, §2.3).**

By contrast, `src/steel_onslaught/match/duel.py:94` and `:127` call
`assemble_match_with_dependencies` **without** a `card_cadence` argument, and the default is `atomic`
(`composition.py:395`, `:1656`; `contracts/application.py:185`). That is the configuration OMN-15591's
own reproduction uses — `tests/learning/test_duel_card_mode_causality_omn15489.py`, which the ticket
says fails once `_MAX_TICKS` is raised past the decisive tick. **The defect lives on the atomic duel
path, which leg (a) does not touch.**

### 9.2 Empirical corroboration — 61 decisive card-mode matches, zero replay failures

The OMN-15488 `_r2` battery ran on this exact overlay, cadence, driver, and evaluator binding:

- **Zero draws across all 61 matches** — per-phase win counts baseline 15/15, promote 1/0, post 19/11
  (red scoring document §4.4). Every one of the 61 matches terminated **decisively**, which is the
  condition OMN-15591 describes.
- **`replay_validity == 1` for both `player.red` and `player.blue` on 61/61 rows, zero exceptions**
  (red acceptance document §2, red scoring document §Method).

If OMN-15591 reached the paced battery path, that run could not have produced 61/61 valid replays on 61
decisive matches. It is a 61-for-61 empirical disproof on the same configuration leg (a) will use, not
an argument from code reading alone.

### 9.3 What this disposition does **not** claim

1. **OMN-15591 is a real, open defect** (Backlog, High). Nothing here closes it, downgrades it, or
   argues it should not be fixed.
2. **It remains a hard bound on leg (b)** if leg (b) runs a live `selection_outcome_v1` lane, whose
   `DuelEvaluator` duels run atomic. Leg (b)'s own pre-registration must dispose of it on its own
   evidence — and OMN-15489's fix does **not** address it (that ticket's own residual #3 says so).
3. **This disposition is cadence-conditional and must be re-verified at launch.** If the executing
   overlay does not declare `card_cadence: paced`, or if a future commit changes the cadence gating in
   `runner.py`, this entire section is void. The launch session must confirm — from the executing
   overlay file and from `runner.py` at the executing pin — that both still hold, and record the
   confirmation. **A leg (a) run on atomic cadence is not authorized by this pre-registration.**
4. **AC2's `replay_validity == 1` requirement stands regardless.** It is the standing mechanical check
   that would catch this class if any of the above changed. This section explains why it is expected to
   pass; it does not replace it.

---

## 10. MANDATORY execution path

Both clauses are requirements of this pre-registration, not recommendations. A run that skips either is
not evidence under this document.

### 10.1 Launch through `so battery-watch` (OMN-15588)

The battery is launched **only** through the supervised entrypoint documented at
`docs/runbooks/2026-07-28-hermetic-battery-snapshot-recipe.md` §5, with `--run-id`, `--raw-path`,
`--log-path`, `--expected-rows 61`, and `--stall-deadline-seconds`:

```bash
export STEEL_BATTERY_NOTIFY_COMMAND="<argv that reaches the operator; outcome JSON on stdin>"
# and/or: export STEEL_BATTERY_NOTIFY_WEBHOOK="<chat-compatible webhook URL>"
```

**At least one active channel is mandatory: with neither set, `battery-watch` exits 4 and never
launches the driver.** That refusal is the mechanism — a battery whose only failure signal is a file on
disk cannot be started through this path at all. The four terminal states (`COMPLETED` 0 /
`INCOMPLETE` 2 / `CRASHED` 1 / `STALLED` 1; exit 3 if no channel accepted the outcome) are recorded
verbatim in the evidence per AC7.

**Disk sentinels are prohibited.** Do not reintroduce a `BATTERY_DONE` / `NEEDS_ATTENTION` shell
wrapper — `tests/battery/test_watchdog.py` reads the runbook and fails if the bash sentinel recipe
returns to it. The reason is on the record: on the OMN-15488 run an attempt-1 crash sat undetected for
roughly **five hours** behind a correctly written sentinel that nobody read.

Two operational traps carried forward from the runbook, both load-bearing: `</dev/null` on stdin (an
inherited terminal stdin has repeatedly caused double-launch races), and `pgrep -f` before **any**
relaunch against a `--state-root` an existing process may still own — a relaunch onto a live state-root
is a silent data race on `battery_raw.jsonl` / `events.sqlite3`.

### 10.2 Build the snapshot via the amended hermetic runbook, including the OMN-15582 `--no-deps` step

The mandated execution environment is the hermetic snapshot per
`docs/runbooks/2026-07-28-hermetic-battery-snapshot-recipe.md`. Its **§3 is mandatory and was the gap
that cost the red lane two failed launch attempts** (OMN-15582): a plain `uv sync` produces an
`omnibase_infra` venv whose co-installed `omnimarket` is a non-VCS install, which the delegation CLI's
drift guard refuses at runtime. A full-resolve `uv pip install "omnimarket @ git+...@<pin>"` **cannot**
succeed — `omnimarket` → `omninode-memory` carries conflicting transitive git URLs for
`omnibase-infra`. The working recipe is the `--no-deps` install:

```bash
cd "$SNAP/omnibase_infra" && env -u PYTHONPATH uv pip install --python .venv/bin/python --no-deps \
  "omnimarket @ git+https://github.com/OmniNode-ai/omnimarket.git@<pin>"
```

**The verification, not the exit code, is the gate:** assert `direct_url.json` shows
`vcs_info.vcs == "git"` **and** `vcs_info.commit_id == <pin>`.

Also carried from the runbook: run with `OMNI_HOME="$SNAP"` so the drift belt compares the frozen
snapshot's own install against the frozen snapshot's own clone; and never run
`scripts/check-omnimarket-venv-drift.sh` (or anything doing a live fetch / `ls-remote`) against a
hermetic snapshot — it false-positives by design, because the snapshot is meant to sit pinned behind
the remote for the run's duration.

---

## 11. Cost estimate

**Derived from the OMN-15488 `_r2` run's own artifacts**, because the cited source does not carry the
figures — see the residual immediately below.

| Item | Basis | Estimate |
|---|---|---|
| Battery wall time | 61 `match_started` events spanning 2026-07-31T07:50:26Z → 12:58:04Z (queried from `events.sqlite3`, red acceptance document §4) = 5h07m38s | **~5.1 h**, ≈ 5.0 min/match |
| Delegation completions | 1499 requested lane-wide on `_r2` (750 baseline + 30 promote + 719 post; red acceptance document §4) | **~1,500**, ≈ 24.6/match |
| Canary (n=2) | observed 9 min warm / 29 min cold on the red lane's attempts 5 and 4 | **~10–30 min** |
| Snapshot build + pin verification | runbook §1–§3, idempotent on re-runs | **~10–20 min** |
| **Total endpoint occupancy** | | **~5.5–6 h**, unattended |
| Marginal monetary cost | local MLX (`stickybeatz-studio:8401`); no metered API | **$0** — the real cost is exclusive occupancy of that endpoint |

**Residual — a documentation claim that does not check out, flagged rather than papered over.**
Ruling 25's Linear comment on OMN-15488 and `docs/plans/ROLLING_SEVEN_DAY_PLAN.md` (§3a ruling-25 row
and WS-3 item 6) both state that *"per-leg costs live on OMN-15488's completion comment."* All comments
on OMN-15488 were read on 2026-07-31; **no comment on that ticket carries a cost figure of any kind**
— the closest is the completion comment (`bd2406cc`), which records acceptance gates, scoring, and
follow-ups, but no cost. The estimate above is therefore derived from the run's measured artifacts
instead. The plan's pointer should be corrected or the costs recorded where it says they are.

*(Minor internal inconsistency noted in passing, not resolved here: the red acceptance document §2
reports a `BATTERY_DONE` sentinel mtime of "Jul 31 06:03–06:05 local," which does not reconcile with a
last `match_started` of 12:58:04Z under any plausible local offset. The ledger-derived window is the
better-sourced figure and is what §11 uses.)*

---

## 12. Pre-registration of record, and the AC1 seam this document creates

`scripts/check_preregistration_timing.py` reads the **executing overlay file's** latest commit author
timestamp and compares it against the first `match_started`. It does **not** read this document.

Therefore, before launch, the launch session must:

1. Embed §2 through §7 of this document **verbatim** into the header of
   `contracts_data/overlays/tactical_split_overdeal_v1_delegation_learning_blue.yaml`, and land that
   commit.
2. Land any execution-infrastructure amendment as a **dated, numbered amendment appended to that same
   header**, before the first scored match — never as a silent edit, and never touching a criterion
   region (hypothesis, endpoints, bands, escapes, interpretation map).
3. Run AC1 against the executing state-root and record the exit-0 output and the margin verbatim.
4. Cross-check AC1 against the overlay's **full** commit ancestry, not just the script's single-commit
   output — the red lane's margin was 10m 43s and the ancestry cross-check is what made a thin margin
   trustworthy.

This is an **added obligation**, not a substitute for the gate. If the overlay header and this document
ever disagree, **the overlay header is the pre-registration of record** and the disagreement is itself
a reportable defect.

---

## 13. Limitations, collected in one place

- **Power.** n=30/phase, one-sided Welch, alpha 0.05 → ~80% power at `d ≈ 0.65`; the historically
  observed vent effects on this seat sit below that floor. DIRECTIONAL-ONLY is the modal expectation
  (§5).
- **Sequential, non-interleaved phases** on one MLX endpoint process; between-phase endpoint drift is
  unclosable from these artifacts (§7.3.6).
- **Delegation-binding fidelity gaps** (no `temperature` forwarding, collapsed system/user prompt,
  `json_mode` as prompt text) are held constant within the battery but make its absolute levels
  incomparable to #126/#128's HTTP-binding numbers (§7.3.2).
- **Attack keep-rate is likely ceilinged in both phases**, constraining what the primary can express
  (§6.2).
- **Stalemate risk in an unflown sniper mirror** — bounded, not eliminated, by §6.3.
- **The comparison to #126/#128 crosses step, genesis, and binding** and is not a clean step-size test
  (§7.3.2).
- **One model, one arena/loadout pairing, one seed set, one binding, card mode only.**
- **Leg (a) is not terminal for the prompt-guidance mechanism under ruling 25**, whatever it finds
  (§7.3.1).

---

## Citations

- **Ruling 25:** operator, 2026-07-31 ~17:00Z; recorded on OMN-15488 (Linear comment `3df7e451`),
  `docs/plans/ROLLING_SEVEN_DAY_PLAN.md` §3a and WS-3 item 6, and the rolling work ledger 17:05Z entry.
- **Red leg evidence pair:** `docs/evidence/2026-07-31-lgate2-decisive-battery-acceptance.md` (ACCEPT;
  AC1/AC2/AC3/AC6 PASS) and `docs/evidence/2026-07-31-lgate2-decisive-battery-scoring.md`
  (`D_ws = -0.003425` NOT-SUPPORTED; `D_vent = +0.019604`, `p = 0.070` DIRECTIONAL-ONLY; §5.1's
  seat/persona caveat; §4.2's raw-computed vent shares).
- **Prior batteries:** `docs/evidence/2026-07-22-lgate2-adaptation-battery.md` (#126);
  `docs/evidence/2026-07-22-lgate2-significance-battery.md` (#128, **including its 2026-07-31 OMN-15489
  correction**, which supersedes pre-registered limit B4 — RUN B's duel gate was a structural zero, not
  a swamped signal, and RUN B's numbers are evidence of nothing about `vent_at_heat_margin`).
- **Red pre-registration of record:**
  `contracts_data/overlays/tactical_split_overdeal_v1_delegation_learning.yaml` header
  (`ff5df34` #235, `4bae73e` #239, `a3b0d8a` #240).
- **Driver:** `scripts/run_lgate2_adaptation_battery.py`. **Gates:**
  `scripts/check_preregistration_timing.py`, `scripts/check_contamination_gate.py`.
- **Runbook:** `docs/runbooks/2026-07-28-hermetic-battery-snapshot-recipe.md` §3 (OMN-15582 `--no-deps`
  VCS install), §5–§6 (OMN-15588 supervised launch and terminal states).
- **Source read for §9:** `src/steel_onslaught/match/runner.py` (`:523`, `:539`, `:551`, `:623`,
  `:1046`, `:1071`), `src/steel_onslaught/match/duel.py` (`:94`, `:127`),
  `src/steel_onslaught/match/composition.py` (`:395`, `:1656`),
  `src/steel_onslaught/contracts/application.py` (`:185`),
  `contracts_data/overlays/tactical_split_overdeal_v1_delegation_learning.yaml` (`:474`) — all at
  `origin/main` `d78094a`.
- **Source read for FD5:** `src/steel_onslaught/cards/pilot_policy.py` (`:287-306`),
  `src/steel_onslaught/match/composition.py` seat-rule binding block, commit `f1e6a07` (#248).
- **Tickets:** OMN-15488 (this lane), OMN-15489 (duel-gate causal bypass — hard gate on leg (b)),
  OMN-15582 (runbook VCS step), OMN-15587 (share denominator), OMN-15588 (supervised watchdog),
  OMN-15591 (card-round replay validation — disposed for leg (a) in §9, open for leg (b)),
  OMN-15482 (delegation backend-coverage / fidelity gaps).

*No figure in this document is asserted from an agent self-report: every number is either quoted from a
merged evidence document with its section named, or read from source at a named path and line at
`origin/main` `d78094a`. This document authorizes no run.*

---

## Amendments

Amendments are appended, dated, and numbered, per §12 clause 2. They are landed on the executing
overlay's header (the pre-registration of record) and mirrored here so the two surfaces agree —
§12 makes a header/document disagreement a reportable defect. **The §2–§7 text above is unchanged
by any amendment**; an amendment that needed to edit a criterion region would not be an amendment.

### Amendment 1 (2026-07-31, before any match of this battery exists) — §7.1 INTERPRETATION-MAP ROW PRECEDENCE

**The defect.** §7.1 is a five-row table whose rows OVERLAP, and it states no rule for which row
governs when two match. A run with primary SUPPORTED and vent DIRECTIONAL-ONLY matches both row 1
(`SUPPORTED | any`) and row 4 (`any | DIRECTIONAL-ONLY`), and those rows give opposite readings —
row 1 says the L-GATE-2 behavioral half PASSES at this operating point, row 4 says the result is
unresolved and no terminal/non-terminal call may be made from it. Left as written, the scoring
session picks one after seeing the data, which is exactly the discretion a pre-registration exists
to remove.

**Why this is a restoration, not a new rule.** The red battery's pre-registration (quoted verbatim
in `docs/evidence/2026-07-31-lgate2-decisive-battery-scoring.md`, §"PRE-DECLARED INTERPRETATION
MAP") had no such ambiguity because it was not a table: it was three NAMED rows followed by a
CLOSING clause — *"DIRECTIONAL-ONLY outcomes -> reported as unresolved; the terminal/non-terminal
call is NOT made from an unresolved band."* The red scoring document applied precisely that
structure to its own NOT-SUPPORTED / DIRECTIONAL-ONLY result: *"none of the three named rows apply
and the closing clause governs."* Reformatting into a flat table silently dropped the ordering that
made the map decidable.

**The clause, restored.** Read §7.1's rows **in table order; the FIRST row whose bands both match
the scored result governs, and no later row is consulted.** Rows 4 and 5 are therefore residual
clauses, exactly as the red pre-registration's closing clause was.

**All nine cells, resolved:**

| primary | vent | governing row | reading |
|---|---|---|---|
| SUPPORTED | CONFIRMED | 1 | behavioral half PASSES at this operating point |
| SUPPORTED | DIRECTIONAL-ONLY | 1 | behavioral half PASSES at this operating point |
| SUPPORTED | NOT-CONFIRMED | 1 | behavioral half PASSES at this operating point |
| NOT-SUPPORTED | CONFIRMED | 2 | semantics are the defect, not the learning chain |
| NOT-SUPPORTED | NOT-CONFIRMED | 3 | H_POLICY_INERT; with the red leg, the symmetric null |
| NOT-SUPPORTED | DIRECTIONAL-ONLY | 4 | unresolved |
| DIRECTIONAL-ONLY | CONFIRMED | 5 | unresolved |
| DIRECTIONAL-ONLY | DIRECTIONAL-ONLY | 4 | unresolved |
| DIRECTIONAL-ONLY | NOT-CONFIRMED | 5 | unresolved |

Row 1 covering all three vent bands is not an artefact of ordering — it is what `SUPPORTED | any`
already says, and it matches the red pre-registration's own first row (*"primary SUPPORTED (any
vent outcome)"*). The red leg's actual scored cell (NOT-SUPPORTED / DIRECTIONAL-ONLY) resolves to
row 4 = unresolved, which is verbatim the call its scoring document made. The clause changes no
band, no endpoint, no direction, no alpha, no escape, and no cell's reading; it removes only the
discretion to choose between two rows after seeing which is more convenient.

### Amendment 2 (2026-07-31, before any match exists) — the executing command, completed

Execution-infrastructure only; no criterion region is touched. Full text in the overlay header;
the procedure it pins is `docs/runbooks/2026-07-31-lgate2-legA-blue-seat-launch.md`. Summary:

1. **§2.1 FD3 / §3's seed blocks were unreachable.** `scripts/run_lgate2_adaptation_battery.py`
   hardcoded base `4000` three times inline. It now takes `--seed-base` (default 4000, byte-identical
   to every prior invocation); leg (a) passes `--seed-base 6000`, yielding exactly 6001–6030 /
   6101–6115 / 6201–6230, and the executed base is published into `battery_summary.json`.
2. **§10.1's `--expected-rows 61` was wrong for 14 of the 15 possible clean outcomes.** The promote
   phase stops at the first promotion, so a clean run writes `30 + k + 30` rows for `k` in 1..15;
   the watchdog compared with a strict `!=`. `so battery-watch` now takes `--expected-rows-max`, and
   leg (a) launches with the derived `61`–`75`. The §6.1 NO-PROMOTION escape does not hide inside
   that range: a no-promotion run exits nonzero and surfaces as CRASHED.
3. **§6.3's canary decisiveness clause had no checker.** `scripts/check_canary_decisiveness.py` now
   decides all three clauses and fails closed on missing evidence. The canary flies `--seed-base 9100
   --n 2 --promote-attempts 0` — exactly the pre-registered canary seeds 9101/9102, and exactly two
   matches, creating no policy lineage.

**Landing these amendments authorizes no run.** Leg (a) starts only when an operator says so.
