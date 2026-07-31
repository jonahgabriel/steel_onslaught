# SO-REDMID — RED MID-RANGE OPTION — PRE-REGISTRATION — 2026-07-31

> **LAUNCH IS SERIALIZED AFTER OMN-15488 LEG (a). THIS DOCUMENT AUTHORIZES NO RUN.**
> The operator ruling that signed this design off also fixed its ordering: leg (a) (the blue-seat
> endpoint-contrast replication, pre-registered at
> `docs/evidence/2026-07-31-lgate2-legA-blue-seat-endpoint-contrast-prereg.md`, merged as #249) launches
> first and SO-REDMID launches only after it. Landing this document creates a pre-registration of record
> and nothing else. It starts no battery, reserves no MLX endpoint, changes no packaged default, and
> pre-approves no launch.

**Ticket:** OMN-15586 (parent: OMN-15154). **Authoring session:** `fable-steel-0731` wave-4.
**Repo state at authoring:** `jonahgabriel/steel_onslaught@ea20e67` (`origin/main`).

---

## 0. What this document is, and what it is not

**It is:** the hypothesis, the arms, the endpoint definitions with their denominators, the decision
rule, the seeds, the escapes, the interpretation map, the acceptance gates, the arm-legality record,
and the mandatory execution path for the SO-REDMID battery — fixed before any data exists.

**It is not:** an executable artifact, and it is not a launch authorization. It also does not — by
deliberate choice, matching the leg-(a) precedent — author the overlay or loadout files the battery
will run against. Those are enumerated with their exact required contents in §11 and are the launch
session's setup work. The reason is mechanical: `scripts/check_preregistration_timing.py` reads the
**executing overlay file's** commit author timestamp, not this document's, so the overlay header is the
pre-registration of record for the timing gate (§12). Authoring the overlay in this lane and launching
weeks later would put a stale, un-amendable file in the timing gate's path.

**It changes nothing.** No packaged default, no `contracts_data` value, no existing weapon, loadout,
chassis, boiler, arena, or overlay file is modified by this lane. The `so play` watchable default
(`src/steel_onslaught/cli/play.py:1891`, `:1894`, `:1895`) is untouched, and changing it stays gated on
a SUPPORTED verdict **plus** a separate explicit operator decision (§8, §10).

### 0.1 Operator sign-off provenance

- **Design signed off:** operator ruling recorded 2026-07-31, verbatim *"go with your suggested
  approaches"*, against the pre-registration draft posted on OMN-15586 (Linear comment `7d593c9e`,
  2026-07-31T19:20:51Z). That draft's three arms, endpoint set, decision rule, and n=30/seeds
  5001–5030 design are what this document formalizes.
- **Launch ordering:** the same ruling serialized SO-REDMID **after** leg (a). This document may land;
  the battery may not start until leg (a) has run.
- **Deltas from the signed-off draft are named, not silently applied.** §2.4 records three corrections
  this document makes to the draft's own arithmetic and framing, each with the file-level evidence that
  forced it. A reviewer should read §2.4 before quoting the draft.

---

## 1. Ground truth — the arithmetic, verified in file at `ea20e67`

Every number in this section was read from a named file at `origin/main` `ea20e67`. Nothing here is
quoted from an agent summary.

### 1.1 The packaged watchable default pairing

| Seat | Loadout file | Chassis | Boiler | Weapons (range) |
|---|---|---|---|---|
| red | `contracts_data/loadouts/llm_qwen35_berserker.yaml` | `chassis.light.scout_mk1` | `boiler.compact.v1` | `machine_gun` (12), `shrapnel_thrower` (8) |
| blue | `contracts_data/loadouts/qwen35/sniper_ironclad.yaml` | `chassis.heavy.ironclad_mk1` | `boiler.industrial.bessemer_90` | `artillery_mortar` (50), `harpoon_gun` (30) |

Bound as the zero-configuration defaults at `cli/play.py:1894` and `:1895`; default overlay
`contracts_data/overlays/tactical_split_v1_qwen.yaml` (`:1891`), arena `foundry_60`.

Chassis constraints (`contracts_data/chassis/light_scout_mk1.yaml`,
`contracts_data/chassis/heavy_ironclad_mk1.yaml`):

| | red scout_mk1 | blue ironclad_mk1 |
|---|---:|---:|
| `base_hp` | 60 | 160 |
| `base_armor` | 6 | 16 |
| `base_speed` | 6 | 2 |
| `heat_weapon_vulnerability` | 1.1 | **1.3** |

### 1.2 The range asymmetry, stated exactly

Red's longest weapon reaches 12; blue's reaches 50. `validate_weapon_fire_intent`
(`src/steel_onslaught/reducers/weapons.py:101-134`) raises `target_out_of_range` when
`distance > weapon_range`, so on the interval 12 < d ≤ 50 blue can fire and red mechanically cannot.

The operator's live-play report (*"the only time I saw fire from red was right on top of blue"*) is
quantified on the ticket from match `match.072B7ENH0S9NE8PEG5JRBN7HX6`: `weapon_fire_intent` 63,
`weapon_fire_rejected` **39**, `weapon_fired` 24 — a 61.9% pooled rejection rate; red `damage_dealt` 0,
blue `damage_dealt` 32, blue victory by elimination. **Provenance label:** those five figures are
quoted from the OMN-15586 triage comment and were **not** re-read from a ledger by this lane — that
match's `.onex_state` artifacts are not on `origin/main`. They motivate SECONDARY 1's definition; no
band in §5 depends on them.

### 1.3 The damage arithmetic — and why the ticket's "range asymmetry" framing is incomplete

The damage chain is `runner.py:1516-1538`: `damage_raw = int(damage × target_class_effectiveness)` →
armor absorption capped by damage type (`reducers/damage.py:45-49`, `:117-124`; HEAT 0.50 / STANDARD
0.75 / PRESSURE 0.90) → `int(after_armor × heat_weapon_vulnerability)` **only** when
`damage_type is HEAT` (`reducers/damage.py:127-150`).

Per-hit effective damage **at full armor**, computed by hand through that exact chain:

| Weapon | vs | raw | armor absorbed | vulnerability | **effective** |
|---|---|---:|---:|---:|---:|
| `machine_gun` (STANDARD, 8, heavy 0.7) | blue ironclad, armor 16 | `int(5.6)`=5 | `min(16, ceil(3.75))`=4 | — | **1** |
| `shrapnel_thrower` (STANDARD, 12, heavy 0.6) | blue ironclad, armor 16 | `int(7.2)`=7 | `min(16, ceil(5.25))`=6 | — | **1** |
| `heat_lance` (**HEAT**, 18, heavy 1.0) | blue ironclad, armor 16 | `int(18.0)`=18 | `min(16, ceil(9.0))`=9 | ×1.3 → `int(11.7)` | **11** |
| `artillery_mortar` (STANDARD, 45, light 0.9) | red scout, armor 6 | `int(40.5)`=40 | `min(6, ceil(30.0))`=6 | — | **34** |
| `harpoon_gun` (STANDARD, 28, light 0.8) | red scout, armor 6 | `int(22.4)`=22 | `min(6, ceil(16.5))`=6 | — | **16** |

Two consequences, both load-bearing for how this battery must be read:

1. **Red's entire packaged kit does 1 effective damage per hit to blue at full armor**, against blue's
   160 hp. Blue kills red in **two** mortar hits (34 + 34 ≥ 60). The engagement-envelope asymmetry the
   ticket names is real, but it is **not the only binding constraint** — even a red that closes to
   contact is doing 1/160 per hit until blue's armor is chewed down. Any reading of this battery that
   attributes an A1 effect to "range" alone is unsupported by the arithmetic above.
2. **`heat_lance` is not a range variant of red's existing weapons.** It changes range (8 → 20), damage
   type (STANDARD → **HEAT**, which halves the armor mitigation cap *and* switches on blue's ×1.3
   vulnerability), class effectiveness vs heavy (0.6 → 1.0), damage (12 → 18), cooldown (2 → 2, equal),
   pressure (6 → 8), and heat (5 → **18**). At full armor it is an **11× per-hit upgrade** against blue.
   This is pre-registered here as a **multi-delta manipulation**, not a single-axis one (§2.3).

### 1.4 The heat cost of A1, computed against the automatic vent

`boiler.compact.v1` (`contracts_data/boilers/compact_v1.yaml`): `heat_capacity` 80, `redline_threshold`
65, `rupture_threshold` 80, `vent_rate` 6. `heat_vent_rate` is bound from that spec field
(`runner.py:1685`), and **venting is automatic on every `MATCH_TICK`** — `reducers/boiler.py:139`,
`new_heat = max(heat_current - heat_vent_rate, 0)` — not a programmed action. `WEAPON_FIRED` adds
`heat_generated` capped at rupture (`reducers/boiler.py:150-160`).

`BOILER_OVERLOADED` trips after **3 consecutive ticks** at `heat ≥ redline`
(`reducers/failure.py:86`, `:264-292`), applies a 0.2 accuracy penalty to the next shot and disables
mode switching for 3 ticks; rupture follows at `heat ≥ 80` or 5 consecutive overloaded ticks
(`reducers/failure.py:95`, `:298`). `BOILER_OVERLOADED` also carries a scoring penalty
(`reducers/scoring.py:14`, `:102`).

At `heat_lance`'s maximum cadence (`cooldown_ticks: 2`) the net is **+18 per shot against −6 per tick**,
i.e. **+6 per two-tick firing cycle** — roughly **11 consecutive maximum-cadence shots** from cold to
redline, not the "about three shots" the ticket draft estimated. The draft's estimate ignored the
automatic per-tick vent; §2.4 records the correction. The heat guardrail (§4) is retained anyway,
because a real overload would still confound a win-rate reading — but its prior of firing is
substantially lower than the draft implied, and that is stated in advance rather than discovered in the
scoring document.

---

## 2. Design — three arms

### 2.1 Arms

| arm | manipulation | seat changed | file discipline |
|---|---|---|---|
| **A0 CONTROL** | the packaged watchable default pairing, unchanged | — | no new contract file; binds the two shipped loadouts |
| **A1 RED-MID** | red `shrapnel_thrower` (r8) → `heat_lance` (r20). `machine_gun` untouched. | red | **new** `contracts_data/loadouts/qwen35/berserker_midrange.yaml` (§11.1) |
| **A2 BLUE-CAP** | blue `artillery_mortar` (r50) → `artillery_mortar_r15` (r15). `harpoon_gun` untouched. | blue | **no new file** — `contracts_data/loadouts/qwen35/sniper_ironclad_mortar_r15.yaml` already exists (§2.2) |

**Additive-only, new files never edits.** No existing weapon, loadout, chassis, boiler, arena, or
overlay file is modified, so every historical replay stays valid. This is the same discipline the
SO-RANGECAP arm used (`contracts_data/weapons/artillery_mortar_r15.yaml` header).

A2 is in the design because it is the *other* lever the ticket names, it is already authored and
merged, and it separates "shrink blue's envelope" from "extend red's" — two different design answers to
one complaint.

**Deliberately no dose ladder.** Three corners, one question. The P1–P7 dose sweep is the cautionary
precedent (§8).

### 2.2 A2 needs no new contract file — verified by diff

`contracts_data/loadouts/qwen35/sniper_ironclad_mortar_r15.yaml` differs from the packaged
`qwen35/sniper_ironclad.yaml` in exactly two lines (`diff` of both files with comments stripped, run at
`ea20e67`): the `id`, and `weapon.siege.artillery_mortar` → `weapon.siege.artillery_mortar_r15`.
Chassis, boiler, pilot, `harpoon_gun`, both sensors, both gizmos, and the whole `budgets` block are
byte-identical.

And `artillery_mortar_r15.yaml` differs from `artillery_mortar.yaml` in exactly three lines: `id`,
`display_name`, and `range: 50 → 15`. `damage`, `pressure_cost`, `heat_generated`, `cooldown_ticks`,
`accuracy_curve`, `target_class_effectiveness`, `damage_type`, and `compatibility` are byte-identical.

**So A2 is a genuine single-axis range manipulation and A1 is not.** That asymmetry is the single most
important thing to carry into the interpretation map (§7).

Note on the accuracy curve: `artillery_mortar_r15`'s curve still starts at breakpoint `range: 20`, and
`reducers/weapons.py::interpolate_accuracy` clamps to the first breakpoint below it (0.80), so cutting
range to 15 changes **whether** a shot is legal, not its hit probability once legal. That property was
established and relied on by the SO-RANGECAP arm and is inherited here unchanged.

### 2.3 A1 is a multi-delta manipulation — pre-registered as such

Per §1.3, swapping `shrapnel_thrower` → `heat_lance` moves six weapon fields at once (range, damage
type, class effectiveness vs heavy, damage, pressure cost, heat), and the damage-type move alone
triggers two engine paths (`_MITIGATION_CAP` 0.75 → 0.50 and blue's `heat_weapon_vulnerability` 1.3).

**This is not a defect in the arm; it is what "give red a mid-range option" means as a product change.**
But it fixes what A1 can conclude: A1 answers *"does giving red this specific mid-range weapon make the
default pairing competitive/watchable?"* It does **not** answer *"is engagement-envelope asymmetry the
binding constraint?"* — A2 is the arm that speaks to that, and even A2 speaks only about blue's mortar.

A single-axis red-range arm (a `shrapnel_thrower_r20` variant with every other field held) is the clean
counterfactual and is **explicitly out of scope here**, recorded in §2.5 so it is not silently
revisited or silently assumed to have been run.

### 2.4 Corrections to the signed-off draft, each with its evidence

The operator signed off *"go with your suggested approaches."* Three statements in the draft do not
survive a file-level re-read, and applying them silently would put wrong numbers in a pre-registration:

1. **`heat_lance` chassis compatibility.** The draft said `compatible_chassis_classes: [light, medium]`.
   The file says **`[light, medium, heavy]`** (`contracts_data/weapons/heat_lance.yaml`, the
   `compatibility` block). The legality conclusion is unchanged (light is in both readings) — but §3
   records the value that is actually in the file.
2. **"About three shots to redline."** Corrected to **~11 maximum-cadence shots**, because the draft's
   estimate ignored the automatic per-tick vent at `reducers/boiler.py:139` (§1.4).
3. **"A1 is a range manipulation."** Corrected to a **six-field multi-delta** manipulation whose largest
   single effect is plausibly the damage-type switch, not the range extension (§1.3, §2.3). The draft's
   own framing — that this arm "tests the residual [range] hypothesis directly" — is **withdrawn** and
   replaced by §7's interpretation map.

None of these changes an arm, an endpoint, a band, a seed, or n. They change what the result may be
said to mean, which is exactly what a pre-registration is for.

### 2.5 Rejected alternatives, recorded so they are not silently revisited

- **A single-axis red-range variant (`shrapnel_thrower_r20`: range 8 → 20, every other field held).**
  This is the clean test of the ticket's stated hypothesis, and it is a strictly better *scientific*
  arm than A1. **Rejected for this battery** because the operator's ask is a *watchable default*, and a
  weapon that reaches 20 while still doing 1 effective damage per hit to blue (§1.3) would very likely
  produce a red that shoots and still never wins — answering the science while leaving the product
  complaint exactly where it is. It remains available as its own arm under its own pre-registration and
  is the natural follow-up to an A1 SUPPORTED verdict (§7.3).
- **Pricing a new mid-range weapon under the OMN-15250 points program.** Rejected as a dependency:
  `heat_lance` already exists and is already legal on the scout (§3), so this battery needs no pricing
  and is not blocked behind OMN-15250 (which is itself queued behind OMN-15172 acceptance and the AI4
  freeze).
- **Changing the packaged default on face validity, without a battery.** Rejected as the *default* path
  — but it is a live operator option and it is stated as such in §10, because "red visibly shoots" may
  be the actual product goal and it does not require a win-rate result.

---

## 3. ARM-LEGALITY HAND-CHECK RECORD (OMN-15594) — mandatory, because nothing enforces this

**OMN-15594: weapon/chassis compatibility is declared in three places and consumed in none.** Verified
at `ea20e67` by exhaustive grep over `src/`:

- `contracts/weapon.py:54` — `compatible_chassis_classes: tuple[str, ...]`, declaration only.
- `contracts/boiler.py:21` — `compatible_chassis_classes: tuple[str, ...]`, declaration only.
- `contracts/chassis.py:37` — `weapon_classes: tuple[str, ...]` (inside `ModelSOChassisCompatibility`,
  referenced at `:80`), declaration only.
- `grep -rn "compatible_chassis_classes" src/` returns **exactly those two definition sites** and no
  consumer. `grep -n "weapon_classes" src/steel_onslaught/contracts/chassis.py` returns the definition
  and nothing else.
- `EnumBudgetViolationKind` (`contracts/budget.py:36-41`) is `MASS | SLOTS | PRESSURE` — there is no
  compatibility violation kind, and `validate_loadout_budgets` (`contracts/budget.py:118-173`) checks
  only those three axes.

**Therefore an illegal weapon/chassis pairing runs silently, produces a plausible-looking battery, and
is invisible in the output.** The hand-check below is the only thing standing between this battery and
a non-comparable run. It is recorded now, pre-registration, and **must be re-run and re-recorded by the
launch session against the executing pin** (§11.4) — a later commit could change a compatibility field
without any test failing.

### 3.1 A1 red loadout — `scout_mk1` + `compact.v1` + [`machine_gun`, `heat_lance`] + `short_range_scanner`

| # | Axis | Value read | Source | Verdict |
|---|---|---|---|---|
| 1 | `heat_lance.weapon_class` ∈ `scout_mk1.compatibility.weapon_classes` | `medium` ∈ `[light, medium]` | `weapons/heat_lance.yaml`; `chassis/light_scout_mk1.yaml` | **LEGAL** |
| 2 | `scout_mk1.chassis_class` ∈ `heat_lance.compatibility.compatible_chassis_classes` | `light` ∈ `[light, medium, heavy]` | same two files | **LEGAL** |
| 3 | `machine_gun.weapon_class` ∈ chassis weapon classes | `light` ∈ `[light, medium]` | `weapons/machine_gun.yaml` | **LEGAL** (unchanged from control) |
| 4 | `scout_mk1.chassis_class` ∈ `machine_gun` compatible classes | `light` ∈ `[light, medium]` | same | **LEGAL** (unchanged) |
| 5 | `scout_mk1.chassis_class` ∈ `compact.v1.compatibility.compatible_chassis_classes` | `light` ∈ `[light, medium]` | `boilers/compact_v1.yaml` | **LEGAL** (unchanged) |
| 6 | boiler class ∈ `scout_mk1.compatibility.boiler_classes` | `compact` (from `boiler.compact.v1`) ∈ `[compact, volatile]` | both files | **LEGAL** (unchanged) |

**Axes 1–6 are all unenforced.** Each was evaluated by hand against the two files named.

### 3.2 A1 red loadout — the three axes that ARE enforced

Normalization conventions read at `match/runner.py:1780-1840` (`_module_budgets`): a weapon contributes
`mass=0`, `slots=1`, `pressure_draw=0.0`, `heat_output=heat_generated`, active in `assault`; a sensor
contributes `mass=0`, `slots=1`, its `pressure_draw_per_tick` / `heat_per_tick` / `signature_impact`,
active in all modes; a gizmo contributes its contract mass/slots. Thresholds from
`contracts/budget.py:145-172`.

| Axis | A1 computed | Limit | Verdict |
|---|---:|---:|---|
| MASS | 0 (weapons and sensors are mass 0; red fields no gizmos) | `scout_mk1.max_mass` 60 | **PASS**, identical to control |
| SLOTS | 2 weapons + 1 sensor = **3** | `scout_mk1.max_module_slots` 4 | **PASS**, identical to control |
| PRESSURE (steady state) | weapons 0.0 + `short_range_scanner.pressure_draw_per_tick` 2.0 = **2.0** | `compact.v1.pressure_capacity` 50 × `PRESSURE_HEADROOM_FRACTION` 0.7 = **35.0** | **PASS**, identical to control |

**Non-gating, recorded for completeness:** `expected_heat_peak` in assault mode rises from
`3 + 5 + 0.5 = 8.5` (control) to `3 + 18 + 0.5 = 21.5` (A1). It is computed
(`contracts/budget.py:87-116`) but is **not** a `EnumBudgetViolationKind` member, so it cannot reject a
loadout. It stays under the loadout's declared `expected_heat_peak: 30` either way; §11.1 requires the
declared `budgets` block to be copied byte-identically from the baseline and this fact recorded in the
new file's header, rather than a new number being invented.

### 3.3 A2 blue loadout — `sniper_ironclad_mortar_r15`

| # | Axis | Value read | Verdict |
|---|---|---|---|
| 1 | `artillery_mortar_r15.weapon_class` ∈ `ironclad_mk1.compatibility.weapon_classes` | `siege` ∈ `[light, medium, heavy, siege]` | **LEGAL** |
| 2 | `ironclad_mk1.chassis_class` ∈ `artillery_mortar_r15` compatible classes | `heavy` ∈ `[heavy]` | **LEGAL** |
| 3 | MASS / SLOTS / PRESSURE | byte-identical to the packaged sniper loadout (§2.2 diff); the swap changes only `range`, which feeds no budget axis | **PASS** |

A2's legality is additionally corroborated by the fact that this exact loadout already flew a merged
30-seed battery (`docs/evidence/2026-07-25-rangecap_r15_dmg16-battery.md`).

### 3.4 A0 control

Legality inherited unchanged — A0 is the shipped default pairing, verified above at axes 3–6 (red) and
by construction (blue).

---

## 4. Endpoints, with their denominators declared

All figures are computed from `$ROOT/battery_raw.jsonl` and `$ROOT/events.sqlite3` (opened read-only /
`immutable=1`). `battery_summary.json` is **not** a source for any scored figure — it is a cross-check
only. This matches the OMN-15488 red battery's discipline and is what kept that battery's findings
intact when the share-denominator defect was found (§4.6).

### 4.1 PRIMARY — red win rate

Per arm, red wins ÷ **decided matches** (terminal class `elimination`; aborts excluded from the
denominator and never counted as wins). The all-match basis (n=30 denominator, aborts in the
denominator, not wins) is reported alongside it, per the P1–P7 / SO-RANGECAP convention, and the
scoring document must report **both** bases and state which one the band was evaluated on.

```
Δ = p(A1) − p(A0)
```

tested with a **two-proportion z**, two-sided, alpha = 0.05.

**Denominator escape, pre-declared:** SO-RANGECAP's criterion was written as an integer win count on an
assumed zero-abort denominator, then met one abort and had to be scored three ways after the fact. This
document therefore fixes the denominator **as a proportion on the decided basis**, states the
all-basis figure as a required companion, and pre-commits that **if the two bases fall on opposite
sides of the band, the arm is scored DIRECTIONAL-ONLY** and the discrepancy is reported. That rule
exists so no post-hoc reading is available.

### 4.2 SECONDARY 1 — red fire-rejection ratio

Per arm, pooled over the arm's matches:

```
rejection_ratio = count(weapon_fire_rejected | red) / count(weapon_fire_intent | red)
```

from `events.sqlite3` event types `weapon_fire_rejected` / `weapon_fire_intent`
(`events/envelope.py:32`, `:47`). **This is the operator's complaint made numeric.** The per-match
distribution is also reported (mean and median over the matches with `weapon_fire_intent > 0`), and the
count of matches excluded for a zero intent denominator is stated explicitly — never silently dropped.

**Rejection reasons must be broken out**, not pooled: `validate_weapon_fire_intent`
(`reducers/weapons.py:101-134`) raises four distinct stable codes — `insufficient_pressure`,
`weapon_on_cooldown`, `target_out_of_range`, `target_not_alive`. Only `target_out_of_range` speaks to
the engagement envelope. A rejection-ratio move driven by `insufficient_pressure` (plausible: A1 raises
pressure cost 6 → 8) would be a different mechanism wearing the same number, and the pre-registered
reading requires the `target_out_of_range` component specifically.

### 4.3 SECONDARY 2 — time to red's first shot

Per match, the tick of red's first `weapon_fired` event; reported per arm as a **median over the
matches in which red fired at all**, with the count of matches where red never fired stated explicitly
as a separate figure (it is not an infinity to be imputed, and it is not a zero). This is the direct
measure of "red spends the match closing under fire."

### 4.4 SECONDARY 3 — red damage dealt

Per match, red's total `damage_dealt`; reported per arm as a **median over all 30 flown matches**,
including zeros (a match where red dealt no damage is a real 0, not a missing value). Mean and the
count of exact zeros are reported alongside.

### 4.5 GUARDRAIL — red boiler overload

Per arm, total `boiler_overloaded` events attributed to red (`events/envelope.py:43`), reported as a
count and as a per-match mean **over all 30 flown matches**. §5's decision rule uses it as a veto: an
arm that buys a win-rate gain with an overload explosion has traded a range problem for a heat problem
and is not the mechanism under test.

### 4.6 Denominator semantics (OMN-15587) — and the scope limit nobody should assume away

**The defect.** OMN-15587 (fixed at `630ce08`, #243) found that `mean_planned_share[c]` was averaged
over only the rows whose `planned_share` dict carried key `c`, so a category that was dealt and never
programmed dropped out of the **denominator** instead of contributing an explicit `0.0`. On the merged
OMN-15488 battery that inflated `vent` **15.4×** (0.0154 over 2 present rows vs 0.0010 over the 30
flown) and **6.0×** (0.0223 over 5 vs 0.0037 over 30). The fix keys the row over `dealt | planned`,
reserves `None` for the genuinely undefined 0/0 case, and publishes `planned_share_matches` so the
denominator is falsifiable from the artifact alone.

**The scope limit, stated because it is easy to get wrong.** That fix landed in
`scripts/run_lgate2_adaptation_battery.py` **only**. SO-REDMID runs on
`scripts/run_ogate_objectives_battery.py`, which emits no `mean_planned_share` and no
`planned_share_matches` at all (`grep -n "planned_share" scripts/run_ogate_objectives_battery.py`
returns nothing at `ea20e67`). **SO-REDMID therefore inherits none of OMN-15587's protection**, and
quoting "#243 fixed the denominator" as if it covered this battery would be false.

**What this document does instead.** Every endpoint in §4.1–§4.5 names its denominator in its own
definition, and each names what happens to an undefined row:

| Endpoint | Denominator | Undefined rows |
|---|---|---|
| PRIMARY | decided matches (`elimination` terminals); all-match basis reported alongside | aborts excluded from decided basis, counted in all basis, never a win |
| SECONDARY 1 | pooled `weapon_fire_intent` events; per-match over matches with intent > 0 | zero-intent matches counted and reported, not silently dropped |
| SECONDARY 2 | matches in which red fired | never-fired matches counted and reported as their own figure |
| SECONDARY 3 | **all 30 flown matches** | a zero is a real 0 |
| GUARDRAIL | **all 30 flown matches** | a zero is a real 0 |

AC5 requires the scoring document to print each endpoint's denominator **as an integer next to its
value**. A share whose denominator is not printed is not acceptable evidence in this program.

### 4.7 Multiplicity, stated plainly

One gating endpoint (§4.1) plus three reported secondaries and one guardrail. **No family-wise
correction is applied**, the secondaries carry no p-values in the band, and the scoring document must
say so. The secondaries exist to say *what happened*, not to accumulate significance.

### 4.8 TERTIARY descriptives (reported, never gating)

Terminal-class mix and `play_terminal_fraction` per arm; match length distribution; blue's mirror
metrics for each of §4.2–§4.5; `failed_completions` distribution per arm (retry-belt health, not a
hypothesis metric); per-weapon `weapon_fired` / `weapon_fire_rejected` counts with reasons, which is the
engine-layer proof that the manipulation landed at all (AC4).

---

## 5. Decision rule, fixed before any run

Evaluated on the **decided basis** (§4.1), with the all-basis figure required alongside.

```
SUPPORTED         — Δ(A1 − A0) >= +0.15 absolute
                    AND two-proportion z gives p < 0.05 at n=30/arm
                    AND SECONDARY 2 (median time-to-first-shot) FALLS vs A0
                    AND GUARDRAIL: red boiler_overloaded count in A1 is NOT more
                        than 2x A0's count.

DIRECTIONAL-ONLY  — Δ > 0 but p >= 0.05, AND both SECONDARY 1 (rejection ratio,
                    target_out_of_range component) and SECONDARY 2 move as
                    predicted (rejection ratio DOWN, time-to-first-shot DOWN).
                    Also the forced verdict when the decided and all-match bases
                    fall on opposite sides of the band (§4.1).

NOT-SUPPORTED     — otherwise.
```

**A2 is scored on the same three bands against the same A0 control**, with `Δ(A2 − A0)` substituted
throughout. A2 has no separate guardrail: the manipulation is on blue's weapon and cannot raise red's
heat.

**A NOT-SUPPORTED result publishes as a finding.** If neither arm moves red's win rate, the conclusion
is that engagement-envelope manipulation of this magnitude is not sufficient at this pairing — a
genuinely informative negative against the P1–P7 residual hypothesis, consistent with OMN-15250 §0.1's
"the duel format itself is the problem, not any single lever inside it," and **the packaged default does
not change**. That is a real result, not a failed run.

**Power, declared before the run.** A two-proportion z at n=30/arm has roughly 80% power to detect a
shift from a 0.2 baseline to about 0.55, i.e. an absolute Δ near +0.35 — **more than twice the +0.15
band above.** So the SUPPORTED band as written is under-powered against its own threshold, and
**DIRECTIONAL-ONLY is the modal expectation for a real but moderate effect.** n is held at 30 to match
every prior arm in this family (P1–P7, SO-RANGECAP, SO-STANDOFF), which is what makes the cross-arm
comparison in §7.2 legible; raising n would improve this battery's own resolution at the cost of that
match, and that trade is named here rather than made silently. A DIRECTIONAL-ONLY outcome is a **power
statement, not evidence of absence**, and the scoring document must say so rather than upgrade or
downgrade the band.

---

## 6. Phases, seeds, caps

Three independent arms, each n=30, **same seed block in every arm** so the comparison is paired:

| arm | seeds | n | state root |
|---|---|---:|---|
| A0 CONTROL | 5001–5030 | 30 | `.onex_state/steel_onslaught/so_redmid_a0_control` |
| A1 RED-MID | 5001–5030 | 30 | `.onex_state/steel_onslaught/so_redmid_a1_heatlance` |
| A2 BLUE-CAP | 5001–5030 | 30 | `.onex_state/steel_onslaught/so_redmid_a2_mortar_r15` |

**On the seed block.** 5001–5030 is the balance program's block (`--seed-base 5000` is the O-GATE
driver's own default, `scripts/run_ogate_objectives_battery.py:508`), reused deliberately for a paired
comparison exactly as SO-RANGECAP reused P6's. This is the opposite of the leg-(a) convention, where
disjoint 6xxx blocks were chosen so cross-lane collision would be detectable — the two programs have
opposite requirements and this document takes the balance program's. Cross-arm isolation here is
provided by **disjoint state roots**, not disjoint seeds, and AC2 is written accordingly (§9).

`--max-ticks` stays the driver default of 1000 (clock failsafe only) and the value used is recorded
verbatim in the evidence. Both seats are live Qwen3.6-35B-A3B-8bit via `onex-local-coder-mlx`.

**Total: 90 matches across three arms.**

---

## 7. Pre-declared interpretation map

### 7.1 Within SO-REDMID

| A1 | A2 | reading |
|---|---|---|
| SUPPORTED | any | **this specific mid-range weapon** makes the default pairing competitive. Attribution to range specifically is NOT licensed (§2.3) — the follow-up is the single-axis `shrapnel_thrower_r20` arm (§2.5), which separates range from damage type. |
| NOT-SUPPORTED | SUPPORTED | red's problem is blue's envelope, and it is fixable from blue's side. The product answer is a range-capped blue default, not a new red weapon. |
| SUPPORTED | SUPPORTED | both directions work; the choice becomes a design/aesthetic call about which default is more watchable, not a measurement question. |
| NOT-SUPPORTED | NOT-SUPPORTED | envelope manipulation of this magnitude does not move this duel from either side. Read together with §1.3's damage arithmetic (red does 1 effective damage per hit to blue at full armor), the binding constraint is likely **damage throughput against a heavy chassis**, not range — a specific, testable successor hypothesis this battery would have earned. |
| DIRECTIONAL-ONLY | any | **unresolved.** No packaged-default change and no terminal call is made from an unresolved band. |

### 7.2 Against the existing arm family

SO-REDMID's A0 is the **packaged watchable default** pairing (berserker vs sniper on the shipped
loadouts). P1–P7 / SO-RANGECAP / SO-STANDOFF all ran a **dose-modified** red (`_dmg16`, `_dmg24`) on the
asym objective arena. A0 is therefore a **new control cell**, not a re-run of P6, and cross-arm
comparison to those batteries is **directional only** — absolute win rates are not comparable across
the two families. Only within-SO-REDMID contrasts (A1−A0, A2−A0) are scored.

### 7.3 What SO-REDMID cannot conclude — read this before quoting any result

1. **A1 cannot attribute an effect to range.** Six weapon fields move at once and the damage-type switch
   alone is an 11× per-hit change against blue at full armor (§1.3). Anyone who wants the range claim
   must run the single-axis arm in §2.5.
2. **A2's claim is about blue's mortar, not "blue's range."** `harpoon_gun` (range 30) is untouched, so
   blue's engagement envelope is cut to 30, not to 15. SO-RANGECAP made this same observation about its
   own arm and it applies here unchanged.
3. **No claim generalizes** beyond Qwen3.6-35B-A3B-8bit on `local-coder-mlx`, this arena/overlay, this
   loadout pairing, this seed set, and card mode.
4. **A SUPPORTED verdict does not change the packaged default by itself.** It makes the change eligible;
   the change still needs an explicit operator decision and its own PR (§10).
5. **The rejection-ratio secondary is not a win-rate proxy.** SO-RANGECAP's blue mortar rejection rate
   went from 43.3% to 79.6% — a large, real engine-layer manipulation — while the win rate missed its
   pre-registered bar by one match. A large SECONDARY 1 move with a null PRIMARY is a fully expected
   shape here and must not be reported as partial support.
6. **This program's base rate for "one loadout knob fixes the duel" is low.** Every arm of this class so
   far (P1–P7 dose ladder, `_r15`, `_r30`, standoff, rangecap) failed to move win rate past its bar, and
   the most recent decisive battery (OMN-15488) landed primary NOT-SUPPORTED. That prior is stated up
   front so a null is read as the expected outcome of a well-designed measurement, not as a failure.

---

## 8. What this battery is for, and the cheaper alternative that does not need it

Stated plainly because it is an operator decision, not a measurement one:

If the goal is a **watchable** default pairing rather than a **balanced** one, A1 can be shipped as an
alternate watchable preset on **face validity alone** — red visibly shoots, which is the actual reported
complaint — without waiting on a win-rate verdict, and balance can be settled properly under OMN-15250.
This battery is the right instrument for the balance question. It is not required for the watchability
question. The operator should not be made to buy ~6 hours of endpoint occupancy to answer a question
that a one-field preset already answers.

That option is recorded here so that choosing it later is a decision, not a reversal.

---

## 9. Acceptance gates

All run **read-only** by an agent independent of the scoring assembler; the recompute verifier must not
review the assembler's draft (the three-agent separation the OMN-15488 red battery used).

| AC | Gate |
|---|---|
| **AC1** | **Pre-registration timing.** `scripts/check_preregistration_timing.py --state-root $ROOT --overlay <arm overlay>` exits 0 for **each arm**: the overlay's latest commit author timestamp precedes that arm's first `match_started`. Cross-checked against the overlay's **full** commit ancestry (`git log --format='%H %aI %s' -- <overlay>`), not the script's single-commit output, and against `MIN(emitted_at)` over `match_started` from `events.sqlite3`. |
| **AC2** | **Contamination / bijection / casualties, per arm.** `match_started` ↔ `match_ended` ↔ `battery_raw.jsonl` are the same `match_id` set (bijective, zero orphans); seeds are exactly 5001–5030 with zero duplicates and zero out-of-block seeds; `skipped_seeds` empty; `replay_validity == 1` for both seats on every row; excluded-row counts stated per endpoint. `check_contamination_gate.py` is run **per arm state-root**. Because all three arms share the seed block by design (§6), the cross-arm isolation assertion is **state-root disjointness plus per-arm `match_id` disjointness**, re-derived explicitly and disclosed as the substitute for seed disjointness. |
| **AC3** | **ARM LEGALITY, re-run at the executing pin (OMN-15594).** Every axis in §3.1, §3.2, §3.3 re-evaluated by hand against the executing pin's contract files, with the read values quoted, and the "no consumer exists" grep re-run to confirm the enforcement gap has not silently closed or changed shape. **An arm whose legality was not hand-checked at the executing pin is not acceptable evidence** — the engine will not catch an illegal pairing (§3). |
| **AC4** | **Manipulation landed, at the engine layer.** Per-weapon `weapon_fired` / `weapon_fire_rejected` counts with reasons show A1's red actually fired `heat_lance` at ranges A0's red could not reach, and A2's blue mortar shows the `target_out_of_range` rejection shift. A win-rate delta with no engine-layer manipulation signature is a configuration defect, not a result. |
| **AC5** | **Scoring.** The primary computed exactly as §4.1 defines it, from `battery_raw.jsonl`, on both bases; every share printing its integer denominator next to its value (§4.6); the z/p implementation validated against reference values **before** being trusted on the data and cross-checked against an independent implementation; §4.7's no-correction statement quoted. |
| **AC6** | **Provider receipts.** `provider_id` literals ⊆ the overlay's declared set across all `llm_completion_*` event types; `requested = resolved + failed` exactly at lane and provider granularity. |
| **AC7** | **Supervised launch.** Each arm launched through `so battery-watch` with at least one active notification channel; the terminal state it reported (`COMPLETED` / `INCOMPLETE` / `CRASHED` / `STALLED`) recorded verbatim. A run that cannot show its watchdog terminal state is not acceptable evidence. |
| **AC8** | **No packaged default or existing contract file changed.** `git diff --stat <merge-base>..<head>` shows only additions of new paths under `contracts_data/` plus `docs/evidence/`; `cli/play.py` untouched. |

`python-test`, `frontend-test`, `sanitize-text`, and `evidence-schema` must be green on every PR in this
lane, as for all steel work.

---

## 10. MANDATORY execution path

Both clauses are requirements of this pre-registration, not recommendations. A run that skips either is
not evidence under this document.

### 10.1 Launch through `so battery-watch` (OMN-15588)

Each arm is launched **only** through the supervised entrypoint
(`src/steel_onslaught/cli/battery_watch.py`), with `--run-id`, `--raw-path`, `--log-path`,
`--expected-rows 30`, and `--stall-deadline-seconds`:

```bash
export STEEL_BATTERY_NOTIFY_COMMAND="<argv that reaches the operator; outcome JSON on stdin>"
# and/or: export STEEL_BATTERY_NOTIFY_WEBHOOK="<chat-compatible webhook URL>"
```

**At least one active channel is mandatory: with neither set, `battery-watch` exits 4 and never launches
the driver** (`battery_watch.py:_CONFIG_ERROR_EXIT`, `resolve_notifiers` / `NoActiveNotifierError`).
That refusal is the mechanism. `--expected-rows 30` is load-bearing: a short clean exit is reported
`INCOMPLETE`, not `COMPLETED`.

**Disk sentinels are prohibited.** Do not reintroduce a `BATTERY_DONE` / `NEEDS_ATTENTION` shell
wrapper — `tests/battery/test_watchdog.py` reads the runbook and fails if the bash sentinel recipe
returns to it. On the OMN-15488 run an attempt-1 crash sat undetected for roughly **five hours** behind
a correctly written sentinel that nobody read.

Two operational traps carried forward, both load-bearing: `stdin=DEVNULL` (the watchdog does this
itself — an inherited terminal stdin has repeatedly produced a double-launch race), and `pgrep -f`
before **any** relaunch against a `--state-root` an existing process may still own; a relaunch onto a
live state-root is a silent data race on `battery_raw.jsonl` / `events.sqlite3`.

### 10.2 Build the environment via the amended hermetic-snapshot runbook

The mandated execution environment is the hermetic snapshot per
`docs/runbooks/2026-07-28-hermetic-battery-snapshot-recipe.md`, **including its §3** — the OMN-15582
amendment that cost the red lane two failed launch attempts before it was written down. A plain
`uv sync` produces an `omnibase_infra` venv whose co-installed `omnimarket` is a non-VCS install, which
the delegation CLI's drift guard refuses at runtime, and a full-resolve
`uv pip install "omnimarket @ git+...@<pin>"` **cannot** succeed (conflicting transitive git URLs for
`omnibase-infra` via `omninode-memory`). The working recipe is the `--no-deps` install:

```bash
cd "$SNAP/omnibase_infra" && env -u PYTHONPATH uv pip install --python .venv/bin/python --no-deps \
  "omnimarket @ git+https://github.com/OmniNode-ai/omnimarket.git@<pin>"
```

**The verification, not the exit code, is the gate:** assert `direct_url.json` shows
`vcs_info.vcs == "git"` **and** `vcs_info.commit_id == <pin>`.

Also carried from the runbook: run with `OMNI_HOME="$SNAP"` so the drift belt compares the frozen
snapshot's own install against its own clone; and never run `scripts/check-omnimarket-venv-drift.sh`
(or anything doing a live fetch / `ls-remote`) against a hermetic snapshot — it false-positives by
design.

**The red-seat battery's existing snapshot at `~/.omnibase/battery_envs/omn15488-hermetic-20260730` is
NOT to be mutated.** SO-REDMID builds its own snapshot, or reuses that one strictly read-only with its
own state roots. That snapshot is leg (a)'s execution environment and is live evidence infrastructure.

### 10.3 The executing command shape (declared before any run)

Per arm, from the hermetic snapshot's `steel_onslaught` root, wrapped in `so battery-watch`:

```
uv run python scripts/run_ogate_objectives_battery.py \
  --overlay contracts_data/overlays/<arm overlay>.yaml \
  --red-loadout  <arm red loadout> \
  --blue-loadout <arm blue loadout> \
  --expected-arena <the arm overlay's arena_id> \
  --n 30 --seed-base 5000 --fresh \
  --state-root .onex_state/steel_onslaught/<arm state root>
```

`--overlay`, `--red-loadout`, and `--blue-loadout` are **mandatory and explicit**. The driver's argparse
defaults resolve to the asym objective overlay and its own default pairing
(`scripts/run_ogate_objectives_battery.py:458-495`), so an omitted flag silently runs a different
condition — the exact failure OMN-15166 warns about and the red battery's remediation note records.
`--expected-arena` must be passed explicitly for the same reason: its default is `foundry_60_asym_v1`,
and a mismatch against the chosen overlay's `arena_id` is a hard assertion failure on every
`MATCH_STARTED`, which is the desired fail-closed behavior — but only if the value is chosen
deliberately rather than inherited.

---

## 11. Artifacts the launch session must author, before the pre-registration commit

None of these exist yet. Authoring them is the launch session's setup, not this lane's (§0).

### 11.1 `contracts_data/loadouts/qwen35/berserker_midrange.yaml` (A1 red)

A **new** file, byte-identical to `contracts_data/loadouts/llm_qwen35_berserker.yaml` except:

- `id: loadout.llm.qwen35_berserker_midrange`
- `modules.weapons`: `[weapon.light.machine_gun, weapon.medium.heat_lance]` — `shrapnel_thrower` is the
  only module removed and `heat_lance` the only one added.
- a header comment carrying: the one-field-swap statement, the §3.1/§3.2 legality record, and the
  explicit note that the `budgets` block is copied **byte-identically** because weapon contracts carry
  no mass field (`runner.py:1780-1800` hardcodes `mass=0` for every weapon) and `expected_heat_peak` is
  a declared expectation that no `EnumBudgetViolationKind` reads — with the computed 8.5 → 21.5 shift
  recorded in the comment rather than written into the declared value.

`chassis_id`, `boiler_id`, `pilot_id`, `sensors`, `cooling`, `armor`, `gizmos`, and the whole `budgets`
block are unchanged. **`llm_qwen35_berserker.yaml` itself is not modified.**

### 11.2 Three arm overlays

One per arm, so each carries its own isolated `.onex_state` ledger paths (the SO-RANGECAP convention).
Byte-identical to each other except:

- the ledger / leaderboard / learning-artifact / evaluation-storage paths (§6's state roots),
- the header (§12),
- the arm identity in the header.

**The base overlay is the launch session's decision and must be recorded, with its reason, in each
header.** The trade is real and is not resolved here: the shipped `so play` watchable default binds
`tactical_split_v1_qwen.yaml` (arena `foundry_60`), which is the pairing the operator actually
complained about; the O-GATE battery family binds the overdeal/utility overlays on
`foundry_60_asym_v1`, which is what makes cross-arm comparison to P1–P7 legible. **Whichever is chosen,
A0 is the control and internal validity holds** — but the choice bounds §7.2's external comparison and
must be stated, not inherited from a driver default.

**One trap, found while authoring this document, that the launch session must not walk into:**
`contracts_data/overlays/tactical_split_overdeal_utility_sym_v1_qwen.yaml` declares
`arena_id: foundry_60` but its header text describes the **asym** overlay and every one of its
`.onex_state` paths points at the
`tactical_split_overdeal_utility_asym_v1_qwen` lane. Using it unmodified would write SO-REDMID's events
into another lane's ledger. If it is chosen as the base, the ledger paths must be re-pointed (which the
per-arm copies do anyway) and the header drift noted.

### 11.3 A contract test pinning each arm overlay's header sha

Mirroring `tests/contracts/test_lgate2_delegation_overlay_omn15488.py`, so a silent post-launch edit to
a pre-registration-of-record header fails `python-test`.

### 11.4 A re-run of the §3 legality hand-check at the executing pin

Recorded in the launch session's evidence, per AC3. This is not optional and it is not satisfied by
citing §3 — §3 is the record at `ea20e67`.

---

## 12. Pre-registration of record, and the AC1 seam this document creates

`scripts/check_preregistration_timing.py` reads the **executing overlay file's** latest commit author
timestamp and compares it against the first `match_started`. It does **not** read this document.

Therefore, before launch, the launch session must:

1. Embed **§2 through §7 of this document verbatim** into the header of each arm overlay, and land that
   commit before the first match of that arm.
2. Land any execution-infrastructure amendment as a **dated, numbered amendment appended to that same
   header**, before the first scored match — never as a silent edit, and never touching a criterion
   region (hypothesis, arms, endpoints, denominators, bands, escapes, interpretation map).
3. Run AC1 against each executing state-root and record the exit-0 output and the margin verbatim.
4. Cross-check AC1 against each overlay's **full** commit ancestry, not just the script's single-commit
   output.

This is an **added obligation**, not a substitute for the gate. If an overlay header and this document
ever disagree, **the overlay header is the pre-registration of record** and the disagreement is itself a
reportable defect.

---

## 13. Cost estimate

Derived from this program's own measured artifacts, not asserted.

| Item | Basis | Estimate |
|---|---|---|
| Per-arm wall time | the OMN-15488 `_r2` run measured ≈5.0 min/match from its own `events.sqlite3` window (61 matches over 5h07m38s); duel matches on this pairing are shorter than that learning battery's, so this is an upper bound | **≤ ~2.5 h / arm** |
| Three arms, serial on one MLX endpoint | 3 × the above | **≤ ~7.5 h**, unattended |
| Snapshot build + pin verification | runbook §1–§3, idempotent on re-runs | **~10–20 min** |
| Marginal monetary cost | local MLX; no metered API | **$0** — the real cost is exclusive occupancy of that endpoint |

**The endpoint-occupancy cost is the reason §8 exists.** ~7.5 hours of exclusive endpoint time is a real
scheduling cost against the AI4 window, and it buys a balance answer, not a watchability answer.

---

## 14. Limitations, collected in one place

- **A1 is multi-delta and cannot attribute an effect to range** (§1.3, §2.3, §7.3.1).
- **A2 caps blue's mortar, not blue's envelope** — `harpoon_gun` at range 30 is untouched (§7.3.2).
- **Power.** The +0.15 SUPPORTED band is under-powered at n=30; DIRECTIONAL-ONLY is the modal outcome
  for a real but moderate effect (§5).
- **Weapon/chassis compatibility is enforced by nothing** (OMN-15594); the §3 hand-check is the only
  guard and must be re-run at the executing pin (AC3).
- **OMN-15587's denominator fix does not cover this battery's driver** (§4.6); every denominator is
  therefore declared per-endpoint in this document.
- **A0 is a new control cell**, not a re-run of P6; cross-family comparison is directional only (§7.2).
- **The overlay base is unresolved here** and bounds the external comparison (§11.2).
- **One model, one arena/overlay, one loadout pairing, one seed set, card mode only.**
- **Red's damage arithmetic against a heavy chassis may be the real binding constraint** (§1.3) and no
  arm in this battery manipulates it.

---

## Citations

- **Ticket:** OMN-15586 (parent OMN-15154). Signed-off design draft: Linear comment `7d593c9e`
  (2026-07-31T19:20:51Z). Split-out code defect: **OMN-15594** (Linear comment `af32949d`).
- **Operator ruling:** 2026-07-31, *"go with your suggested approaches"*; SO-REDMID launch serialized
  after OMN-15488 leg (a).
- **Sibling pre-registration (convention followed here):**
  `docs/evidence/2026-07-31-lgate2-legA-blue-seat-endpoint-contrast-prereg.md` (#249, merge `ea20e67`).
- **Prior arms of this family:** `docs/evidence/2026-07-25-rangecap_r15_dmg16-battery.md`,
  `docs/evidence/2026-07-25-standoff_r15_dmg16-battery.md`,
  `docs/evidence/2026-07-24-pair_p6_dmg16-battery.md`,
  `docs/evidence/2026-07-25-pair_p7_dmg24-battery.md`,
  `docs/evidence/2026-07-22-lgate2-adaptation-battery.md` (the 21/21 sniper-dominance balance note).
- **Most recent decisive battery:** `docs/evidence/2026-07-31-lgate2-decisive-battery-acceptance.md`
  and `docs/evidence/2026-07-31-lgate2-decisive-battery-scoring.md` (primary NOT-SUPPORTED).
- **Driver:** `scripts/run_ogate_objectives_battery.py` (`:456-523` arg surface, `:508` seed-base
  default, `:604` summary path). **Gates:** `scripts/check_preregistration_timing.py`,
  `scripts/check_contamination_gate.py`.
- **Runbook:** `docs/runbooks/2026-07-28-hermetic-battery-snapshot-recipe.md` §3 (OMN-15582 `--no-deps`
  VCS install), §5–§6 (OMN-15588 supervised launch and terminal states).
- **Source read for §1 and §3, all at `origin/main` `ea20e67`:**
  `src/steel_onslaught/cli/play.py` (`:1891`, `:1894`, `:1895`),
  `src/steel_onslaught/contracts/weapon.py` (`:54`, `:101`),
  `src/steel_onslaught/contracts/boiler.py` (`:21`, `:48`),
  `src/steel_onslaught/contracts/chassis.py` (`:37`, `:58`, `:80`),
  `src/steel_onslaught/contracts/budget.py` (`:36-41`, `:54-77`, `:87-116`, `:118-173`),
  `src/steel_onslaught/reducers/weapons.py` (`:101-134`),
  `src/steel_onslaught/reducers/damage.py` (`:45-49`, `:117-124`, `:127-150`),
  `src/steel_onslaught/reducers/boiler.py` (`:125-160`),
  `src/steel_onslaught/reducers/failure.py` (`:86`, `:95`, `:248-300`),
  `src/steel_onslaught/reducers/scoring.py` (`:14`, `:102`),
  `src/steel_onslaught/match/runner.py` (`:1516-1538`, `:1685`, `:1780-1840`, `:1856-1868`),
  `src/steel_onslaught/events/envelope.py` (`:32`, `:43`, `:47`),
  `src/steel_onslaught/cli/battery_watch.py`,
  and the contract data files `contracts_data/weapons/{heat_lance,machine_gun,shrapnel_thrower,artillery_mortar,artillery_mortar_r15,harpoon_gun}.yaml`,
  `contracts_data/chassis/{light_scout_mk1,heavy_ironclad_mk1}.yaml`,
  `contracts_data/boilers/compact_v1.yaml`,
  `contracts_data/sensors/short_range_scanner.yaml`,
  `contracts_data/loadouts/llm_qwen35_berserker.yaml`,
  `contracts_data/loadouts/qwen35/{sniper_ironclad,sniper_ironclad_mortar_r15}.yaml`.
- **Related tickets:** OMN-15594 (compatibility enforced by nothing — the §3 hand-check exists because
  of it), OMN-15587 (share denominator — scope-limited, §4.6), OMN-15588 (supervised watchdog),
  OMN-15582 (runbook VCS step), OMN-15250 (configurable-loadout points program — deliberately NOT a
  dependency, §2.5), OMN-15488 (leg (a), which this battery is serialized behind), OMN-15166
  (silent-wrong-condition launch defaults).

*Every number in this document is either read from a named file at a named path and line at
`origin/main` `ea20e67`, quoted from a merged evidence document with its section named, or explicitly
labelled as quoted-from-ticket and not re-verified (§1.2). This document authorizes no run, and the
SO-REDMID launch is serialized after OMN-15488 leg (a).*
