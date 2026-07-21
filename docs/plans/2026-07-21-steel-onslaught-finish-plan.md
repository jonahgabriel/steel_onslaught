# Steel Onslaught finish plan

Status: proposed execution plan (revised 2026-07-21 from the finish audit)  
Baseline: `main` at `4752a7f` (2026-07-20)  
Scope: `steel_onslaught` only  
Evidence: [canonical & viral finish audit](../2026-07-21-steel-onslaught-finish-audit.md) —
90 findings (6 blocker / 12 high / 32 medium / 40 low), each cited to `file:line` and
re-checked by an independent skeptic: 89 confirmed, 1 uncertain (`ledger-replay-03`).
Finding ids used below (e.g. `cards-02`) index that register.

## Finish line

Steel Onslaught is finished when a clean browser session can start the default
LLM-vs-LLM match, show the authoritative arena and split decks, use real
configured providers, produce strategically different trajectories, reach a
durable terminal result, and expose replayable evidence for the decisions and
learning state. A deterministic fallback remains an explicit failure mode, not
the default demo path.

The finish line is evidence-based. “The UI loaded” or “a match reached a tick”
is not sufficient; every gate below names the proof that must be retained.

## Current baseline (shipped, but not all proven)

- Event-sourced reducer, SQLite ledger/replay, typed envelopes, and terminal
  scoring are on `main`.
- The live overlay is `tactical_split_v1_qwen`: `foundry_60`, 60×60, 336
  blocking/LOS terrain cells, spawns `(4,4)` and `(55,55)`, paced five-register
  split decks (red 3 movement/2 weapon, blue 2 movement/3 weapon).
- The provider catalog and roster include local Qwen, GLM, Gemini, OpenRouter,
  and human options. Fresh raw matches have reached terminal state with real
  Qwen calls, but the clean-browser external-provider gate is still unproven.
- **Seat identity is broken, and worse than previously recorded.** The tactical
  overlay binds both card programmers to `pilot.llm.qwen35` (persona
  `berserker`) while labelling the blue seat `sniper`; in paced card mode the
  **card programmer — not the loadout pilot — is the decision-maker** (`runner`
  skips `ReducerPilotTick` when registers are enabled), so the default demo runs
  **berserker-vs-berserker**. No validator reconciles `deck_policy.archetype`
  with the programmer's persona (`archetype` is read by no handler), the
  mismatch survives to the ledger (`persona_id=berserker` on blue, contradicting
  `MATCH_STARTED`) and to the UI (both rails render `LLM · berserker`). The
  correct `pilot.llm.qwen35_sniper` (persona `sniper`) ships unused **in the very
  directory this overlay already loads** — `contracts_data/pilots/fire_dense_qwen/`,
  its declared `pilot_registry_dir` — alongside `llm_qwen35.yaml`, and the
  validated roster path (`canonical_qwen35.yaml`) already binds it correctly. The
  overlay rebind is therefore a one-line change requiring no registry move.
  Systemic: every qwen/glm overlay
  collapses both seats onto one persona; only gemini/openrouter differentiate.
  Differentiation is further thinned by identical decks (only `hand_quota`
  differs) and `register_count == hand_size` in every deck, so pilots reorder
  rather than select. Loci: blocking-defects table below, plus
  `contracts-data-02/03/04/06/07`, `contracts-models-01`, `cards-01/04`,
  `pilots-bus-01`, `product-viral-04`.
- PRs #106 and #107 fixed late replay delivery and stale-match promotion and
  are merged. The two remaining GitHub PRs are #81 (movement-variety guard) and
  #100 (preferred-range handler).
- Learning persists after-match evidence only, and the live path is **dead code,
  not merely disabled**. `LiveLearningCoordinator` is never instantiated in
  production, no concrete `LiveLearningEvaluator` implementation exists anywhere
  in `src/`, and `begin_match` has no production caller. The port seam is also
  broken: `LiveLearningPromotionPort` exposes only `handle_after_match`, but the
  concrete coordinator raises unless the match was admitted via `begin_match` —
  so wiring it as-is would **raise on every scored match**. Where promotion
  happens at all it is an in-memory `current_policy` mutation or a YAML lineage
  file; there is no promotion member in `SOEventType` and no promotion event is
  ever written, so live-learning state is neither durable nor replayable and
  depends on wall-clock ordering recorded nowhere.
  (`learning-adaptation-01/02/03/04`)
- No larger battlefield contract exists. `foundry_60` is the authoritative
  current map; legacy `foundry` (40×40) remains valid only for old replays.
- The full Python suite is not green in this environment solely because the
  Playwright Chromium executable is not installed; the missing browser binary
  is a release-blocking environment prerequisite, not a test to skip.
- **Deterministic fallback is currently the shipped default**, contradicting
  both the finish line and operating rule 4. The demo overlay sets
  `failure_policy: fallback` on both programmers (the model default is `raise`),
  and `LLMProgrammingPilot.program` swallows `LlmSemanticError` *and* a bare
  `except Exception` into the deterministic priority planner behind a
  `_LOG.warning`. `PLAN_COMMITTED` carries no provenance field, so a degraded
  match is indistinguishable from a real LLM match in the authoritative folded
  evidence. (`contracts-models-02`, `llm-providers-02`, `match-composition-04`,
  `product-viral-05`)
- **Terminal state has correctness gaps that a demo will hit**: sudden death is
  side-biased — the lexicographically-later mech always wins at full HP,
  reproduced across seeds 17/99/1234 (`match-runner-fold-01`); a mutual
  boiler-rupture KO goes 2→0 survivors and emits no terminal at all, leaving the
  runner publishing empty ticks until the progress gate aborts
  (`reducers-02`); two consecutive heat-locked rounds crash the runner because
  `previous_plan` is rebuilt from free-registers-only `plan_committed`
  (`cards-02`); a drawn match emits `match_scored` after `match_ended` and the
  frontend transport hard-throws on it, killing the scorecard (`frontend-02`);
  and a non-boundary worker error leaves the runtime FSM stuck in `RUNNING`
  forever with no `FAILED` status and no `MATCH_ENDED` (`match-composition-02`).
- **Closedness is enforced per-model but not at the boundary.** The envelope
  stores `payload` as an unchecked `FrozenJSONMapping` with no
  `event_type`↔payload cross-check; "closedness" is a consumer-side convention
  guarded by a hand-maintained AST allowlist that already omits a real
  raw-payload consumer (`llm/adaptation.py`, which reads `payload.get("action","?")`
  with a silent default). The single replay-equality gate compares only
  `ModelSOMatchState`, which excludes provider/persona/model-output identity —
  so replay proves physics reconstruction, not provider fidelity, and the seat
  mismatch above is invisible to replay-verified truth.
  (`events-envelope-01/02`, `llm-providers-05`; `ledger-replay-03` is the
  audit's one UNCERTAIN finding — confirm it in Phase 6 before building on it)
- **The demo path is the least-tested path.** The default overlay has zero
  coverage and the suite actively asserts the samey seat binding as correct; the
  no-cap test asserts only `LAST_MECH_STANDING` and never the winning side
  (masking the sudden-death bias); the only frontend "real match" test replays a
  legacy side-less heuristic ledger. (`contracts-data-05`, `projections-cli-04`,
  `match-runner-fold-05`, `frontend-03`, `cards-05`, `match-composition-06`)

## Audit-confirmed blocking defects

Six blockers. **Five are the same root defect observed from five subsystems** —
fix the seat-identity invariant once at the composition boundary and they
collapse together. The sixth is the unwired learning loop.

| id | defect | locus |
| --- | --- | --- |
| `contracts-data-01` | Demo overlay runs blue "sniper" on the berserker persona | `contracts_data/overlays/tactical_split_v1_qwen.yaml:65` |
| `llm-providers-01` | Programmer persona resolved with no seat cross-check | `src/steel_onslaught/match/composition.py:1079` |
| `match-composition-01` | Card-programmer identity never validated against admitted seat | `src/steel_onslaught/match/composition.py:1401` |
| `projections-cli-01` | Seat rebind is `--catalog-index`-only; overlay/roster path unguarded | `src/steel_onslaught/cli/play.py:1684` |
| `product-viral-01` | Ledger/UI advertise sniper while decisions are berserker | `contracts_data/overlays/tactical_split_v1_qwen.yaml:61` |
| `learning-adaptation-01` | Live policy adaptation is entirely unwired dead code | `src/steel_onslaught/learning/live.py:65` |

**The canonical fix and the viral fix are the same change.** Two seats with
genuinely different personas, the variety handlers actually enabled, and
`plan_committed.rationale` rendered as a decision row converts "two identical
mechs bumping into each other" into "two AI personalities you can watch reason
and diverge" — which is the entire pitch. Everything else in this plan is
correctness hardening around that payoff.

## Operating rules

1. Keep all implementation in Steel Onslaught worktrees; never edit the
   canonical child checkout directly.
2. Keep contracts, overlays, reducers, and orchestrators declarative. Any rule
   that changes behavior is an allowlisted handler selected by a typed overlay;
   no hidden conditionals or provider-specific forks in core simulation code.
3. Make event envelopes `extra="forbid"`; unknown fields are rejected at the
   boundary and every handler extracts `envelope.payload`. Preserve UUID
   correlation IDs as UUIDs.
4. Use one canonical provider/transport protocol. SQLite and Postgres are
   storage implementations behind the same typed protocol; a legacy adapter is
   not a second semantic path. Dependencies are declared in contract overlays
   and injected through DI, with no ambient provider/database fallbacks.
5. Preserve deterministic replay. Provider output, handler IDs, overlay hash,
   catalog hash, seed, and model identity must be recorded in the event/ledger
   evidence. **Determinism is a replay property, never a live decision path** —
   see rule 9.
6. Do not silently replace `foundry_60` with a guessed “larger” map. Choose a
   versioned arena contract first, then implement and migrate deliberately.
7. Do not call learning enabled until a live policy promotion changes a later
   decision and the change is replay/audit visible. Evidence-only learning is
   a separate state.
8. Treat stale branches/worktrees as inventory: promote valuable work through
   reviewed PRs, then close/delete superseded branches only after their changes
   are accounted for. Do not delete dirty or unpushed worktrees.
9. **Live matches are LLM-driven end to end. Determinism is replay-only.**
   (operator decision, 2026-07-21.) No deterministic or heuristic planner may
   produce a decision in a live match — not as a fallback, not as a degraded
   mode, not silently. If a provider fails, the match fails loudly and is
   classified; it does not quietly continue on a priority planner. The
   deterministic path exists for exactly two purposes: replaying a previously
   recorded match from its stored provider output, and hermetic tests. Heuristic
   pilots stay valid contract options for non-demo lanes; the demo lane admits
   LLM seats only.

## Design decisions (operator, 2026-07-21)

Settled in post-audit review. Constraints, not options.

1. **Unbounded matches.** No tactical tick cap — a tick limit is an arbitrary
   clock, not a design. A ~1000-tick failsafe is permitted purely as a runaway
   guard. Two consequences to reconcile rather than discover later: (a) the
   *actual* binding limit today is the LLM completion budget
   (`max_completions=256`, `match-composition-03`), which at two seats is ~128
   rounds — make the binding limit explicit instead of incidental; (b) an
   unbounded match with a kiting sniper can stalemate, so convergence must come
   from escalating in-world arena pressure, made side-fair
   (`match-runner-fold-01`), never from a clock.
2. **Pilots select cards.** Break `register_count == hand_size`; deal more than
   can be programmed so the discard is the decision (`cards-04`, approved).
3. **The map exists to create a speed/range tradeoff.** Archetypes are an
   explicit triangle: fast/brawler mechs move far per card, carry short weapon
   range, and must close under fire; sniper/heavy mechs move little, carry long
   range, and win by holding standoff. The arena must be large enough that
   closing is a real contested cost — that is the reason for a larger map, not
   aesthetics. Terrain LOS blocking is the brawler's approach tool and the
   sniper's main vulnerability, which is what makes the 336 blocking cells
   load-bearing. Requires the versioned movement-distance/multiplier field; the
   card schema supports only `speed: full` today.

## Ordered execution phases

### Phase 0 — inventory and landing hygiene

**Goal:** establish one coherent implementation line before adding behavior.

- Review PR #81 and #100 against current `main`; rebase if needed. Merge only
  after focused tests and an overlay-level proof. Close if superseded, with the
  replacement commit recorded.
- Audit unmerged branches/worktrees. Promote only the valuable slices:
  `feat/so-qwen-seat-differentiation`, the movement guard, preferred-range
  policy, and the learning-live boundary. Treat fire-dense/tactical-pack,
  duplicate replay fixes, and old UI branches as experiments until their
  behavior is compared with `main`.
- Record every branch decision in the merge-controller and rolling ledgers.
- Delete or wire the dead surfaces the audit found; a validated-but-unread
  contract field is worse than none. Specifically: the dead second
  `ReducerModeTransition` semantic path (`reducers-01`), the effect-node
  contract naming a handler class that does not exist (`llm-providers-04`), the
  legacy `OneShotLlmClient` superseded by `BoundedLlmClient` (`llm-providers-06`),
  the defined-and-tested-but-never-mounted REST replay endpoint
  (`projections-cli-03`), the dead frontend view cluster shipping with a test
  that certifies an unmounted component (`frontend-04`), and the `human.py`
  docstring that falsely claims the module is unwired (`pilots-bus-05`).
- Isolate ledger row validation: opening a ledger currently re-validates every
  row of every match against current models, so one schema-drifted row denies
  read access to all matches (`ledger-replay-02`).

**Exit evidence:** open-PR list is intentional; each retained branch has an
owner/next PR; no duplicate fix lane remains; the dead surfaces above are
deleted or wired, with a grep proving no remaining references.

### Phase 1 — reliable real-provider browser match

**Goal:** make the actual demo path work from a clean browser without refreshes
or stale-match artifacts.

- Install the pinned Playwright browser in the test environment and run the
  proof-of-life integration test. If an in-app browser is unavailable, use the
  repository's Playwright runner in CI or a documented local environment.
- Replace the current manual bootstrap-copy step with one startup command that
  generates the catalog-merged frontend artifact and launches both services.
  Add an HTTP smoke assertion that backend and Vite bootstrap return 200 with
  the same overlay/catalog hash before opening a browser.
- Exercise `Start Match` through the UI against `tactical_split_v1_qwen`, with
  two different configured Qwen seats by default (depends on the seat-identity
  repair — immediate action 1 — landing first). Verify the setup panel
  disappears after `MATCH_STARTED`, the current match ID/arena header updates,
  controls re-arm after `MATCH_ENDED`, and a new match supersedes an incomplete
  old prefix without a manual refresh.
- Run a long match with no artificial two/eleven-tick cap. Prove provider
  requests, responses/fallbacks, terminal events, SQLite rows, and replay
  validation all agree.
- Capture one screenshot per UI state (setup, running, terminal, replay) and
  retain the event/ledger IDs with the evidence.
- Fix the three defects that break a terminal match before claiming this phase:
  the frontend transport hard-throw on the draw path — `match_scored` legitimately
  follows `match_ended` because the ledger subscribes before scoring, so treat it
  as a valid post-terminal projection (`frontend-02`); the runtime FSM having no
  `FAILED`/`ABORTED` status, so a non-boundary worker error wedges the match in
  `RUNNING` with no terminal evidence and `mark_match_ended` can never succeed
  (`match-composition-02`); and the bus re-raising *every* subscriber exception as
  one `ExceptionGroup` with no critical/best-effort tiering, which couples a
  browser/WS failure to abort of the authoritative simulation (`pilots-bus-03`).

**Exit evidence:** clean-browser Playwright trace/screenshots; one real
LLM-vs-LLM terminal match; a drawn match that renders its scorecard without a
transport throw; a forced worker-error match that reaches the new
`FAILED`/terminal state instead of wedging in `RUNNING`; zero
stale-map/blank-screen/start-button defects.

### Phase 2 — interesting, rule-driven combat

**Goal:** convert the existing split-deck model into visible tactical variety.

- **Precondition — repair seat identity as one validated contract. Nothing else
  in this phase is measurable until this lands.** Add a fail-closed
  composition-time validator that, when `deck_policy` and `programmers` are both
  present, requires each programmer's resolved persona to equal its seat's
  `archetype` and requires the two seats to resolve to *distinct* personas. Apply
  the seat→option pilot rebind on the overlay/roster path, not only the
  `--catalog-index` path (or drive the programmer from the admitted seat
  selection so there is one path, not two). Bind blue to
  `pilot.llm.qwen35_sniper` and sweep the other qwen/glm overlays. Either make
  `deck_policy.archetype` load-bearing or delete it. Prove it with a
  cross-boundary regression driving overlay → `build_card_programmers` →
  `LLM_COMPLETION_REQUESTED` that asserts blue's recorded `persona_id` is
  `sniper` — two independent unit suites do not satisfy this.
- Land the movement-variety guard (#81) and preferred-range handler (#100), or
  replace them with a single reviewed successor. Enable handlers explicitly in
  `tactical_split_v1_qwen`; merging a handler PR without enabling the active
  split overlay does not satisfy this phase. Leave the baseline overlay
  available for A/B comparison and record handler provenance in replay.
- Finalize typed deck policies by archetype: fast/brawler mechs receive more
  movement and shorter movement steps; heavy/sniper mechs receive more weapon
  cards and a preferred standoff range. Add a versioned movement multiplier or
  pressure-cost field (the current card schema only supports `speed: full`) so
  fast/heavy balance is declarative rather than an untracked heuristic. Keep
  movement and weapon quotas independently observable in the hand/register UI.
- Add/retain distinct archetypes and seats (for example berserker versus
  sniper/opportunist); do not default both players to the same pilot persona.
  Give the seats genuinely different decks — today both seats draw from the same
  `deck.movement.v1`/`deck.weapon.v1` and differ only by `hand_quota`. Break the
  `register_count == hand_size` identity so pilots actually *select* cards rather
  than merely reordering a forced hand; a deck that commits every dealt card
  cannot express a tactical choice. Add a distinctness guard at launch admission
  so an all-mirror default match cannot be admitted.
  (`contracts-data-07`, `cards-04`, `product-viral-04`, `commands-gateway-05`)
- Fix the combat-correctness defects that make a match end wrong or not at all —
  a viewer hits these before any balance concern. Sudden death must apply the
  tick's pressure to **all** living mechs before resolving any destruction, and
  declare a draw when two would die on the same tick, with tie order resolved
  through seeded initiative rather than a raw `mech_id` sort
  (`match-runner-fold-01`). Emit a terminal on the >1→==0 survivor transition so
  a mutual boiler-rupture KO produces a result instead of an infinite empty-tick
  loop (`reducers-02`). Rebuild `previous_plan` from **resolved** registers
  (including `HEAT_LOCKED` repeats) so two consecutive heat-locked rounds stop
  crashing the runner (`cards-02`). Guard the resolved weapon-slot seam so a slot
  index beyond the equipped weapon count cannot crash a paced round
  (`cards-06`). Cap overkill damage to remaining HP so `HIT_RESOLVED` /
  `DAMAGE_APPLIED` stop inflating the learning fitness signal
  (`match-runner-fold-04`).
- Instrument and display the metrics needed to explain a match: movement-card
  diversity, approach/retreat ratio, distance over time, legal fire attempts,
  shots, weapon range rejections, heat/armor changes, and card draws/discards.
- Run a repeatable battery of at least 20 real-provider matches per overlay.
  Compare distributions, not one exciting run; flag identical trajectories,
  all-retreat behavior, zero-fire sides, or immediate contact as failures.

**Exit evidence:** overlay hash + handler IDs, per-match ledger/replay bundle,
metric summary showing both sides move and fire, and a short balance decision.
Seat identity is proven end-to-end: a ledger readback showing the two seats
carry *different* `persona_id` values on their `LLM_COMPLETION_REQUESTED`
evidence, agreeing with `MATCH_STARTED`'s seat assignments. The variance battery
must report winner-side distribution, not just termination reason — a battery
that never asserts which side won cannot detect the sudden-death bias.

### Phase 2.5 — objectives and weapon keywords

**Goal:** give the match a win condition that is not "kill everything" and give
the archetypes mechanical identity in contract data. Borrowed deliberately from
Warhammer 40k 10th edition; the non-adoptions below are as deliberate as the
adoptions.

- **Objective-based victory — the core change.** Steel Onslaught is pure
  deathmatch today (last mech standing plus escalating arena pressure), which is
  precisely why an unbounded match with a kiting sniper can stalemate and why
  artificial convergence looked necessary. 40k is won on Victory Points scored
  for holding objective markers, not for kills; models carry an Objective Control
  characteristic and players score at the end of each battle round. Adopt that:
  contested objective points on the arena, scored per round, match ends on a VP
  threshold. Consequences to state rather than rediscover:
  - it removes the need for an arbitrary clock — the match ends when someone
    *wins*, which is what makes design decision 1 (unbounded matches) coherent
    rather than open-ended;
  - a sniper can no longer kite indefinitely; denying ground is not the same as
    holding it, so it must contest;
  - it makes the large map earn itself — distance between objectives is the
    contested cost design decision 3 asks for;
  - it creates **asymmetric goals** — the brawler is a natural holder, the
    sniper a natural denier — which is the mechanism that produces visibly
    divergent trajectories instead of two mechs converging on the same line;
  - escalating sudden-death arena pressure likely becomes vestigial, so
    `match-runner-fold-01` drops in priority once objectives land. It is still a
    real fairness bug and still gets fixed; it just stops being the convergence
    mechanism.
- **Weapon keywords as allowlisted handlers.** A 40k weapon keyword *is* a small
  declarative rule attached to a typed weapon profile, so this is a direct fit
  for operating rule 2 — no new conditional surface in core simulation code.
  Start with exactly two: **Heavy** (bonus accuracy when the bearer did not move
  this round — standing still is rewarded, the sniper's mechanical identity) and
  **Assault** (may fire after advancing — move-and-shoot, the brawler's). State
  the point plainly: Heavy versus Assault **is** the speed/range tradeoff
  expressed as contract data rather than as a persona prompt, which is what gives
  the LLM something real to reason about instead of an adjective to role-play.
  Later candidates, named but not scheduled: `Rapid Fire X` and `Melta X` (both
  reward closing), `Hazardous` (self-damage risk, maps onto the existing
  boiler/heat system), `Ignores Cover` / `Indirect Fire` (which is what makes the
  336 blocking LOS cells load-bearing in both directions), `Anti-[keyword]`.
- **Explicit non-adoption: 40k's dice resolution.** Do not take hit roll → wound
  roll → save roll. High per-attack variance obscures whether the LLM played
  well, and "model quality is visible" is the entire premise. Randomness belongs
  in the **deal** — which cards are offered — not in resolution. Low-variance
  resolution is also what makes a replay read as "its choices caused this"
  rather than "it got lucky".
- **Deferred, named but not scheduled:** command points / stratagems (a spend
  resource for swing moments) and points costs (for balancing asymmetric
  loadouts). Both are depth-on-depth; the base loop must work first.
- **Statline discipline.** Formalize archetypes as explicit numeric profiles —
  movement per card, weapon range band, damage — so balance is tunable and the
  LLM prompt can carry a compact profile table. Archetype stops being an
  adjective and becomes the versioned movement/range fields Phase 2 already
  requires.

**v1 slice:** three objective points on `foundry_60` (centre plus two flanks),
scored at end of round, first to N VP wins, 1000-tick failsafe only; exactly two
keywords, Heavy and Assault; deal 8 / program 5; differentiated decks per
archetype.

**Exit evidence:** a versioned objective contract with its hash in
`MATCH_STARTED`; per-round VP events in the ledger and a VP-threshold terminal
across the variance battery; keyword handler IDs recorded in replay provenance
with a fixture proving Heavy fires at bonus accuracy only on a no-move round and
Assault fires after advancing; a battery showing objective contests, not only
kills, decide matches.

### Phase 3 — live learning loop

**Goal:** move from evidence collection to controlled adaptation.

- Decide first whether this phase is in scope for the demo at all. "Learning is
  explicitly off, and the code says so" is an acceptable terminal state for this
  plan and is cheaper than a half-wired loop; what is *not* acceptable is the
  current state, where dead code implies a capability that does not exist.
- If in scope: wire `LiveLearningCoordinator` into the composition and supply a
  concrete `LiveLearningEvaluator` — **none exists**; the shipped `DuelEvaluator`
  implements an unrelated protocol with a different signature. Fix the port seam
  before wiring: `LiveLearningPromotionPort` exposes only `handle_after_match`,
  while the coordinator requires prior `begin_match` admission, so passing the
  real coordinator as the `promotion` port today raises on **every** scored
  match. The match runtime must call `begin_match` at admission and the same
  instance must receive the terminal, and `AfterMatchLearningHandler` must stop
  discarding the returned `ModelSOLiveLearningOutcome`. Keep promotion disabled
  by default unless the overlay opts in.
- Require candidate lineage, policy/meta hashes, public/hidden holdouts,
  replay determinism, anti-exploit checks, bounded promotion cadence, and an
  explicit rollback path. Promotion must be an event, not an in-memory flag:
  add a closed `POLICY_PROMOTED` member to `SOEventType` carrying policy id,
  spec hash, parent hash, lineage digest, and generation; emit it to the ledger;
  and reconstruct `current_policy` by folding that stream rather than holding a
  mutable field guarded by an `RLock`. Today's promotion is lost on restart and
  its outcome depends on the wall-clock ordering of concurrent match completions,
  an ordering recorded in no event.
- Run a before/after battery using the same scenario family and provider mix.
  Prove that a later match can select a promoted policy and that the ledger and
  replay identify why it changed. Keep an evidence-only mode for debugging.

**Exit evidence:** promotion event and candidate artifact, holdout report,
replay proof, rollback proof, and a documented statement of whether adaptation
is enabled in the demo overlay.

### Phase 4 — terrain and battlefield decision

**Goal:** make the map support tactics without breaking old replays.

- First decide whether `foundry_60` is the demo battlefield. If a larger map is
  desired, define a new versioned arena contract (size, spawns, cell budget,
  movement scale, LOS rules) before implementation; never change legacy map
  semantics in place.
- For the selected contract, specify obstacle semantics: blocking, cover,
  clamber/traversal, graduated LOS penalties, and sensor/weapon cover fields.
  Implement each change as a contract + handler/reducer slice with replay
  fixtures.
- Add map proof: blocked movement, LOS denial/penalty, cover interaction, and
  spawn/path validity. Keep the 40×40 `foundry` contract for historical replay.

**Exit evidence:** arena contract/version/hash in `MATCH_STARTED`, geometry and
semantics fixtures, path/LOS/cover metrics, and a migration note.

### Phase 5 — provider and operator matrix

**Goal:** ensure model selection is real, typed, and diagnosable.

- For every catalog option (Qwen, GLM, Gemini, OpenRouter, human), run a
  smoke match or explicit human-turn fixture. Record provider/model/endpoint
  identity without secrets.
- Test timeout, malformed output, unavailable endpoint, and fallback behavior;
  distinguish intentional fallback from a provider that was never invoked.
  Make that distinction *durable*, not just observable at runtime: ship the demo
  overlay with `failure_policy: raise` (fallback becomes opt-in for offline/eval
  overlays only), and add a typed `plan_source`
  (`llm` | `deterministic_fallback`) to `ModelSOPlanCommittedPayload` so a
  degraded plan is classified in the ledger and detectable by replay. Narrow the
  bare `except Exception` in `LLMProgrammingPilot.program` that currently routes
  any error into the deterministic planner behind a log warning. Record
  `model_identity` and the served model in completion evidence so the model that
  actually answered can be verified against the configured identity
  (`llm-providers-05`), and meter the real completion budget rather than the
  dead `max_completions` grant field (`commands-gateway-01`,
  `match-composition-03`).
- Keep the default lane LLM-vs-LLM and make human-vs-LLM an explicit picker
  choice. Re-verify the Phase 2 seat-identity validator across the full matrix:
  each admitted seat's programmer, pilot, persona, chassis, loadout, and
  provider identity agree, and the differentiation survives bootstrap, WS
  commands, ledger, and replay.

**Exit evidence:** provider matrix, request/response counts, failure-policy
evidence, and a UI screenshot showing multiple configured choices.

### Phase 6 — contract and dependency canonicalization

**Goal:** remove semantic compatibility paths that can make the demo appear to
work while violating the canonical architecture.

- Audit every event model for `extra="forbid"`, unknown-field rejection, and
  envelope payload extraction. Add negative tests for an envelope containing an
  unknown field and for a handler receiving a raw payload instead of the typed
  envelope. The per-model closedness is already real; the gap is the **boundary**
  — the envelope stores `payload` as an unchecked `FrozenJSONMapping` with no
  `event_type`↔payload authority cross-check, so closedness is a consumer-side
  convention policed by a hand-maintained AST allowlist that already misses
  `llm/adaptation.py`. Enforce the authority at the boundary rather than
  extending the allowlist. Also validate the free-form envelope `schema_version`
  (nested payloads pin a `Literal`; the envelope does not) and add the missing
  negative test for `ModelSOPilotDecision`, the boundary model that becomes
  `PILOT_DECISION_MADE`. (`events-envelope-01/02/05`, `pilots-bus-06`)
- Define the storage protocol once and run the same contract/replay suite
  against SQLite and Postgres implementations. **Scope correction:** only the
  SQLite implementation exists today, so there is no second storage semantic
  path to remove — this item is live only if Postgres is actually introduced,
  and should not be carried as open debt otherwise. The real duplicate-semantics
  violation in the codebase is **seat selection**, which has two parallel
  contracts — a validated roster path (`validate_player_roster_against_overlay`,
  which does check persona binding) and an un-validated overlay-`programmers`
  path — and the demo runs the un-validated one. Collapse them to one path
  (`contracts-data-06`). Preserve only explicitly versioned replay migrations;
  any temporary adapter needs a deletion ticket and no alternate domain
  semantics.
- Close the replay-fidelity gap described in the baseline: first confirm
  `ledger-replay-03` (the audit's one UNCERTAIN finding) against the live gate,
  then fold seat/persona/model identity into the replay-verified comparison —
  today seat/launch identity round-trips as opaque bytes while card provenance
  is validated — and emit card-runtime provenance in split mode, which currently
  emits none. (`ledger-replay-03`, `contracts-models-03`)
- Require all provider, storage, learning, and rule dependencies to be named
  in overlays and supplied by DI. Add composition tests that fail when a
  dependency is silently defaulted or when a handler is not allowlisted by the
  selected rule pack.
- Reconcile the deferred omnimarket import (D3) with the canonical handler
  protocol. Either land it after sibling-version alignment or record a concrete
  compatibility contract; do not maintain two HTTP client semantics.

**Exit evidence:** extra-field negative tests including boundary-level
`event_type`↔payload rejection, a single seat-selection path with its
fail-closed validator test, a replay-equality gate that covers seat/persona/model
identity, DI/composition validation, and a decision record for legacy runtime
paths/D3. A SQLite/Postgres parity report is required only if Postgres is
actually introduced; today one storage implementation ships.

### Phase 7 — Pressure Deck UI completion

**Goal:** reconcile the shipped UI with the design document and make state
legible during a real match.

- Complete the design acceptance checklist: setup/roster, split hand quotas,
  register strip, battlefield scale/identity, telemetry/event river, terminal
  state, replay, keyboard focus, reduced motion, and responsive layout.
- **Render the reasoning. This is the shareable moment and it is currently
  absent.** In card/paced mode — the demo mode — no `PILOT_DECISION_MADE` events
  are produced at all (the runner skips `ReducerPilotTick` when registers are
  enabled), and `EventRow` renders the expanded decision row, quoted rationale,
  and confidence meter *only* for that event type. So the designed "watch the
  LLM think" centerpiece never appears: the river shows rows labelled
  "plan committed … event" with no reasoning text and the DECISIONS tally
  stays 0. Map `plan_committed` into the decisions group, add its summary case,
  and render `plan_committed.rationale`/confidence the same way. Also render the
  authoritative per-seat identity (`launch_provenance.seat_assignments`), which
  is strictly parsed today and then displayed nowhere — the UI shows only a
  runtime-derived persona, which is exactly how the seat mismatch stayed
  invisible. (`product-viral-02`, `frontend-01`, `frontend-05`)
- Fix the interaction defects: river rows are keyboard-reachable only via
  undiscoverable `j`/`k` keys (`tabIndex=-1`) and the inspector drawer is not
  focus-managed; arena transient overlays expire on wall-clock so pause does not
  freeze the arena; the tick odometer truncates past 999.
  (`frontend-07`, `frontend-06`)
- Remove stale 40×40 comments/fallbacks where they mislead, while retaining a
  safe pre-start placeholder and authoritative post-start arena size.
- Add visual regression screenshots and accessibility checks to CI; do not mark
  the gate complete on unit tests alone.

**Exit evidence:** Playwright screenshots/traces for each state, `npm run
build`, frontend tests, typecheck/lint, and the completed UI checklist.

### Phase 8 — release and maintenance gate

**Goal:** leave one reproducible, supportable release line.

- Run Python tests, frontend tests/build, contract/replay fixtures, and Docker
  integration tests (the deployment-shaped environment, not only Poetry/local
  processes).
- Retire the green-on-surrogate tests, which are the reason these defects
  survived a passing suite. The default demo overlay has **zero** coverage and
  the suite asserts the samey seat binding as correct; the no-cap test asserts
  only `LAST_MECH_STANDING` and never the winning side; the rule test uses a
  hand shape no shipped deck emits; the promotion-port test passes against a
  surrogate that ignores admission; the frontend's only "real match" test
  replays a legacy side-less heuristic ledger; and the evidence-schema release
  gate passes vacuously when zero evidence tickets exist. Each must be replaced
  by coverage that drives the actual shipped path.
  (`contracts-data-05`, `match-runner-fold-05`, `cards-05`,
  `learning-adaptation-04`, `frontend-03`, `projections-cli-05`)
- Run a final real-provider smoke and a multi-match variance battery. Archive
  the overlay/catalog/model hashes and match IDs.
- Reconcile README, handoff, deep-dive, learning, terrain, and UI plan status.
  Mark deferred Kafka delegation (R5) and omnimarket import (D3) explicitly
  optional or schedule them as separate work; neither is a hidden release gate.
- Close/merge intentional PRs, prune only clean merged worktrees/branches, and
  verify no unpushed source changes remain. Update both ledgers with the final
  receipt and known deferred work.

**Release evidence:** green CI/build receipt, Docker proof, provider/variance
battery, completed acceptance matrix, clean worktree report, and ledger links.

## Acceptance matrix

| Area | Must be true | Evidence |
| --- | --- | --- |
| Start/lifecycle | Start works once, setup hides, terminal re-arms, no refresh | Playwright trace + screenshots |
| Identity | `foundry_60`, 60×60, match/overlay/catalog hashes agree | `MATCH_STARTED` + bootstrap + ledger |
| Seat identity | Each seat's programmer, pilot, persona, chassis, loadout and provider agree; the two seats are distinct personas; mismatch fails closed | cross-boundary regression + per-seat `persona_id` in `LLM_COMPLETION_REQUESTED` vs `MATCH_STARTED` |
| Providers | Real configured provider invoked; fallback is classified *in the ledger*, not only in logs | request/response counts + model IDs + `plan_source` |
| Combat | Both sides draw legal move/fire cards, actually select (not merely reorder) them, and change range/position | 20-match metric report + replays + winner-side distribution |
| Objectives | Matches end on a VP threshold from contested objective points, not a clock; Heavy/Assault keywords change resolution as declared | objective contract hash in `MATCH_STARTED` + per-round VP events + keyword handler IDs in replay + keyword fixtures |
| Terminal | Every match reaches a durable terminal: mutual KO, draw, and worker-error paths included; no wedged `RUNNING` | terminal event per match across the battery + draw scorecard screenshot |
| Terrain | Obstacles affect movement/LOS according to versioned contract | geometry/LOS fixtures |
| Learning | Promotion is either proven and auditable or explicitly off | promotion/holdout/rollback artifacts |
| Architecture | Extra fields reject; storage/provider protocols and DI are canonical | negative/composition tests (storage parity only if Postgres lands) |
| UI | Pressure Deck states and accessibility checklist complete | screenshots + CI checks |
| Release | Tests/build/Docker/clean worktrees pass | CI receipt + ledger closeout |

## Immediate next actions

Reordered 2026-07-21: the seat-identity repair now leads, because it clears five
of the six audit blockers, is the precondition for every combat metric being
meaningful, and is simultaneously the highest-value product fix.

1. **Repair seat identity end-to-end and lock it with a fail-closed validator**
   (Phase 2 precondition). Bind blue to `pilot.llm.qwen35_sniper`, collapse the
   two seat-selection paths to one, and land the cross-boundary regression that
   asserts the two seats record different `persona_id` values. Without this,
   actions 5 and 7 measure a mirror match.
2. Set `failure_policy: raise` on the demo overlay and add `plan_source` to
   `PLAN_COMMITTED`, so a provider failure can no longer masquerade as a real
   LLM match in the authoritative evidence.
3. Make startup generate the catalog-merged bootstrap artifact and add the
   hash-equality HTTP smoke before browser testing.
4. Fix the terminal-state defects (sudden-death fairness, mutual-KO terminal,
   two-round heat lock, draw-path transport throw, runtime `FAILED` status), then
   prove the clean-browser start/terminal flow with Playwright.
5. Review #81 and #100, land the selected handler path on top of `main`, and
   **enable it in the active split overlay** (`handler_ids` is empty today, so
   merging alone changes nothing).
6. Render `plan_committed.rationale` as a decision row and surface
   `seat_assignments` in the UI — the cheapest change that makes the demo
   legible and shareable.
7. Run the 20-match variance battery, reporting winner-side distribution
   alongside the tactical metrics; use it to choose the first balance
   adjustment. Do not tune from a single ledger.
8. Decide and document whether `foundry_60` is sufficient for the first
   satisfying demo; if not, open a separate versioned-arena slice.
9. Decide whether live learning is in demo scope at all. If yes, implement the
   promotion boundary as an event only after the combat and provider gates are
   green, then run the before/after adaptation battery. If no, say so in code
   and docs and delete the dead coordinator.

## Explicit deferrals

Kafka delegation (LLM plan R5) and the deferred omnimarket handler import (D3)
remain separate integration projects unless product scope is expanded. They
must not be used to mask a failing browser, provider, combat, learning, or UI
gate.
