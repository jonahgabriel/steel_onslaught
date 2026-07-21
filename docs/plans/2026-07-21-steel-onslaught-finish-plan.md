# Steel Onslaught finish plan

Status: proposed execution plan  
Baseline: `main` at `4752a7f` (2026-07-20)  
Scope: `steel_onslaught` only

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
- The split quotas are present, but the tactical overlay currently binds both
  card programmers to `pilot.llm.qwen35` while the blue sniper loadout names
  `pilot.llm.qwen35_sniper`; the admitted pilot and card-programmer identity
  must be one validated contract.
- PRs #106 and #107 fixed late replay delivery and stale-match promotion and
  are merged. The two remaining GitHub PRs are #81 (movement-variety guard) and
  #100 (preferred-range handler).
- Learning currently persists after-match evidence. `promotion=None` in the
  default composition means live policy adaptation is not enabled yet.
- No larger battlefield contract exists. `foundry_60` is the authoritative
  current map; legacy `foundry` (40×40) remains valid only for old replays.
- The full Python suite is not green in this environment solely because the
  Playwright Chromium executable is not installed; the missing browser binary
  is a release-blocking environment prerequisite, not a test to skip.

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
   evidence.
6. Do not silently replace `foundry_60` with a guessed “larger” map. Choose a
   versioned arena contract first, then implement and migrate deliberately.
7. Do not call learning enabled until a live policy promotion changes a later
   decision and the change is replay/audit visible. Evidence-only learning is
   a separate state.
8. Treat stale branches/worktrees as inventory: promote valuable work through
   reviewed PRs, then close/delete superseded branches only after their changes
   are accounted for. Do not delete dirty or unpushed worktrees.

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

**Exit evidence:** open-PR list is intentional; each retained branch has an
owner/next PR; no duplicate fix lane remains.

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
  two different configured Qwen seats by default. Verify the setup panel
  disappears after `MATCH_STARTED`, the current match ID/arena header updates,
  controls re-arm after `MATCH_ENDED`, and a new match supersedes an incomplete
  old prefix without a manual refresh.
- Run a long match with no artificial two/eleven-tick cap. Prove provider
  requests, responses/fallbacks, terminal events, SQLite rows, and replay
  validation all agree.
- Capture one screenshot per UI state (setup, running, terminal, replay) and
  retain the event/ledger IDs with the evidence.

**Exit evidence:** clean-browser Playwright trace/screenshots; one real
LLM-vs-LLM terminal match; zero stale-map/blank-screen/start-button defects.

### Phase 2 — interesting, rule-driven combat

**Goal:** convert the existing split-deck model into visible tactical variety.

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
- Instrument and display the metrics needed to explain a match: movement-card
  diversity, approach/retreat ratio, distance over time, legal fire attempts,
  shots, weapon range rejections, heat/armor changes, and card draws/discards.
- Run a repeatable battery of at least 20 real-provider matches per overlay.
  Compare distributions, not one exciting run; flag identical trajectories,
  all-retreat behavior, zero-fire sides, or immediate contact as failures.

**Exit evidence:** overlay hash + handler IDs, per-match ledger/replay bundle,
metric summary showing both sides move and fire, and a short balance decision.

### Phase 3 — live learning loop

**Goal:** move from evidence collection to controlled adaptation.

- Wire `LiveLearningCoordinator` and an evaluator/promotion policy into the
  composition; keep promotion disabled by default unless the overlay opts in.
- Require candidate lineage, policy/meta hashes, public/hidden holdouts,
  replay determinism, anti-exploit checks, bounded promotion cadence, and an
  explicit rollback path. Promotion must be an event, not an in-memory flag.
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
- Keep the default lane LLM-vs-LLM and make human-vs-LLM an explicit picker
  choice. Validate that seat differentiation survives bootstrap, WS commands,
  ledger, and replay.
- Validate an invariant that each admitted seat's card programmer, pilot,
  persona, chassis, loadout, and provider identity agree; a blue sniper may not
  silently run the berserker programmer.

**Exit evidence:** provider matrix, request/response counts, failure-policy
evidence, and a UI screenshot showing multiple configured choices.

### Phase 6 — contract and dependency canonicalization

**Goal:** remove semantic compatibility paths that can make the demo appear to
work while violating the canonical architecture.

- Audit every event model for `extra="forbid"`, unknown-field rejection, and
  envelope payload extraction. Add negative tests for an envelope containing an
  unknown field and for a handler receiving a raw payload instead of the typed
  envelope.
- Define the storage protocol once and run the same contract/replay suite
  against SQLite and Postgres implementations. Remove or quarantine runtime
  legacy adapters when parity is proven; preserve only explicitly versioned
  replay migrations. Any temporary adapter needs a deletion ticket and no
  alternate domain semantics.
- Require all provider, storage, learning, and rule dependencies to be named
  in overlays and supplied by DI. Add composition tests that fail when a
  dependency is silently defaulted or when a handler is not allowlisted by the
  selected rule pack.
- Reconcile the deferred omnimarket import (D3) with the canonical handler
  protocol. Either land it after sibling-version alignment or record a concrete
  compatibility contract; do not maintain two HTTP client semantics.

**Exit evidence:** extra-field negative tests, SQLite/Postgres parity report,
DI/composition validation, and a decision record for legacy runtime paths/D3.

### Phase 7 — Pressure Deck UI completion

**Goal:** reconcile the shipped UI with the design document and make state
legible during a real match.

- Complete the design acceptance checklist: setup/roster, split hand quotas,
  register strip, battlefield scale/identity, telemetry/event river, terminal
  state, replay, keyboard focus, reduced motion, and responsive layout.
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
| Providers | Real configured provider invoked; fallback is classified | request/response counts + model IDs |
| Combat | Both sides draw legal move/fire cards and change range/position | 20-match metric report + replays |
| Terrain | Obstacles affect movement/LOS according to versioned contract | geometry/LOS fixtures |
| Learning | Promotion is either proven and auditable or explicitly off | promotion/holdout/rollback artifacts |
| Architecture | Extra fields reject; storage/provider protocols and DI are canonical | negative/parity/composition tests |
| UI | Pressure Deck states and accessibility checklist complete | screenshots + CI checks |
| Release | Tests/build/Docker/clean worktrees pass | CI receipt + ledger closeout |

## Immediate next actions

1. Decide and document whether `foundry_60` is sufficient for the first
   satisfying demo; if not, open a separate versioned-arena slice.
2. Make startup generate the catalog-merged bootstrap artifact and add the
   hash-equality HTTP smoke before browser testing.
3. Review #81 and #100, then land the selected handler path on top of `main`
   and enable it in the active split overlay.
4. Wire two differentiated Qwen seats into the default overlay and prove the
   clean-browser start/terminal flow with Playwright.
5. Run the 20-match variance battery and use its metrics to choose the first
   balance adjustment; do not tune from a single ledger.
6. Implement the live-learning promotion boundary only after the combat and
   provider gates are green, then run the before/after adaptation battery.

## Explicit deferrals

Kafka delegation (LLM plan R5) and the deferred omnimarket handler import (D3)
remain separate integration projects unless product scope is expanded. They
must not be used to mask a failing browser, provider, combat, learning, or UI
gate.
