# Steel Onslaught — Session Handoff (2026-07-22)

Repo: `jonahgabriel/steel_onslaught` · default branch `main` · conventional-commit titles, no ticket prefix.
CI installs Playwright chromium and runs it; **CI green is required**. Locally chromium is absent, so the
Playwright proof-of-life test fails **local-only** (deselected/skipped locally, passes in CI).

All PR / CI / SHA facts below were read live via `gh` on 2026-07-22 — not transcribed from the ledger. Every
open PR checked with `gh pr checks <n>`; merged/closed state via `gh pr view`; main's CI via `gh run list`.

---

## 1. State of the world

Steel Onslaught is a browser-rendered, LLM-piloted tactical mech skirmish: two AI pilots ("mechs") program
and resolve cards on a grid arena, all live decisions made by real language models (LLM-only — no scripted
pilot on the live path; determinism is replay-only). As of this session it **launches keyless** (`uv run so
play`, zero flags), renders the **60×60 `foundry_60`** board, defaults to **two distinct keyless Qwen
personas**, and **plays a full match to a REAL terminal** — the mid-match stall that used to freeze the game
is fixed and merged (#115). Live-verified end to end (screenshots in `docs/evidence/2026-07-21-live-run/`).
What is **not** yet true: the fixed-deck **brawler (light scout, 60 HP, short range) vs sniper (heavy
ironclad, 160 HP, long-range mortar+harpoon) duel is not a fair fight.** Four measured live-Qwen intervention
rounds (heat-lockout → ×5.5 brawler damage → moves-scaled evasion + strength sweep → sniper range-band +
carbine throttle + sniper-JSON fix) moved the brawler from ~2 to ~50 median DMG-OUT (~36% of the sniper's
160 HP) and ~4× survival, and eliminated sniper malformed-JSON aborts (3→0 across 56 matches) — but win-rate
stayed **~5% (pooled 1/43)**. Per the pre-agreed decision, single-lever tuning of this lopsided fixed deck is
**stopped**. The direction has **pivoted to DEPTH**: over-dealing the hand so pilots *select* which cards to
program is **empirically validated** (Phase A, #117) and is now the active foundation; drafting / utility
cards / asymmetric matchups + objectives are how balance re-emerges, not more knobs. **LEARNING** is a
necessary co-equal next-session track — the live learning loop is currently dead code and must be wired over
the same depth decision space (that pairing is the RSD / platform-proof thesis).

---

## 2. Live-GH scorecard (read live 2026-07-22)

**`main` @ `6a88c28e3a0914c5fa93c66cb9a062a6346041aa`** (= #112 merge commit) — CI run `29887910076` (event
`push`): **`success`** (all jobs). Latest 8 `main` push runs are all `success` — no red on `main`.

**Open PRs** (`gh pr list --state open`), each with its four checks (`gh pr checks <n>`):

| PR | Title | head SHA | branch | mergeable / state | CI (evidence-schema / frontend-test / python-test / sanitize-text) |
|----|-------|----------|--------|-------------------|--------------------------------------------------------------------|
| #117 | feat(cards): over-deal the hand so pilots select which cards to program | `2ced627` | `feat/so-overdeal-card-selection` | MERGEABLE / CLEAN | ✅ / ✅ / ✅ (3m02s) / ✅ — **all 4 pass** |
| #116 | feat(balance): brawler damage buff + live-abort cut, stacked on the c11 sniper heat-tax | `74216c9` | `feat/so-overpressure-cooldown` | MERGEABLE / CLEAN | ✅ / ✅ / ✅ (3m27s) / ✅ — **all 4 pass** |
| #108 | docs: add Steel Onslaught finish plan (this handoff rides here) | `18f320e` | `docs/so-finish-plan` | MERGEABLE / **BLOCKED** | ✅ / ✅ / **python-test PENDING** / ✅ |

**Findings from the scorecard:**
- **No red CI on any open PR and none on `main`.** #117 and #116 are 4/4 green and `CLEAN`/MERGEABLE.
- **Not a hard finding: #108 `python-test` PENDING / `BLOCKED`.** At read time #108's Playwright `python-test`
  was still running on the just-pushed plan-update commit `18f320e`; `mergeStateStatus=BLOCKED` reflects that
  pending required check, **not** a failure (the other three checks pass). This handoff commit pushes a new
  head and re-triggers all four checks; #108 is the handoff-carrier and is **not** slated to merge this
  session. Re-verify green before any future merge of #108.
- **Merged this session (confirmed `MERGED` via `gh pr view`, with merge commits):** #109 `f869d6a`, #110
  `05fd8ae`, #111 `1b8ac8f`, #112 `6a88c28` (= `main` head), #113 `1833251`, #114 `b53e4f7`,
  #115 `9a01ee3`. All are on `main`.
- **Closed (superseded), confirmed `CLOSED` via `gh pr view`:** #81 `feat(cards): guarantee movement variety
  via opt-in rule`; #100 `feat(range): add preferred-range policy handler and metrics`. Both were open+stale
  in the prior handoff; this session closed them. Do not reopen or land either — their behavior is
  superseded by the merged #114 (editable prompts + plug-in rule handlers).

---

## 3. What was accomplished this session — with honest proof class

Proof classes: **merged-on-main** (landed + CI-green on `main`) · **open-PR-verified** (CI-green, unmerged) ·
**measured-on-live-Qwen** (real-provider battery numbers) · **spec-only** (design pass, no code).

**Merged-on-main (the game now launches keyless and plays to a real terminal):**
- **#110** seat identity — one validated seat contract + LLM-only live decisions.
- **#111** terminal correctness — every wrong/missing match terminal fixed.
- **#109** reasoning visibility — render the card-cadence pilot reasoning in the deck.
- **#115** stall recovery — bounded reprompt + classified terminal; the mid-match `invalid_action_parameters`
  freeze is gone. This is the change that flips the finish-line "durable terminal" gate from red to GREEN for
  the stall class.
- **#113** one-command keyless launch + reliable start lifecycle (`uv run so play`).
- **#112** every-configured-model selectable for either seat (= `main` head `6a88c28`).
- **#114** editable prompts + plug-in rule handlers / mounted workbench.
- `#81` + `#100` **closed as superseded** (not merged).
  NET, live-verified end to end (`docs/evidence/2026-07-21-live-run/`): keyless launch, 60×60 `foundry_60`
  board, full match to a real terminal (no stall), two distinct keyless Qwen personas.

**Measured-on-live-Qwen (balance investigation — four rounds, then stop; all on #116, unmerged):**
- **r1 c11 heat-lockout** — did not fix (taxes the sniper's heat, not its offense).
- **r2 brawler damage ×5.5** (machine_gun 8→44, shrapnel 12→66) — brawler now OUT-damages the sniper in some
  matches but DIES before converting. Damage ceiling solved.
- **r3 moves-scaled evasion + strength sweep (0.08/0.14/0.20)** — the RIGHT survivability lever (sniper aimed
  hit-rate falls to 0.14 at max) but win-rate PLATEAUS ~9%; fixes being-hit, not kill-conversion. A
  survivability/flavor knob, not the win lever; pushing higher is cheesy before fair.
- **r4 sniper range-band + sustainable close-in carbine** — mechanism fired (mortar in-band hit 0.72→0.33)
  but STILL ~0%; the carbine backfilled point-blank.
- **r4b carbine throttle (cooldown 1→3) + sniper invalid-JSON fix** — STILL ~5% (pooled 1/43). **Carbine
  theory FALSIFIED**: sniper DMG-OUT stayed flat (62→64) regardless of carbine rate — the harpoon+mortar core
  is the real killer. **Sniper JSON fix WORKED**: blue `malformed_json` aborts 3→0 across 56 matches.
  Progress despite no win: brawler ~2 → ~50 median DMG-OUT (36% of 160 HP), ~4× longer survival, sniper JSON
  aborts eliminated — but the 60-vs-160 fixed-deck duel resisted FOUR measured single-lever interventions.
  New residual surfaced: a **RED brawler `invalid_action_parameters` abort** is now the dominant abort (sniper
  JSON fixed) — next-session follow-up.

**Open-PR-verified (depth thesis validated — Phase A, #117, CI-green, unmerged, mergeable):**
- Over-dealing the hand (deal 8 / program 5) so the LLM SELECTS which cards to play produced genuinely
  INTENTFUL pruning, decisively better than random — and tactical identity emerges from the SELECTION, not the
  deal: on the same balanced 4/4 hand, brawler keeps ADVANCE 0.94 vs sniper 0.30 and dumps dead VENT cards
  0.11 vs random 0.62. The "watch two models out-think each other" payoff, empirically confirmed. Over-deal
  needed **ZERO new code** — `hand_quota` was already the declarative deal count. Green-lights utility cards +
  heat-drafting.

**Spec-only (design work recorded, not built):**
- **Heat-drafting deckbuilder design pass** (`docs/design/2026-07-22-heat-drafting-deckbuilder-design.md`):
  DON'T pivot the core loop yet, PROBE with kill-gates; the make-or-break **unmeasured** risk is DRAW-THROUGH
  (do acquired cards get drawn+played before match end). `ModelSOCard.heat_cost` field already EXISTS but is
  inert — heat-as-card-currency was designed in and never wired.
- **Utility cards** (chaff/flares/smoke) as active counterplay + depth — spec.
- **Terrain lever** — false premise CORRECTED: obstacles DO block movement AND weapon LOS today (88% of shots
  blocked), so "they do nothing" was false. Real issue is LAYOUT QUALITY: 336 symmetric-scatter cells that
  help nobody; needs asymmetric cover via a NEW versioned arena, not editing `foundry_60`.
- **Range-band** (gradient close-range accuracy falloff on mortar+harpoon) — mechanism, built on #116 but
  the win-lever it targeted was falsified; the knob itself works.
- **On record:** the 20-candidate balance bracket (final 5: c11, Heavy-vs-Assault, Shell-Windup,
  Juking-Scout, Sensor-Fog — several built levers map to it: evasion=Juking-Scout, terrain=Cover-Corridors,
  range-band=Siege-Dead-Zone/Point-Blank-Falloff); the 90-finding canonical audit
  (`docs/2026-07-21-steel-onslaught-finish-audit.md` + `-findings.json`, PR #108). The W-R2 branch
  `jonah/so-recover-cards` is DEAD/abandoned (local-only, no PR, 17d dormant, unreachable from `main`, a
  different shooter-accuracy mechanic) — safe to ignore.

---

## 4. Open decisions for next session

- **(a) DECIDE what to merge from #116.** The **sniper invalid-JSON fix is a standalone robustness win**
  (blue `malformed_json` aborts 3→0 across 56 matches) and is worth landing on its own. The **balance
  numbers** (×5.5 damage, evasion, range-band, carbine throttle) may be **superseded by the depth direction**
  — do not merge the balance tuning just to close the PR. Options: (i) cherry-pick / split the JSON fix into
  its own PR and merge, hold the rest; (ii) merge #116 whole; (iii) hold #116 open as verified evidence.
  Recommend (i). PR #116 stays a real, verified, measured artifact regardless.
- **(b) DECIDE whether to merge Phase A #117.** It is the validated over-deal foundation (deal-8/program-5,
  zero new code, CI-green, mergeable). Depth builds on it. Recommend **merge** to make it the base for the
  depth+learning design.
- **(c) DECIDE the fix path for the RED brawler `invalid_action_parameters` abort** — now the dominant abort
  after the sniper JSON fix. Is it a prompt/schema fix (like the sniper JSON fix) or an engine-side
  parameter-validation tolerance change.
- **(d) DECIDE the depth path shape:** utility cards (chaff/flares/smoke) as the next increment **vs** a
  SINGLE unified depth+learning design so the deckbuilder and the live learning loop compose from the start
  (recommended below) rather than bolting learning on later.

---

## 5. Next actions — priority order

1. **P1 — The UNIFIED depth + learning design/build (single design, not two).** Over-deal (#117) is the
   FOUNDATION. Drafting / utility cards are the DECISION SPACE. The live learning loop wires OVER that space —
   this is the RSD / platform-proof thesis (event-sourced replay makes promoted policies AUDITABLE: "here's
   the policy that got promoted, replay why"). The learning infrastructure can start **independently**, but
   its efficacy rides on the depth decision space, so design them together. Concrete learning work (blocker
   `learning-adaptation-01/02/03`, NOT touched this session — the offline loop works but the LIVE path is
   DEAD CODE):
   - Instantiate `LiveLearningCoordinator` + a concrete evaluator (`begin_match` is never called; promotion
     is `None`).
   - Add a **`POLICY_PROMOTED` EVENT to `SOEventType`** so promotion folds from events, not an in-memory
     flag/YAML (`learning-adaptation-02`).
   - Connect the **admission↔terminal seam** (`learning-adaptation-03`: it would raise on every scored match
     today).
2. **P2 — Balance re-emerges from DEPTH, not fixed-deck knobs.** Asymmetric matchups + objective-based victory
   (VP/contested points, 1000-tick failsafe only) + Heavy/Assault keywords (40K-derived, Phase 2.5, spec'd);
   utility cards as active counterplay; asymmetric cover via a NEW versioned arena. Stop tuning the 60-vs-160
   fixed duel.
3. **P3 — Standalone robustness:** land the sniper invalid-JSON fix from #116 (decision 4a); fix the RED
   brawler `invalid_action_parameters` abort (decision 4c).
4. **P4 — Merge #117** to establish the over-deal foundation for P1/P2 (decision 4b).

---

## 6. Durable pointers

- **`main` @ `6a88c28e3a0914c5fa93c66cb9a062a6346041aa`** (= #112 merge; CI `success`).
- **Open PRs:** #116 `feat/so-overpressure-cooldown` @ `74216c9` (balance, CI-green, unmerged — merge
  decision open); #117 `feat/so-overdeal-card-selection` @ `2ced627` (Phase A over-deal, CI-green, unmerged);
  #108 `docs/so-finish-plan` @ `18f320e`→(this handoff commit) (docs carrier, not to merge this session).
- **Finish plan:** `docs/plans/2026-07-21-steel-onslaught-finish-plan.md` (updated this session — commit
  `18f320e`: balance stop, depth validation, learning track).
- **Canonical audit:** `docs/2026-07-21-steel-onslaught-finish-audit.md` +
  `docs/2026-07-21-steel-onslaught-finish-audit-findings.json` (90 findings).
- **Heat-drafting design doc:** `docs/design/2026-07-22-heat-drafting-deckbuilder-design.md`.
- **Live-run evidence:** `docs/evidence/2026-07-21-live-run/` (`02-configured.png`, `03-just-started.png`,
  `04-running.png`) — keyless launch → configured two-Qwen match → running to terminal. The four balance
  rounds are **measured live** and their numbers live in the finish plan's balance-investigation section
  (`## 2026-07-21 session update`); there is no separate committed battery JSON — the numbers are the record.
- **Prior handoff:** `docs/handoff/2026-07-21-steel-onslaught-session-handoff.md`.
