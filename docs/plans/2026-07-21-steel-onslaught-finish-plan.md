# Steel Onslaught finish plan

Status: proposed execution plan (revised 2026-07-21 from the finish audit)  
Baseline: `main` at `4752a7f` (2026-07-20)  
Scope: `steel_onslaught` only  
Evidence: [canonical & viral finish audit](../2026-07-21-steel-onslaught-finish-audit.md) —
90 findings (6 blocker / 12 high / 32 medium / 40 low), each cited to `file:line` and
re-checked by an independent skeptic: 89 confirmed, 1 uncertain (`ledger-replay-03`).
Finding ids used below (e.g. `cards-02`) index that register.

**Corrected 2026-07-21** against an execution trace of every match entrypoint.
The audit — and this plan built on it — assumed `tactical_split_v1_qwen` was
"the live overlay" and the flagship demo. It is loaded by nothing. See
[Demo-path correction](#demo-path-correction-2026-07-21-verified) and the
[open decision](#open-decision--which-overlay-is-the-demo) it forces; both
supersede any statement elsewhere in this document that names a default overlay.

## Finish line

Steel Onslaught is finished when a clean browser session can start the
**designated** demo LLM-vs-LLM match — designation is itself open, see the
demo-path correction below — show the authoritative arena and that overlay's
decks, use real configured providers, produce strategically different
trajectories, reach a durable terminal result, and expose replayable evidence
for the decisions and learning state. A deterministic fallback remains an
explicit failure mode, not the default demo path.

The finish line is evidence-based. “The UI loaded” or “a match reached a tick”
is not sufficient; every gate below names the proof that must be retained.

**The "durable terminal result" gate is now GREEN for the stall class
(2026-07-22).** The [2026-07-21 live run](#live-run--verified-gameplay-2026-07-21)
had a real Qwen match stall at tick 31 with no `match_ended` when the engine
rejected a provider plan as `invalid_action_parameters` and neither retried,
terminated, nor degraded. **PR #115** (bounded reprompt + classified
`provider_semantic_failure` terminal) **merged to `main`**; a keyless
`uv run so play` match now plays through to a **real terminal, no stall**,
live-verified end to end. **Residual, not a regression:** with the sniper
`malformed_json` abort separately fixed on PR #116, a RED brawler
`invalid_action_parameters` abort is now the dominant abort — a next-session
follow-up, not a re-open of the stall gate.

## Current baseline (shipped, but not all proven)

### Live run — verified gameplay (2026-07-21)

Driven with a real browser against the live Qwen endpoint, not read from code.
Launch: `uv run so play` (zero flags, keyless). Provider: `Qwen3.6-35B-A3B` over
`http://omninode-pc.tail75df5e.ts.net:8000`. Match `match.2WKZ1NPNND8T795ZFFA9JWQSEN`,
`foundry_60` 60×60, seed 7. Screenshots and authoritative ledger counts in
[`docs/evidence/2026-07-21-live-run/`](../evidence/2026-07-21-live-run/)
(`02-configured.png`, `03-just-started.png`, `04-running.png`).

**Works (empirically, this run):**

- Keyless `uv run so play` launches and truly plays on live Qwen — Vite deck and
  match server both HTTP 200, `/v1/models` 200. Live Qwen was genuinely called:
  `llm_completion_requested` ×14 / `resolved` ×13 (`04-running.png`).
- 60×60 `foundry_60` renders with terrain; RED = Qwen berserker scout (spawn 4,4,
  60 HP), BLUE = Qwen sniper ironclad (spawn 55,55, 160 HP) — **two visibly
  distinct pilots** (the PR #110 seat-identity fix renders correctly: rails show
  `LLM · berserker` vs `LLM · sniper`) (`02-configured.png`, `04-running.png`).
- Split decks are visibly different in the hand UI: red **M3/W2**, blue **M2/W3**
  (`04-running.png`).
- The setup / PLAYER SELECT panel and START button **correctly disappeared** on
  match start — the reported "panel doesn't disappear" defect did **not**
  reproduce this run (`02-configured.png` shows the panel; `04-running.png` shows
  it gone). Downgrade that defect below.
- Real play happened: `movement_resolved` ×30, blue `artillery_mortar` fired ×3,
  one 34-damage hit put red to HP 26/60 at tick 29.

**Broken (empirically, this run):**

- **STALL — the #1 blocker.** The match ran ticks 0→31 in ~16 s then **froze with
  no terminal event**. Pinned to the last ledger event, tick 31:
  `llm_completion_failed {provider_id: qwen35, reason_code: invalid_response,
  semantic_failure_code: invalid_action_parameters, model: Qwen3.6-35B-A3B,
  completion_tokens: 176}`. The endpoint stayed healthy (re-probed 200). A Qwen
  plan the engine rejected as `invalid_action_parameters` halted the match with
  **no retry, no terminate, no recovery** — no `match_ended`, no victor. This is
  the live-provider stall (`match-composition-02` class), **resolved 2026-07-22
  by PR #115** (`fix/so-live-provider-stall-recovery`, bounded reprompt +
  classified `provider_semantic_failure` terminal), **now merged to `main`; a
  keyless `so play` match reaches a real terminal, no stall (live-verified).**
- **The brawler never brawled.** RED (berserker, short-range) fired **0 shots**;
  `weapon_fire_rejected` ×17 (out of range). It was chunked by blue's artillery
  on the approach and never closed. The speed/range tradeoff is not working — this
  is exactly the Phase 2 / Phase 2.5 combat-depth gap, not a stall symptom.
- **HP asymmetry reads unfair at a glance:** blue ironclad 160 HP vs red scout
  60 HP (`04-running.png`).
- **Pacing:** 31 ticks in ~16 s then freeze — "watch it play" is currently a
  burst, not a match. Follows directly from the stall (no terminal to pace
  toward) plus the never-closing brawler.

### Demo-path correction (2026-07-21, verified)

An independent execution trace of every match entrypoint refutes this plan's
central premise. The statements below are verified by running the code, not by
reading it.

- **There is no default overlay anywhere.** Every entrypoint declares
  `--overlay` as `required=True` with no `default=`: `so run`
  (`src/steel_onslaught/cli/main.py:49`), `so play` (`cli/play.py:1802-1807`),
  `so play-live` (`cli/play.py:1887-1892`), `so serve` (`cli/serve.py:416-421`),
  plus `balance` / `learn` / `learn-experiment` / `run-adaptation`. Nothing
  selects `tactical_split_v1_qwen`. It is not "the live overlay"; it is an
  argument no operator has ever been told to type.
- **`so play-live` is the only working browser match command.** `so play`
  cannot start a match on any shipped overlay: it builds through
  `CliApplicationFactory.packaged()` (`cli/play.py:1567`,
  `cli/application.py:43-46`, `secret_resolver=None`), so
  `live_provider_capability` stays `None` and Start Match raises
  `NonStubModelProviderError` (`commands/coordinator.py:409`) — all 8 shipped
  overlays declare `kind: openai_compatible` and none declares a stub provider.
  It also never creates the overlay's `.onex_state` directories (only
  `play_live_command` does, `cli/play.py:1999-2007`), so it fails on
  `sqlite3.OperationalError` first. `so serve` is replay-only
  (`cli/serve.py:450`).
- **A clean checkout cannot open a browser session at all.**
  `frontend/vite.config.ts:16-17` `readFileSync`s
  `frontend/.steel-onslaught-bootstrap.generated.json` *inside* `defineConfig`;
  that file is gitignored (`.gitignore:22`) and absent, so `npm run dev` fails
  at config load with `ENOENT`. No fallback, no committed bootstrap. Only
  `so play-live --bootstrap-output` produces a usable one (`cli/play.py:1935`,
  written at `:1790-1792`), because `BrowserPlayServer.start()` rewrites it with
  the bound port *and* a `command_gateway` binding.
  `scripts/export_frontend_bootstrap.py:53,63` never passes `command_gateway`
  (`cli/serve.py:67-95`), so its bootstrap binds `NULL_COMMAND_SOCKET_FACTORY`
  (`frontend/src/lib/application.ts:615`) and the browser cannot issue Start
  Match — that exporter is a replay artifact, not a demo path.
- **The reachable demo provider is GLM, not local Qwen.** With
  `--catalog-index configured_v1.yaml` all five providers merge live
  (`glm-5.2, qwen35, qwen27, openrouter, gemini`, verified by executing
  `load_model_catalog_runtime_overlay`), and the catalog's *default* seat
  options are GLM — `player_option.glm_sniper` / `player_option.glm_opportunist`
  (`configured_v1.yaml:83,97`), sourced from `live_glm_cards.yaml`
  (`configured_v1.yaml:34-36`). Out of the box the browser demo is GLM 5.2 over
  `api.z.ai` (`live_glm_cards.yaml:49-61`). The dropdown can be changed per
  seat, so the provider is an operator choice, not a property of the build.
- **That path is a SINGLE-deck match.** `live_glm_cards.yaml` declares one
  `deck.standard.v1`. `tactical_split_v1_qwen.yaml` is the **only** overlay of
  the eight that declares `deck_policy` at all (verified by loading all 8).
- **No wired path produces a split-deck match, and the split overlay is
  unreferenced.** `grep -rn "tactical_split" tests/ frontend/ scripts/ src/
  evidence/ .github/` returns **exit 1, zero matches** — no catalog entry, no
  roster, no script, no test, no documented command. Its only repo-wide
  references are this plan and the audit. The audit's own `findings.json:666`
  already recorded that `grep -rln tactical_split_v1_qwen tests/` returns
  nothing, so the "referenced by one test" claim contradicted the audit it came
  from.

**Consequence, stated plainly:** the split-deck, per-seat hand-quota, and
`deck_policy.archetype` design that this plan — all of Phase 2 and Phase 2.5 —
has been specifying applies to an overlay **nobody currently loads**. The
overlay an operator actually reaches today is single-deck and GLM-backed.
Either the split overlay gets wired (see the open decision below) or every
split-deck deliverable here is being built against a file that no demo, no
test, and no documented command touches.

**Not refuted: the split overlay works.** A split-deck match *is* reachable —
it was driven to terminal state three times, once against the live Qwen
endpoint — but only by passing the split overlay explicitly as `--overlay`.
`assemble_match_live` with `tactical_split_v1_qwen.yaml` (the exact `so run`
code path, `cli/main.py:70-76`) ended on seed 7 with 2/2 live Qwen completions
and correct 3/2 · 2/3 split hands. The same overlay under
`so play-live --catalog-index configured_v1.yaml` ended at tick 10 with
**differentiated personas** (`{berserker, sniper}`), because
`_catalog_selection_overlay` (`cli/play.py:1526-1532`) rebinds each seat to the
admitted option's `pilot_spec_id` while preserving the launch overlay's
`deck_policy` — the catalog merge only touches `llm.providers` +
`llm.model_identities` (`match/composition.py:634-678`), so the launch overlay
remains the deck authority. Making the split overlay the demo is wiring plus
one line, not a build.

**The seat-identity fix survives this correction.** PR #110's
`validate_seat_programmer_identity` enforces distinct seats **unconditionally**
— it is no longer gated on `deck_policy` being present — and it runs inside
`build_card_programmers`, the single chokepoint the catalog, roster, and
injected-overlay paths all funnel through, on the post-rebind admitted runtime
selection. So the guarantee covers the **reachable single-deck GLM path**, not
only the split overlay. Seat identity is enforced as the pair
`(provider, persona)`: sniper-vs-sniper across two *different* models is legal
and stays legal, and only same-persona-on-same-provider fails closed. The
archetype-equals-persona check remains conditional on `deck_policy`, which is
correct — it is the split overlay's own consistency rule.

### Open decision — which overlay is THE demo

Unresolved; the operator picks. Costs below come from the same verified trace.

- **(a) Wire `tactical_split_v1_qwen` in and make it the demo.** Mostly wiring:
  add a `catalog_source.qwen35_split` entry to `configured_v1.yaml` pointing at
  the split overlay plus `canonical_qwen35.yaml` and the two qwen35 loadouts,
  and set the seat `default_option_id`s to qwen options. Neither
  `_catalog_selection_overlay` nor `load_model_catalog_runtime_overlay` needs
  changing. **One real one-line blocker:** `tactical_split_v1_qwen.yaml:92-93`
  declares `secret_resolver: kind: none`, so selecting the catalog's GLM
  defaults fails composition with `llm.secret_resolver kind 'none' cannot bind
  secret-bearing providers: ['glm-5.2']` (`match/composition.py:1176-1181`);
  `kind: injected` was applied in-memory and unblocked all five providers.
  **One design defect:** the `--roster` path performs no seat→programmer rebind
  at all (`cli/play.py:1683-1690`, `selected_overlay = overlay` unless a catalog
  is supplied), so the overlay's own both-berserker `programmers`
  (`tactical_split_v1_qwen.yaml:62-67`) run verbatim and the ledger contradicts
  its own `MATCH_STARTED` — fix by binding blue to `pilot.llm.qwen35_sniper`
  (already shipped in this overlay's declared `pilot_registry_dir`) or by
  routing the demo through `--catalog-index`.
- **(b) Add a `deck_policy` to the reachable overlay and keep the current launch
  path.** Keeps GLM + `configured_v1` as the demo and leaves bootstrap/launch
  mechanics untouched. Real work, not wiring: `live_glm_cards` ships a single
  `deck.standard.v1`, so this means authoring split decks and quotas for an
  overlay that has none — and it strands the split overlay a second time.
- **(c) Consolidate the eight card overlays.** Three of the eight
  (`tactical_v1_qwen`, `fire_dense_v1_qwen`, `tactical_split_v1_qwen`) are
  reachable from no catalog and no roster; the first two are referenced only by
  tests, the third by nothing. Real work with real blast radius — every
  consolidation touches the catalog sources at `configured_v1.yaml:10-66` and
  the tests pinned to each overlay — but it is the only option that stops the
  overlay set from accreting further unreferenced files.

**Separate decision, flagged explicitly: is the demo provider GLM or local
Qwen?** This is not implied by the overlay choice and needs its own call. The
catalog default is GLM 5.2 over `api.z.ai` with `secret://llm/glm` ←
`LLM_GLM_API_KEY` (`live_glm_cards.yaml:49-61`); the local alternative is
`Qwen3.6-35B-A3B` over Tailscale `:8000`, keyless
(`tactical_v1_qwen.yaml:55-61`). **Only Qwen has been exercised live end to
end**; whether GLM, Gemini, or OpenRouter completes a real match against its
live endpoint is unverified. The two candidates also disagree on failure
semantics — `live_glm_cards` omits `failure_policy` and therefore defaults to
`raise`, while all six qwen/gemini/openrouter overlays set `fallback` — so
operating rule 9 has to be applied to whichever is chosen.

### Baseline inventory

- Event-sourced reducer, SQLite ledger/replay, typed envelopes, and terminal
  scoring are on `main`.
- `tactical_split_v1_qwen` declares `foundry_60`, 60×60, 336 blocking/LOS
  terrain cells, spawns `(4,4)` and `(55,55)`, and paced five-register split
  decks (red 3 movement/2 weapon, blue 2 movement/3 weapon). **It is loaded by
  nothing** — see the demo-path correction above. Every other shipped overlay is
  single-deck.
- The provider catalog and roster include local Qwen, GLM, Gemini, OpenRouter,
  and human options. Fresh raw matches have reached terminal state with real
  Qwen calls, but the clean-browser external-provider gate is still unproven,
  and no non-Qwen provider has been proven to complete a match live.
- **Seat identity is broken on the un-rebound launch paths.** The split overlay
  binds both card programmers to `pilot.llm.qwen35` (persona `berserker`) while
  labelling the blue seat `sniper`; in paced card mode the **card programmer —
  not the loadout pilot — is the decision-maker** (`runner` skips
  `ReducerPilotTick` when registers are enabled), so a bare `--overlay` or
  `--roster` launch runs **berserker-vs-berserker**. Scope correction: this is
  **not** true of the `--catalog-index` path, which rebinds each seat to the
  admitted option's `pilot_spec_id` (`cli/play.py:1526`) and was verified
  producing `{berserker, sniper}`. No validator reconciles
  `deck_policy.archetype` with the programmer's persona (`archetype` is read by
  no handler — only `hand_quota` is consumed anywhere in `src/`), the mismatch
  survives to the ledger (`persona_id=berserker` on blue, contradicting
  `MATCH_STARTED`) and to the UI (both rails render `LLM · berserker`). The
  correct `pilot.llm.qwen35_sniper` (persona `sniper`) ships unused **in the very
  directory this overlay already loads** — `contracts_data/pilots/fire_dense_qwen/`,
  its declared `pilot_registry_dir` — alongside `llm_qwen35.yaml`. The roster
  `canonical_qwen35.yaml` *declares* the sniper binding correctly, but nothing
  applies it: on the roster path `selected_overlay = overlay`
  (`cli/play.py:1683-1690`), so a verified 12-tick roster run emitted all six
  `LLM_COMPLETION_REQUESTED` with `persona_id: berserker` while
  `MATCH_STARTED.launch_provenance` recorded blue as
  `player_option.qwen35_sniper` / `persona_id: sniper` — one match, two
  contradictory records. The overlay rebind is a one-line change requiring no
  registry move. Systemic in the overlay *files*: every qwen/glm overlay authors
  both seats onto one persona and only gemini/openrouter differentiate as
  authored — but the catalog rebind repairs this at runtime for the catalog
  path, including GLM (verified resolving to `pilot.glm.sniper` /
  `pilot.glm.opportunist`).
  Differentiation is further thinned by identical decks (only `hand_quota`
  differs) and `register_count == hand_size` in every deck, so pilots reorder
  rather than select. Loci: blocking-defects table below, plus
  `contracts-data-02/03/04/06/07`, `contracts-models-01`, `cards-01/04`,
  `pilots-bus-01`, `product-viral-04`.
- **PR state (verified 2026-07-22, `main` at `6a88c28`).** Merged to `main` this
  session: **#110** (one validated seat contract + LLM-only live decisions — the
  seat-identity fix), **#111** (correct every wrong/missing terminal), **#109**
  (render card-cadence pilot reasoning in the deck), **#115** (live-provider stall
  recovery), **#113** (one-command keyless launch + start lifecycle), **#112**
  (every configured model selectable per seat), **#114** (editable prompts +
  plug-in rule handlers / mounted workbench); plus earlier #106/#107 (late replay
  delivery, stale-match promotion). **#81** (movement-variety guard) and **#100**
  (preferred-range handler) are **closed as superseded by #114**. **Open, NOT on
  `main`:** **#116** (balance investigation — CI green, unmerged, open merge
  decision; see the balance section), **#117** (depth Phase A / over-deal — CI
  green, mergeable, unmerged), **#108** (this plan). **The stall-blocked live run
  above is now superseded:** keyless launch (#113), stall recovery (#115),
  per-seat model selection (#112), and editable prompts / plug-in handlers (#114)
  are all on `main`, so `uv run so play` now launches keyless and plays a full
  match to a **real terminal (no stall)** with two distinct keyless Qwen personas
  — live-verified end to end (`docs/evidence/2026-07-21-live-run/`).
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
  **Status:** untouched this session; now a **first-class next-session track**
  (operator: "it's necessary") — wire it unified with depth, see Phase 3.
- No larger battlefield contract exists. `foundry_60` is the authoritative
  current map; legacy `foundry` (40×40) remains valid only for old replays.
- The full Python suite is not green in this environment solely because the
  Playwright Chromium executable is not installed; the missing browser binary
  is a release-blocking environment prerequisite, not a test to skip.
- **Deterministic fallback is the shipped default on six of eight overlays**,
  contradicting both the finish line and operating rule 4. All six
  qwen/gemini/openrouter overlays — including the split overlay — set
  `failure_policy: fallback` on both programmers (the model default is `raise`).
  Correction: `live_glm_cards`, the overlay behind the reachable catalog
  default, **omits** `failure_policy` and therefore already defaults to `raise`,
  so this defect follows the demo-overlay decision rather than preceding it.
  Independently of the overlay, `LLMProgrammingPilot.program` swallows
  `LlmSemanticError` *and* a bare
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
- **The demo path is the least-tested path.** The split overlay has zero
  coverage because it has zero references of any kind (grep exit 1 across
  `tests/ frontend/ scripts/ src/ evidence/ .github/`), and the suite actively
  asserts the samey seat binding as correct; the
  no-cap test asserts only `LAST_MECH_STANDING` and never the winning side
  (masking the sudden-death bias); the only frontend "real match" test replays a
  legacy side-less heuristic ledger. (`contracts-data-05`, `projections-cli-04`,
  `match-runner-fold-05`, `frontend-03`, `cards-05`, `match-composition-06`)

## Audit-confirmed blocking defects

Six blockers. **Five are the same root defect observed from five subsystems** —
fix the seat-identity invariant once at the composition boundary and they
collapse together. The sixth is the unwired learning loop.

Scope correction (2026-07-21): the four overlay/CLI-side loci below are cited
against `tactical_split_v1_qwen`, which **no reachable path loads**. They remain
real defects on the `--overlay` and `--roster` launch paths, and the composition
loci (`llm-providers-01`, `match-composition-01`) are path-independent — but
"demo overlay" in the defect names refers to the overlay this plan *assumed* was
the demo, not the one an operator reaches today. PR #110 lands the fix
unconditionally, so it covers both.

| id | defect | locus |
| --- | --- | --- |
| `contracts-data-01` | Split overlay runs blue "sniper" on the berserker persona | `contracts_data/overlays/tactical_split_v1_qwen.yaml:65` |
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
   **VALIDATED 2026-07-21 (PR #117, Phase A).** Over-deal (deal 8 / program 5)
   produced genuinely intentful pruning, decisively better than random, and
   tactical identity emerged from the *selection* not the deal (same 4/4 hand:
   brawler keeps ADVANCE 0.94 vs sniper 0.30; dumps dead VENT 0.11 vs random
   0.62). It needed **zero new code** — `hand_quota` was already the declarative
   deal count. Green-lights utility cards + heat-drafting.
3. **The map exists to create a speed/range tradeoff.** Archetypes are an
   explicit triangle: fast/brawler mechs move far per card, carry short weapon
   range, and must close under fire; sniper/heavy mechs move little, carry long
   range, and win by holding standoff. The arena must be large enough that
   closing is a real contested cost — that is the reason for a larger map, not
   aesthetics. Terrain LOS blocking is the brawler's approach tool and the
   sniper's main vulnerability, which is what makes the 336 blocking cells
   load-bearing. Requires the versioned movement-distance/multiplier field; the
   card schema supports only `speed: full` today. **Empirically broken as of the
   2026-07-21 live run:** the brawler fired 0 shots and never closed — it was
   chunked on the approach by the sniper's artillery and `weapon_fire_rejected`
   ×17 (out of range). Today the tradeoff is all downside for the brawler with no
   mechanism to make closing pay off; this decision plus Phase 2.5 objectives are
   what make it a real triangle rather than a losing archetype. **Verified since:**
   terrain blocking works (88% of shots blocked); the gap is *layout* — 336
   symmetric-scatter cells help nobody — so the fix is asymmetric cover in a new
   versioned arena (Phase 4), not the blocking mechanic.

## 2026-07-21 session update — balance stopped, depth validated, learning next

Measured or verified this session. Terse by design; do not inflate.

### Balance investigation — four measured rounds, then stop (PR #116, unmerged)

The lopsided fixed deck — brawler (light scout, 60 HP, short-range) vs sniper
(heavy ironclad, 160 HP, long-range mortar + harpoon) — was probed with four
measured live-Qwen rounds, all on **PR #116** (`feat/so-overpressure-cooldown`,
head `74216c9`, **CI green, UNMERGED**):

- **r1 — heat-lockout (c11):** did not fix. Taxes the sniper's heat, not its offense.
- **r2 — brawler damage ×5.5** (machine_gun 8→44, shrapnel 12→66): brawler now
  out-damages the sniper in some matches but **dies before converting**. Damage
  ceiling solved; kill conversion not.
- **r3 — moves-scaled evasion + strength sweep** (0.08/0.14/0.20): the *right*
  survivability lever (sniper aimed hit-rate falls to 0.14 at max) but win-rate
  **plateaus ~9%** — fixes being-hit, not kill-conversion, and pushing higher is
  cheesy before fair. A survivability/flavor knob, not the win lever.
- **r4 — sniper range-band + close-in carbine:** the range-band mechanism fired
  (mortar in-band hit 0.72→0.33) but win-rate **still ~0%** — a point-blank
  carbine backfilled the sniper's close-range hole.
- **r4b — carbine throttle (cooldown 1→3) + sniper invalid-JSON fix:** still
  **~5%** (pooled 1/43). The carbine theory was **falsified** — sniper DMG-OUT
  stayed flat (62→64) regardless of carbine rate; the **harpoon + mortar core is
  the killer, not the carbine**. The sniper JSON fix **worked**: blue
  `malformed_json` aborts 3→0 across 56 matches.

**Progress despite zero wins:** the brawler went from ~2 DMG-OUT to ~50 median
(36% of the sniper's 160 HP) and survives ~4× longer; sniper JSON aborts
eliminated. But the 60-vs-160 fixed deck **resisted four measured single-lever
interventions**.

**Decision (pre-agreed, now triggered): stop tuning this lopsided fixed-deck
matchup.** Balance re-emerges via the **depth direction** (drafting + asymmetric
matchups + objectives), not more knobs — as the heat-drafting design pass
predicted. **PR #116 stays open** as real, verified, measured work; whether/what
to merge is an **open decision** — the sniper-JSON fix is a standalone robustness
win, but the balance numbers may be superseded by depth. **New residual:** with
the sniper JSON abort fixed, a **RED brawler `invalid_action_parameters` abort**
is now the dominant abort — next-session follow-up.

### Depth thesis — VALIDATED (Phase A, PR #117, CI green, mergeable, unmerged)

Over-dealing the hand (deal 8 / program 5) so the LLM **selects** which cards to
play produced genuinely **intentful pruning**, decisively better than random —
and tactical identity emerges from the **selection**, not the deal (same balanced
4/4 hand: brawler keeps ADVANCE 0.94 vs sniper 0.30; dumps dead VENT 0.11 vs
random 0.62). This is the "watch two models out-think each other" payoff,
empirically confirmed. Over-deal needed **zero new code** — `hand_quota` was
already the declarative deal count. This green-lights **utility cards +
heat-drafting**, and validates design decision 2 and the Phase 2
`register_count == hand_size` break. **Depth is now the active direction.**

### Learning — necessary, first-class, next session

Operator: "it's necessary." Not optional, not off. The live loop is dead code
today (`learning-adaptation-01/02/03`); next session wires it for real —
instantiate `LiveLearningCoordinator` + a concrete evaluator, add a
`POLICY_PROMOTED` event to `SOEventType` so promotion folds from events, connect
the admission↔terminal seam. **Unified with depth:** the loop learns over the
deck/draft decision space, and event-sourced replay makes promoted policies
auditable ("here's the policy that got promoted, replay why") = the RSD /
platform-proof thesis. Infra can start independently; efficacy rides on the depth
decision space, so the next depth design and the learning design should be **one
document, not two**. See Phase 3 (rewritten).

### Design menu — spec'd, not built

Queued, rough priority:

- **Utility cards** — chaff / flares / smoke as active counterplay and
  heat-drafting fodder. `ModelSOCard.heat_cost` **already exists but is inert**:
  heat-as-card-currency was designed in and never wired, so pricing utility cards
  in heat is wiring, not a new field.
- **Terrain lever — premise corrected.** Verified: obstacles **do** block
  movement **and** weapon LOS today — **88% of shots blocked** in the probe — so
  "they do nothing" was **false**. The real issue is **layout quality**: 336
  symmetric-scatter cells that help nobody. Fix is **asymmetric cover via a NEW
  versioned arena** (Phase 4), not editing `foundry_60` in place.
- **Heat-drafting deckbuilder** (design pass on PR #108): **do not pivot the core
  loop yet — probe with kill-gates.** The make-or-break **unmeasured risk is
  draw-through**: do acquired cards get drawn and played before match end? Prove
  that before building the deckbuilder.

### On record

- **20-candidate balance bracket** (final 5: c11, Heavy-vs-Assault, Shell-Windup,
  Juking-Scout, Sensor-Fog); several built levers map to it — evasion =
  Juking-Scout, terrain = Cover-Corridors, range-band = Siege-Dead-Zone /
  Point-Blank-Falloff.
- **90-finding canonical audit** (`docs/2026-07-21-…`, PR #108).
- Branch `jonah/so-recover-cards` (W-R2) is **dead/abandoned** — local-only, no
  PR, 17d dormant, unreachable from `main`, a different (shooter-accuracy)
  mechanic. Safe to ignore.

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
  the same overlay/catalog hash before opening a browser. Scope, per the
  demo-path correction: a clean checkout has **no** bootstrap and **no**
  `node_modules`, and `vite.config.ts` throws `ENOENT` at config load, so this
  command must cover `npm install` + bootstrap generation, not just process
  launch. It must use `so play-live --bootstrap-output` (the only generator that
  emits a `command_gateway` binding); `scripts/export_frontend_bootstrap.py`
  yields a Start-Match-incapable bootstrap and is for replay only.
- Fix or delete `so play`. It cannot start a match on any shipped overlay
  (packaged factory ⇒ `NonStubModelProviderError`) and never creates the
  overlay's `.onex_state` directories, so it fails on `sqlite3.OperationalError`
  first. A documented command that cannot work is worse than no command.
- Exercise `Start Match` through the UI against **the overlay chosen by the open
  decision above** — this plan can no longer assume `tactical_split_v1_qwen`,
  because nothing loads it. If the split overlay is chosen, this step also
  requires its `secret_resolver: kind: none` → `injected` one-liner
  (`tactical_split_v1_qwen.yaml:92-93`) or the catalog's GLM defaults fail
  composition. Run with two distinct configured seats (depends on the
  seat-identity repair — immediate action 1 — landing first). Verify the setup panel
  disappears after `MATCH_STARTED`, the current match ID/arena header updates,
  controls re-arm after `MATCH_ENDED`, and a new match supersedes an incomplete
  old prefix without a manual refresh. **Partially discharged (2026-07-21 live
  run):** the setup-panel-disappears and match-ID/arena-header-updates behaviors
  were observed passing on the keyless `so play` path (the reported
  panel-doesn't-disappear defect did not reproduce). The `MATCH_ENDED` re-arm and
  supersession behaviors remain **unproven** because the match stalled with no
  terminal — re-verify once PR #115 lands.
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
  in this phase is measurable until this lands.** In flight as PR #110, and its
  shape changed after the demo-path correction: the distinctness check is now
  **unconditional**, not gated on `deck_policy` being present, so the guarantee
  covers the reachable single-deck catalog/roster paths and not only the split
  overlay. Seat identity is enforced as the pair `(provider, persona)` — the
  same persona driven by two different models is a legitimate matchup and stays
  legal; only same-persona-on-same-provider fails closed as an unannounced
  mirror. `validate_seat_programmer_identity` runs inside
  `build_card_programmers`, the single chokepoint the catalog, roster, and
  injected-overlay paths all funnel through, and it reads the **post-rebind
  admitted runtime selection**, so a differentiated-looking overlay cannot be
  collapsed by the selection that actually launched. The
  archetype-equals-persona check stays conditional on `deck_policy`, which is
  correct: it is the split overlay's own consistency rule. Also apply the
  seat→option pilot rebind on the overlay/roster path, not only the
  `--catalog-index` path (or drive the programmer from the admitted seat
  selection so there is one path, not two). Bind blue to
  `pilot.llm.qwen35_sniper` and sweep the other qwen/glm overlays. Either make
  `deck_policy.archetype` load-bearing or delete it — nothing in `src/` reads it
  today. Prove it with a cross-boundary regression driving overlay →
  `build_card_programmers` → `LLM_COMPLETION_REQUESTED` that asserts blue's
  recorded `persona_id` is `sniper` — two independent unit suites do not satisfy
  this.
- Land the movement-variety guard (#81) and preferred-range handler (#100), or
  replace them with a single reviewed successor. Enable handlers explicitly in
  **the overlay the open decision designates as the demo**; `handler_ids` is
  `[]` in seven shipped overlays and unset in `live_glm_cards`, so merging a
  handler PR without enabling it in a *reachable* overlay changes nothing an
  operator can see. Leave the baseline overlay
  available for A/B comparison and record handler provenance in replay.
- Finalize typed deck policies by archetype: fast/brawler mechs receive more
  movement and shorter movement steps; heavy/sniper mechs receive more weapon
  cards and a preferred standoff range. Add a versioned movement multiplier or
  pressure-cost field (the current card schema only supports `speed: full`) so
  fast/heavy balance is declarative rather than an untracked heuristic. Keep
  movement and weapon quotas independently observable in the hand/register UI.
- Add/retain distinct archetypes and seats (for example berserker versus
  sniper/opportunist); do not default both players to the same pilot persona.
  Give the seats genuinely different decks — in the split overlay both seats
  draw from the same `deck.movement.v1`/`deck.weapon.v1` and differ only by
  `hand_quota`, and in every reachable overlay there is a single shared deck and
  no `deck_policy` at all. Break the
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
- **Utility cards as active counterplay.** chaff / flares / smoke — declarative
  cards that deny or degrade a shot rather than deal damage — add depth and
  heat-drafting fodder. `ModelSOCard.heat_cost` **already exists in the model but
  is inert**: heat-as-card-currency was designed in and never wired, so a utility
  card priced in heat is a wiring job, not a new field. Green-lit by the over-deal
  validation (Phase A / #117).
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

- **Scope is settled: learning is in, and it is necessary** (operator, 2026-07-21
  — "it's necessary"). First-class track, tackled next session, not a deferred
  maybe. The prior "explicitly off is acceptable" framing is withdrawn; the only
  unacceptable state is today's — dead code implying a capability that does not
  exist. Design it **unified with depth**: the loop learns over the deck/draft
  decision space that Phase 2 / Phase 2.5 open up, and event-sourced replay of a
  `POLICY_PROMOTED` stream makes every promotion auditable — "here is the policy
  that got promoted, replay why" — which is the RSD / platform-proof thesis.
  Infrastructure can be built independently; efficacy rides on the depth decision
  space, so the next depth design and the learning design should be one document,
  not two.
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
- **Premise corrected (2026-07-21, verified):** terrain is **not** inert —
  obstacles block movement *and* weapon LOS today (**88% of shots blocked** in the
  probe). The defect is **layout quality**: `foundry_60`'s 336 cells are a
  symmetric scatter that helps nobody. Fix is **asymmetric cover authored into a
  new versioned arena** (approach lanes for the brawler, standoff sightlines for
  the sniper), not an in-place edit — the arena work this phase already scopes.
  This is what makes the speed/range triangle (design decision 3) mechanically
  real. (See the design menu.)
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
  path. Correction: it is worse than "two contracts" — there are three launch
  paths with three different behaviors. `--catalog-index` rebinds seats
  (`cli/play.py:1526-1532`), `--roster` validates its declaration but applies no
  rebind (`cli/play.py:1683-1690`), and a bare `--overlay` does neither. The
  roster path can therefore emit a ledger that contradicts its own
  `MATCH_STARTED`, verified. Collapse them to one path
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
  survived a passing suite. The split overlay has **zero** coverage and **zero
  references of any kind**, and the suite asserts the samey seat binding as
  correct; the no-cap test asserts
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
  The docs are worse than stale, they are wrong: `README.md:23-27` documents
  **no way to start a match at all**, and every `so run`/`so serve` recipe in
  `HANDOFF.md:163-195` is dead (`--ledger-path` does not exist — verified
  `Error: No such option '--ledger-path'`, exit 2), while HANDOFF.md still
  describes a `PROVIDER_ENDPOINTS` constant removed from `client_http.py` long
  ago. `README.md:20-21` also claims the packaged path is stub-safe; it is not —
  when `http_transport is None` and an HTTP provider is selected,
  `match/composition.py:1197-1201` constructs a real `httpx.Client`, so a
  packaged `so run` makes live network calls. Ship exactly one documented,
  executed canonical command for the chosen demo overlay.
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
| Identity | The designated demo overlay's arena (`foundry_60`, 60×60, if that overlay is chosen) and match/overlay/catalog hashes agree | `MATCH_STARTED` + bootstrap + ledger |
| Seat identity | Each seat's programmer, pilot, persona, chassis, loadout and provider agree; the two seats resolve to distinct `(provider, persona)` pairs; mismatch fails closed unconditionally, on single-deck and split overlays alike | cross-boundary regression + per-seat `persona_id` in `LLM_COMPLETION_REQUESTED` vs `MATCH_STARTED` |
| Providers | Real configured provider invoked; fallback is classified *in the ledger*, not only in logs | request/response counts + model IDs + `plan_source` |
| Combat | Both sides draw legal move/fire cards, actually select (not merely reorder) them, and change range/position | 20-match metric report + replays + winner-side distribution |
| Objectives | Matches end on a VP threshold from contested objective points, not a clock; Heavy/Assault keywords change resolution as declared | objective contract hash in `MATCH_STARTED` + per-round VP events + keyword handler IDs in replay + keyword fixtures |
| Terminal | Every match reaches a durable terminal: mutual KO, draw, and worker-error paths included; no wedged `RUNNING` | terminal event per match across the battery + draw scorecard screenshot |
| Terrain | Obstacles affect movement/LOS according to versioned contract | geometry/LOS fixtures |
| Learning | Live loop wired (not dead code); a promotion changes a later decision and is replay-auditable via a `POLICY_PROMOTED` event | promotion/holdout/rollback artifacts + `POLICY_PROMOTED` in ledger |
| Architecture | Extra fields reject; storage/provider protocols and DI are canonical | negative/composition tests (storage parity only if Postgres lands) |
| UI | Pressure Deck states and accessibility checklist complete | screenshots + CI checks |
| Release | Tests/build/Docker/clean worktrees pass | CI receipt + ledger closeout |

## Immediate next actions

Reordered 2026-07-22 after the stall fix and the balance/depth findings. The
**live-provider stall is resolved** — **PR #115 merged**; a keyless
`uv run so play` match now reaches a durable terminal with no stall, live-verified
end to end — so it drops out of the queue, as does the seat-identity repair
(**PR #110 merged**, distinct seats confirmed live). The active direction is now
**depth**, not more balance knobs.

**P1 — commit to the depth direction and design depth+learning as one.** The
balance investigation stopped after four measured single-lever rounds could not
crack the 60-vs-160 fixed deck (see the balance section); over-deal (#117) proved
selection produces intentful, divergent play. So the next build is **depth**
(utility cards + heat-drafting + objectives) and the next design is a **single
unified depth+learning design** — the deckbuilder and the live learning loop must
compose from the start. Learning is **first-class and necessary** (operator), not
a deferred maybe; it is the immediate next-session track (see action 9 and
Phase 3, rewritten).

0. **Answer the open decision — which overlay is THE demo, and which provider.**
   Every action below that names an overlay is blocked on it, and the plan can
   no longer default to `tactical_split_v1_qwen` because nothing loads it.
1. **Repair seat identity end-to-end and lock it with a fail-closed validator**
   (Phase 2 precondition). **DONE — merged as PR #110** and confirmed in the
   2026-07-21 live run (RED berserker vs BLUE sniper rendered distinct). It bound
   blue to `pilot.llm.qwen35_sniper`, collapsed the seat-selection paths, and
   landed the cross-boundary `persona_id` regression. Retained here only as the
   dependency other actions cite; no further work.
2. Set `failure_policy: raise` on the chosen demo overlay and add `plan_source` to
   `PLAN_COMMITTED`, so a provider failure can no longer masquerade as a real
   LLM match in the authoritative evidence.
3. Make startup generate the catalog-merged bootstrap artifact and add the
   hash-equality HTTP smoke before browser testing.
4. Fix the terminal-state defects (sudden-death fairness, mutual-KO terminal,
   two-round heat lock, draw-path transport throw, runtime `FAILED` status), then
   prove the clean-browser start/terminal flow with Playwright.
5. **DONE — PR #114 merged** (plug-in rule handlers / editable prompts / mounted
   workbench), and **#81 and #100 closed as superseded**. Remaining work:
   **enable the handlers in the overlay action 0 designates** — `handler_ids` was
   empty or unset in all eight overlays, so merging alone changed nothing an
   operator sees.
6. Render `plan_committed.rationale` as a decision row and surface
   `seat_assignments` in the UI — the cheapest change that makes the demo
   legible and shareable.
7. **Balance battery run and stopped (2026-07-21).** Four measured live-Qwen
   rounds on PR #116 could not crack the 60-vs-160 fixed deck with any single lever
   (heat-lockout, ×5.5 damage, evasion sweep, sniper range-band + carbine
   throttle); the brawler went from ~2 to ~50 median DMG-OUT and ~4× survival but
   never won. **Decision: stop tuning this matchup; balance re-emerges via depth**
   (drafting + asymmetric matchups + objectives). Do **not** open a fifth lever.
   PR #116 stays open with an **open merge decision** (the sniper-JSON fix is a
   standalone robustness win; the balance numbers may be superseded by depth). The
   brawler still needs a *reason and a way to close* — objectives, Assault keyword,
   movement multiplier — Phase 2 / Phase 2.5 work, not a bigger health bar. When a
   battery reruns, report winner-side distribution, not a single exciting ledger.
8. Decide and document whether `foundry_60` is sufficient for the first
   satisfying demo; if not, open a separate versioned-arena slice.
9. **Wire live learning for real — first-class, next session (operator: "it's
   necessary").** Not a scope question anymore. Instantiate
   `LiveLearningCoordinator` + a concrete `LiveLearningEvaluator`, add a closed
   `POLICY_PROMOTED` member to `SOEventType` so promotion folds from events, and
   connect the admission↔terminal seam (`begin_match` at admission, same instance
   receives the terminal) — closing blocker `learning-adaptation-01/02/03`. Design
   it **unified with depth**: the loop learns over the deck/draft decision space,
   and event-sourced replay makes promoted policies auditable ("replay why this
   policy got promoted") = the RSD / platform-proof thesis. Infra can start
   independently; efficacy rides on the depth decision space. Then run the
   before/after adaptation battery.

## Explicit deferrals

Kafka delegation (LLM plan R5) and the deferred omnimarket handler import (D3)
remain separate integration projects unless product scope is expanded. They
must not be used to mask a failing browser, provider, combat, learning, or UI
gate.

## 2026-07-28 session update — paper track queued

Queued this session; not scheduled, not staffed, no timeline commitment.

### Paper track — incentive-response program (operator-ratified queued 2026-07-28, OMN-15327)

- **Deliverable:** arXiv preprint + LLM-agents workshop paper from the
  preregistered incentive-response arc: display necessity (OBJ-MASK #215,
  ~0% payout-alone m=-0.0218; DECOY #210/#212, ~21% display-alone g=0.2115),
  incentive-dose interior optimum (vp_per_deploy ladder #205/#206/#209, peak
  vp4; truncation confound eliminated by #214), display-salience dose-response
  (arm-1, verification pending), and the falsified 4-round single-lever
  balance program as a first-class preregistered negative. Methods section
  leads with the reproducibility discipline: preregistration + dated
  amendments, contamination gates, deterministic event-sourced replay,
  hermetic frozen-environment execution, adversarial verification.
- **Trigger (findings-gated, not dated):** pick up when arm-1 is verified AND
  at least one headline result has a cross-model replication (crossarch
  batteries partially cover this); never inside the Aug 4-6 demo window.
  Known reviewer weaknesses to close before main-track: single bespoke
  environment, uneven cross-model coverage, n=30 corners.
- **When picked up:** draft from `docs/evidence/` (statistics already
  computed in the battery docs); position against prompt-sensitivity /
  reward-shaping literature; IP check is mechanism-scoped (findings are steel
  science, not RSD internals); venue/timing = operator decision.
