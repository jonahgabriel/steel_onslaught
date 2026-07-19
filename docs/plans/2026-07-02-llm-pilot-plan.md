# LLM Integration — ONEX-native pilots + learning-loop Phase 3 (LLM tuner)

> **Status:** Rev 5 — Phases A–C LANDED on this branch (commits
> `c4f8bc5..76879ff`); this revision reconciles the plan against the shipped
> code, registers divergences to remediate, and scopes remaining work.
> **Author:** generated 2026-07-02 (Rev 1); Rev 2 same day after a 7-agent
> research + adversarial-verification pass (5 research, 2 verify agents; all
> claims below carry file:line evidence from that pass or direct reads).
> **Depends on:** the ONEX restructure (Phases 0–5, landed on
> `feat/armor-degrading-pool`) and the initiative system.
>
> **Rev 2 changes (each forced by verified evidence, not taste):**
> 1. **ONEX-native + reuse-first.** Steel Onslaught is a demo of the OmniNode
>    architecture: every new capability lands as CONTRACT + NODE + HANDLER,
>    reusing the repo's existing primitives (spec registry, archetype
>    chokepoint, contract.yaml schema, EventBus protocol, evaluator seam)
>    and the platform's importable types (spi LLM protocol shapes, core
>    enums) instead of inventing parallels.
> 2. **`llm` becomes a first-class pilot archetype** (Rev 1 had it out of
>    scope, using a `pilots_override` bypass). Evidence killed the bypass:
>    pilots resolve at ONE chokepoint (`match/runner.py::_pilot_from_spec` ←
>    `PilotSpecRegistry.resolve`), shared verbatim by `so run` and the
>    learning loop's `run_duel` (`match/duel.py:62-78`). A 4th archetype
>    case there makes LLM pilots loadout-contract-driven everywhere with
>    zero duplicate plumbing; `pilots_override` would need duplication in
>    two constructors plus carries a silent-skip mis-key hazard
>    (`ReducerPilotTick` skips mechs with no pilot entry).
> 3. **Learning-loop Phase 3 (LLM tuner + context arms) is in scope** — the
>    already-designed loop (addendum §3.3) is the priority payload. The
>    injection seam already exists: `loop.py::run_enumeration(candidates:
>    Iterable[tuple[ParamDict, str]], generator_id)`.
> 4. **Sync httpx client, no async bridging** (adversarial verdict on the
>    spi `ProtocolLLMProvider` route — see §1).
> 5. Rev 1 review findings folded in: `_decision_payload` must be updated
>    for `rationale` (it enumerates fields; nothing "flows automatically"),
>    the decision model's required `reason_code`/`considered_actions` get
>    explicit LLM handling, transport failures hit the REMAIN fallback.
> 6. **(Rev 3) Bus-first evidence + transport lanes.** HTTP lives inside
>    the effect node's handler — the settled platform pattern
>    (`node_llm_delegation_call_effect` does exactly this in production).
>    What Rev 3 adds: every LLM request/response is published as
>    **evidence events on the game bus** (→ append-only ledger,
>    causation-chained, replayable), and the handler seam gains a **Kafka
>    delegation lane** — on infra-installed hosts (.201) a contract
>    override routes completions through the bus to the platform's
>    deployed delegation effect node instead of the game-local handler.
>    In-memory/local bus is the default; Kafka is the override (platform
>    doctrine).
> 7. **(Rev 4) Reuse everything — the infra exclusion is lifted.** The
>    game's earlier "Infra intentionally not pulled into this
>    single-process engine" pyproject line was an April MVP scoping choice,
>    not platform doctrine; operator overrode it (2026-07-02: "we should
>    reuse everything"). omnimarket is published to PyPI (release.yml →
>    `uv publish`; 0.4.3 live), so the game takes `omnimarket` as a normal
>    dependency and **imports the production LLM handler**
>    (`HandlerLlmDelegationCall` — no constructor, no DI, one
>    `handle(request) → typed terminal event/result` method) instead of
>    pattern-copying its code. The hand-written `LlmHttpClient` from Rev
>    2–3 is deleted from this plan. Endpoint/model/key resolution reuses
>    the platform's registry + overlay mechanism rather than a game-local
>    providers.yaml.
> 8. **(Rev 5) Post-implementation reconciliation.** An execution session
>    landed Phases A–C before Rev 4 was written/read — the shipped client
>    is game-local (`llm/client_http.py`), not the omnimarket import. Rev
>    5 adds the state-reconciliation section below: what landed, a
>    divergence register (with severities and corrective tasks), and the
>    remaining work including the operator's new experiment directions
>    from `HANDOFF.md` (cross-adaptation, eval-framework reuse).

> **Current reconciliation (2026-07-19, `origin/main` 8a920f8).** The Rev 5
> history below is retained as historical evidence. The following follow-up
> PRs are now landed and are the current implementation baseline:
>
> - [PR #39](https://github.com/jonahgabriel/steel_onslaught/pull/39),
>   commit `835d2a7`, adds the whole-round `ProgrammingPilot` seam for LLM
>   card plans. `LLMProgrammingPilot` accepts the closed JSON register-plan
>   shape, validates it through the canonical `program_for_seat` boundary, and
>   keeps explicit `raise` versus deterministic fallback policy.
> - [PR #40](https://github.com/jonahgabriel/steel_onslaught/pull/40),
>   commit `0629a4a`, adds contract-declared roster defaults (including human
>   options), public default projection, and multi-provider model composition
>   through injected DI capabilities. Selection is exact and fail-closed; no
>   provider identity is inferred from a string search.
> - [PR #41](https://github.com/jonahgabriel/steel_onslaught/pull/41),
>   commit `905524e`, wires durable context-arm artifacts. The artifact port
>   reads canonical replay traces, decision diffs, and promoted exemplars;
>   the filesystem adapter reads evaluation SQLite ledgers read-only and
>   lineage records deterministically, while the experiment CLI injects the
>   selected artifacts and carries the resulting context manifest hash into
>   experiment rows and usage sidecars.
> - [PR #42](https://github.com/jonahgabriel/steel_onslaught/pull/42),
>   commit `23bbe5c`, completes the frontend roster/default projection. The
>   public roster parser accepts explicit defaults and legacy projections that
>   omit them, while `MatchSetup` honors only the server-declared default and
>   performs no GLM/name inference. The legacy path remains empty/disabled
>   until an allowed option is explicitly selected.
> - [PR #43](https://github.com/jonahgabriel/steel_onslaught/pull/43),
>   commit `2a74c65`, reconciles this plan with the landed LLM pilot, roster,
>   and learning-loop slices; it is documentation-only.
> - [PR #44](https://github.com/jonahgabriel/steel_onslaught/pull/44),
>   commit `fba70f2`, refreshes the reconciliation after the frontend default
>   projection landed; it is documentation-only.
> - [PR #45](https://github.com/jonahgabriel/steel_onslaught/pull/45),
>   commit `e73c7c3`, adds strict overlay card-programmer bindings by seat and
>   pilot-spec reference. Composition resolves only explicitly bound `llm`
>   specs through the injected provider-client and persona graph, then threads
>   the resulting whole-round programmers into `CardRunnerAdapter`. Missing
>   bindings preserve deterministic priority programming; duplicate, disabled,
>   unknown, non-LLM, missing-client, and missing-persona bindings fail closed.
>   This slice does not change runner cadence, replay, event schemas, provider
>   endpoints, UI, deployment, or OCC. A telemetry observer remains a separate
>   deferred slice.
> - [PR #46](https://github.com/jonahgabriel/steel_onslaught/pull/46),
>   commit `3d63d2c`, ships explicit paced card cadence. With
>   `card_cadence="paced"`, the runner latches one complete card-round
>   emission and its causal specifications, then publishes exactly one register
>   per tick. Hand/plan rows are emitted on the first tick, the deck/previous
>   plans/round index commit only after the final register, and terminal
>   boundaries close a partial round with
>   `CARDS_DISCARDED(reason="cancelled:<reason>")` without committing partial
>   deck state. Replay groups lifecycle rows by the stable external causation
>   root across ticks and exposes a `cancelled` flag; the existing atomic cadence
>   remains the default. This slice does not change provider endpoints, UI,
>   deployment, or OCC.
> - [PR #47](https://github.com/jonahgabriel/steel_onslaught/pull/47),
>   commit `8a0b603`, refreshes the plan after the explicit card-programmer
>   composition landed and keeps paced cadence plus the telemetry observer
>   explicitly deferred as separate follow-up slices.
> - [PR #48](https://github.com/jonahgabriel/steel_onslaught/pull/48),
>   commit `01784e7`, reconciles the shipped paced cadence and makes the
>   browser-started live loop the next product gate while retaining the
>   telemetry deferral.
> - [PR #49](https://github.com/jonahgabriel/steel_onslaught/pull/49),
>   commit `3a292b8`, carries the selected atomic/paced card cadence through
>   the closed application overlay and runtime DI; paced cadence is rejected
>   unless card mode is explicitly enabled.
> - [PR #50](https://github.com/jonahgabriel/steel_onslaught/pull/50),
>   commit `6e616af`, composes the live browser server only through explicit
>   capability injection. `configured_live_browser_server` mints a fresh
>   per-start grant with a bounded multi-completion budget, and exact provider
>   and pilot IDs flow through selected runtime DI without ambient key or
>   endpoint discovery. The packaged/default path remains stub-safe and fails
>   closed when the live secret resolver and HTTP transport are not both
>   supplied. This slice does not change provider endpoints, UI, deployment, or
>   OCC.
> - [PR #52](https://github.com/jonahgabriel/steel_onslaught/pull/52),
>   commit `8a920f8`, lands match-scoped telemetry for explicit card-mode LLM
>   programmers. Composition creates a fresh `CardProgrammerFactory` after
>   match identity, event factory, and bus setup, wraps each selected provider
>   client with the canonical observed LLM effect, and clones the card adapter
>   without mutating shared runtime dependencies. Atomic and paced card modes
>   both prove one requested event followed by exactly one resolved/failed
>   terminal event per completion, with exact provider identity and replay
>   equality. Local proof covered the focused DI/composition suite (22 passed),
>   the non-proof-of-life suite (1800 passed, 2 skipped), Ruff, and mypy; hosted
>   CI passed Python, frontend, sanitize-text, and evidence-schema checks. The
>   existing proof-of-life browser test remains environment-blocked by the
>   missing `vite` executable; no provider, deploy, UI, or OCC mutation is part
>   of this telemetry slice.

## Rev 5 — state reconciliation (2026-07-02, post-implementation)

### Landed on this branch (commits `c4f8bc5`, `9461720`, `f3a08f0`, `9307a67`, `76879ff`)

855 tests green, `mypy --strict` clean, and a **live cross-model match
proven**: Qwen3.6-35B (berserker) vs Qwen3.6-27B (sniper) end-to-end, with
genuine strategic rationale stored in the ledger.

- `llm/` module: `schemas.py` (`ProtocolLlmClient`, usage model with
  `prompt_tokens`/`completion_tokens`/`cost_usd`), `stub.py`,
  `client_http.py` (`OpenAICompatibleClient` + `PROVIDER_ENDPOINTS`),
  `effect.py` (publishes `LLM_COMPLETION_REQUESTED/RESOLVED` evidence
  events), `pilot.py`, `personas.py` (in-code), `tuner.py`
  (batch-materialized, snap-to-lattice, dedupe), `context_arms.py` (all 5
  addendum arms), `contract.yaml`.
- `llm` as 4th archetype: `contracts/pilot.py` Literal + params model,
  `pilots/contract_llm.yaml`, `_pilot_from_spec` case; pilot-spec +
  loadout YAMLs under `contracts_data/` (qwen35/qwen27/deepseek/glm).
- Decision schema: `rationale` field (`pilots/schemas.py:173`),
  `LLM_DECISION`/`LLM_FALLBACK` reason codes (`schemas.py:61-62`),
  `_decision_payload` carries rationale (`reducers/pilot_tick.py:135`).
- Learning loop: `SOSearchStrategy.EXTERNAL` + explicit dispatch branch +
  materialized `candidates` param (`loop.py:56,170,306-308`);
  `so learn --generator llm --llm-arm <arm> --llm-provider <id>` works
  end-to-end. Determinism-boundaries doc updated. Python 3.12 alignment.

### Divergence register (remediation queue — severity-ordered)

> **Status reconciliation (2026-07-02, integration gate).** Five parallel lanes
> landed on `feat/armor-degrading-pool`; the full suite (901 passed, 2 skipped;
> `mypy --strict` clean; `ruff check`/`format` clean) is green modulo the
> pre-existing PoL Playwright timing flake (frontend-owned; see HANDOFF).
> D1/D2/D4/D5/D6 are DONE; D3 remains DEFERRED (sibling version misalignment).

| # | Divergence | Evidence | Sev | Corrective action | Status |
|---|---|---|---|---|---|
| D1 | Soft auth: `os.environ.get` + `if api_key:` sends **unauthenticated** requests when the key env var is unset, despite docstrings claiming fail-closed | `llm/client_http.py:76-80` | HIGH | Providers with a declared key ref must raise before the call — never silently unauthenticated | **DONE** — `_resolve_auth_header` raises `RuntimeError` on unset/empty declared `api_key_env` before any network call (`llm/client_http.py:120-135`) |
| D2 | Endpoint URLs (incl. lab Tailscale IPs) hardcoded in Python source via `PROVIDER_ENDPOINTS` | `llm/client_http.py:125-139` | HIGH | Move to contract YAML/overlay (all-URLs-from-contracts); interim: a game contract file, target: platform registry per Rev 4 | **DONE** — all endpoints moved to `llm/providers.yaml`, loaded + validated by frozen `ProviderEndpoint`; no URLs in Python source |
| D3 | Rev 4 reuse directive not applied — game-local client instead of imported omnimarket `HandlerLlmDelegationCall` (execution predated Rev 4) | `llm/client_http.py` exists; no omnimarket dep in pyproject | MED | Swap the lane impl per Rev 4 §1 (contained behind `ProtocolLlmClient`); delete `client_http.py` | **DEFERRED** — omnimarket import still blocked by sibling version misalignment (7 repos at different versions; `PackageNotFoundError`, confirmed by R5 probe §5). `client_http.py` retained behind the `ProtocolLlmClient` seam as the drop-in-replaceable workaround |
| D4 | Bare base_url + `"/chat/completions"` append | `llm/client_http.py:57,97` | MED | Complete-URL-verbatim; resolved by D2/D3 | **DONE** — `providers.yaml` `endpoint_url` is the complete chat-completions URL, posted verbatim (no rstrip, no path append) |
| D5 | Paid models routed via OpenRouter (`openrouter-claude` → `anthropic/claude-sonnet-5`, `openrouter-glm` → `z-ai/glm-5.2`) while direct z.ai entries exist | `llm/client_http.py:137-139` | MED | Routing doctrine: OpenRouter for free models only; GLM routes direct z.ai. Drop or mark experiment-only | **DONE** — paid-via-OpenRouter entries dropped; GLM routes direct to z.ai in `providers.yaml` |
| D6 | Personas in code, not contracts (self-acknowledged interim in its docstring) | `llm/personas.py` | LOW | Migrate to `pilots/personas/*.yaml` per §2 | **DONE** — personas migrated to `contracts_data/pilots/personas/{berserker,sniper,opportunist}.yaml`; `personas.py` now a contract loader (registry test covers it) |

### Remaining work

- **R1 — experiment harness** (§4.5–4.6): `so learn-experiment` — K=5
  seed-varied trials, deterministic baseline floor, ENFORCED
  negative-control arm, `ModelSOTunerUsage` cost sidecar, ROI-compatible
  row export incl. the 7 platform-required fields. — **DONE**: pure half in
  `llm/experiment.py`, effect boundary in `cli/experiment.py`, wired as
  `so learn-experiment`; `tuner.tune_with_usage` returns the usage sidecar.
- **R2 — divergence remediations D1–D6** (D1/D2 first). — **DONE except D3**
  (D1/D2/D4/D5/D6 landed; D3 deferred, see register above).
- **R3 — cross-adaptation experiment** (operator direction, HANDOFF §3):
  a pilot variant that ingests the *opponent's* decision history (ledger
  replay trace) into its prompt; measure whether exposure to B's history
  changes A's win rate on paired seed batteries. Infrastructure exists
  (`llm_replay_trace`/`llm_decision_diff` arm assemblers); needs a short
  design note + the measurement harness from R1. — **DONE**: `OpponentAwareClient`
  wraps the `ProtocolLlmClient` seam (no shipped pilot code edited);
  `cli/adaptation.py` runs paired seed batteries with a McNemar test, wired as
  `so run-adaptation`.
- **R4 — eval-framework reuse survey** (HANDOFF §2): inventory
  omnimarket/omniclaude/omniintelligence eval/benchmark machinery before
  building any cross-model scoring. — **DONE**:
  `docs/research/2026-07-02-eval-framework-reuse-survey.md`.
- **R5 — Phase E Kafka lane** (gate unchanged: verify live topics against
  the deployed .201 lane). — **PROBE DONE / BUILD DEFERRED**:
  `docs/plans/2026-07-02-kafka-delegation-lane-probe.md` (read-only). Gate is
  evidence-supported to proceed — all declared subscribe/publish topics and
  `node_llm_delegation_call_effect` are confirmed live on stability-test
  (`.201`) — but the command topic has **zero messages ever produced**; the
  first live-fire publish (a mutation) is the first step of the Phase E *build*,
  which remains unstarted. Recommendation: sync `confluent-kafka` client (not
  aiokafka), matching the game's hard-sync `decide()`/`EventBus` seam.
- **R6 — new event-flow UI** (operator, 2026-07-02): replace the frontend
  with an event-native view — live event river from the WS bridge with
  causation chains and LLM rationale as first-class display. Designed in
  foreground; implementation dispatched to an Opus agent workflow.
  — **UI-workflow-owned** (not part of this backend integration gate;
  `frontend/` changes are staged/committed by that workflow separately).

## Next — Gate 1 manual live browser proof (telemetry landed)

Paced card cadence is now shipped as an explicit runtime mode rather than a
plan item. The atomic cadence remains the default for callers that do not opt
into `card_cadence="paced"`. The shipped paced mode preserves these
invariants:

- latch the active round's seats, hand, deck state, plan, previous plan, and
  heat-lock context; do not deal or re-plan again between register ticks;
- emit `CARDS_DISCARDED` only after the final register, then commit the deck,
  previous-plan, and round-index state for the next round;
- group card lifecycle events by one stable causation root across ticks while
  retaining phase order, unique seat/register rows, and canonical
  `(tick, sequence_in_tick, event_id)` ordering;
- close or explicitly cancel an active round at decisive death or a
  `max_ticks` terminal boundary, retain lifecycle rows for seats that die
  mid-round, and void later intents without inventing a second hand or plan;
- distinguish committed discards from cancellation evidence in replay, so an
  incomplete round cannot be mistaken for a deck commit.

The next remaining product gate is **Gate 1: a manual browser-started live
loop against an actually injected real provider**. Card-mode LLM completion
telemetry is now landed and replay-proven for both atomic and paced cadence;
the gate remains a live-loop/UI integration proof rather than another backend
telemetry implementation task. The shipped
`configured_live_browser_server` path is intentionally explicit and
stub-safe: a packaged/default launch without the live secret resolver and HTTP
transport is not evidence of a real-provider match. Use an admitted
`MatchSetup`/`BrowserPlayServer` launch with both capabilities injected, then
prove through a Playwright/browser run that the authoritative event stream
arrives through the browser transport, advances through a long enough real
selected-model match (including the LLM-vs-LLM default lane), and reaches a
terminal projection. This is a live-loop/UI integration proof, not permission
to broaden the dashboard, change provider endpoints, or mutate
deployment/runtime infrastructure.

The telemetry observer remains deferred and independent of both the PR #45
composition seam and the shipped paced-cadence runtime. Its eventual contract
must consume the canonical event stream without becoming an alternate source of
match truth or changing replay semantics; it should follow the Gate 1 browser
proof rather than precede it.

## Core principle (verified, unchanged from Rev 1)

Replay reconstructs state by folding the **recorded ledger events** through
the pure fold. So replay is idempotent *by construction* — it does not matter
whether events were generated deterministically or by a coin-flipping LLM.

- `verify_replay_validity` (`reducers/scoring.py:209-220`) compares
  `ReplayEngine(ledger, match_id).reconstruct_at_tick(live.tick) == live` —
  ledger-consistency, never re-invoking a pilot. **The replay gate needs no
  change.**
- `MatchStateFold.delta` has **no case for `PILOT_DECISION_MADE`** — it falls
  to the no-op default (`match/fold.py:271-272`). Decision payloads never
  reach state, so new payload keys cannot perturb state equality or replay.
- **The tuner never touches match determinism.** LLM-proposed candidates are
  evaluated by the same deterministic seed batteries as ever; nondeterminism
  is confined to the generator — exactly where the addendum's experiment
  wants it (addendum §3.3: "the only randomness is in the generator").

## Two consumers, one seam

| | **LLM pilot** (§2–§4) | **LLM tuner** (§5, = learning-loop Phase 3) |
|---|---|---|
| What the LLM does | plays the game live, per tick | proposes candidate `ParamDict`s for heuristic pilots |
| Match determinism | cross-run relaxed; replay-validity holds | **fully preserved** |
| Graded by | nothing (it's the show) | existing evaluate→stats→gate→record loop, unchanged |
| Provenance | `PILOT_DECISION_MADE` + `rationale` in the ledger | `ModelSOLineageGenerator` (`llm.<model>@<arm>`) |

Both consume one LLM completion effect node (§1). Build it once.

## Design

### 1. LLM completion effect node — `src/steel_onslaught/llm/`

A new module **outside** `learning/` (a directory-wide source scan,
`tests/cli/test_learn.py:258-273`, bans the literal substring `datetime.now`
in every file under `learning/` — LLM timeout/clock code cannot live there).

**What we reuse (import, not copy):**

- **The production LLM handler, whole.** `omnimarket` is a normal PyPI
  dependency (published via its release.yml; 0.4.3 live), and
  `HandlerLlmDelegationCall`
  (`omnimarket/nodes/node_llm_delegation_call_effect/handlers/
  handler_llm_delegation_call.py:256`) is a plain class — **no
  constructor, no DI** — with one synchronous
  `handle(request: ModelLlmDelegationCallRequest) →
  ModelLlmDelegationCompletedEvent | ModelLlmDelegationAllTiersFailedEvent
  | ModelLlmDelegationCallResult` method that *returns* typed models
  rather than publishing (the runtime publishes what handlers return — and
  in the game, the game bus does). Everything Rev 2 was going to
  pattern-copy — verbatim-URL doctrine, required timeouts, the error
  taxonomy, usage/cost extraction, endpoint health probing — arrives by
  import, maintained upstream. Sync `handle`, sync `decide()`: no asyncio
  anywhere in the hot path (the spi `ProtocolLLMProvider` async surface
  remains unused; the source-scan guard in §Verification stays).
- **The platform's endpoint/model/key resolution.** Requests carry an
  `endpoint_ref`; resolution + overlay live in omnimarket
  (`resolve_delegation_backend` + registry + overlay, with the
  documented dev-overlay path). Local laptop providers (LM Studio/Ollama)
  are **overlay entries** on the platform's own mechanism — no game-local
  `providers.yaml` reinvented. Personas remain game contracts (§2); which
  `endpoint_ref` a pilot/tuner uses is a field in the game's pilot-spec /
  experiment config.
- **core enums** where the game's own models need them:
  `EnumMessageRole`, `EnumFinishReason`, `EnumResponseFormat`
  (`omnibase_core.enums` — already a dependency).
- **Dependency note (accepted, per operator directive):** omnimarket
  transitively brings omnibase-infra, aiokafka, asyncpg, fastapi, etc. The
  game's pyproject line "Infra intentionally not pulled into this
  single-process engine" is deleted as part of this work. The transitive
  aiokafka also dissolves Phase E's dependency gate. Two mechanical checks
  at build time: `requires-python` compatibility, and pinning
  `omnimarket>=0.4.3` with the same pin-discipline as core/spi.

**The node (branch's established contract pattern, effect template =
`ledger/contract.yaml`):**

- `llm/contract.yaml` — `node_type: effect`, `descriptor: {node_archetype:
  effect, purity: impure, idempotent: false, timeout_ms: <from provider>}`,
  `handler: steel_onslaught.llm.effect:LlmCompletionEffect`,
  `metadata: {transport_type: in_process}`. Use exactly `effect` — do not
  repeat the leaderboard's `node_archetype: projection` divergence from the
  four canonical archetypes (`EnumNodeArchetype`: compute/effect/reducer/
  orchestrator, `omnibase_core/enums/enum_node_archetype.py:54-58`, where
  COMPUTE = "Pure data transformation" and EFFECT = "External I/O
  operations: API calls" — the citation for why an LLM call is an effect).
- `llm/schemas.py` — `ProtocolLlmClient` (runtime-checkable, one sync
  method `complete(request) -> response`) + the request/response models
  above, with `prompt_tokens`/`completion_tokens`/`cost_usd` carried in
  `usage_statistics` so the tuner's `cost_per_promotion` has a source of
  truth from day one.
- `llm/effect.py` — `LlmCompletionEffect`, the game-side adapter node. It
  maps the game's request (persona/arm prompt + `endpoint_ref` from the
  spec) to `ModelLlmDelegationCallRequest`, invokes the configured **lane**
  behind the game's `ProtocolLlmClient` seam, maps the returned terminal
  model back (completed → text + usage; failure classes → the REMAIN
  fallback in §2), and publishes the evidence events (below) on the game
  bus. Which lane is active is contract configuration, never code:

  - **In-process lane (default) — the imported production handler.**
    `HandlerLlmDelegationCall().handle(request)` called directly — the
    real platform node composed into the game process, the same code that
    runs in production. Nothing is reimplemented; the game does not own
    URL discipline, timeouts, error taxonomy, health probes, or usage
    extraction — omnimarket does.

  - **Kafka delegation lane (contract override, infra hosts) — Phase E.**
    Where infra runs (.201), the override publishes the same
    `ModelLlmDelegationCallRequest` wire DTO (imported — no guessed
    envelope shapes) to the deployed node's request topic and consumes the
    terminal event. Same handler code either way; the only difference is
    which process runs it. The former dependency gate is gone (aiokafka
    arrives transitively with omnimarket); the remaining gate is verifying
    the live topic names + consumer wiring against the deployed .201 lane
    before building.

  - **Stub lane — `llm/stub.py::StubLlmClient`:** table-driven, fail-fast
    (KeyError on unscripted input — the repo's `FakeEvaluator` stub
    convention, `learning/fake_evaluator.py:9-32`). All pilot + tuner logic
    is developed offline against it.

**Evidence events (all lanes).** The effect node publishes
`LLM_COMPLETION_REQUESTED` (prompt, model, provider, persona/arm,
correlation) and `LLM_COMPLETION_RESOLVED` (text, finish reason, usage,
latency, failure class on fallback) on the game `EventBus`. During a match
they land in the append-only ledger with causation chains like every other
event; `MatchStateFold` ignores them (default no-op case,
`match/fold.py:271-272`), so state equality and `verify_replay_validity`
are untouched, and ordering is owned by `(tick, sequence_in_tick)`, which
the bus re-stamps. Every prompt and completion becomes durable,
inspectable ledger evidence — and this opens a future `RecordedLlmClient`
lane that serves completions straight from a recorded ledger
(deterministic re-run of an LLM match with no network).

**Invocation stays a direct handler call in-process.** `decide()` must
return a decision within the tick; a request/response round-trip *through*
the synchronous in-process bus would re-enter `publish()` mid-cascade. So
in-process composition wires the effect node into the pilot the way
`assemble_match_live` already wires the ledger and scoring callables —
direct typed calls — while the bus carries the *evidence* (all lanes) and,
on the Kafka lane, the *transport*.

**Provider registry: the platform's, via overlay.** No game-local
`providers.yaml`. The game ships overlay entries for local providers
(LM Studio / Ollama complete-URL endpoints, no key) through omnimarket's
own registry + overlay mechanism, inheriting its conventions for free:
complete URLs verbatim, `api_key_ref` name-not-value resolved fail-closed
at the effect boundary, pricing metadata for cost telemetry. Default
entries are local-first, cloud opt-in — the addendum's routing posture and
the org's no-Anthropic/OpenAI-key constraint. Swapping providers is an
overlay edit. (Build-time check, not a design question: confirm the exact
overlay file/namespace `_resolve_endpoint` reads for game-local refs.)

### 2. The LLM pilot — a 4th archetype, not a bypass

**`llm` joins `ModelSOPilotSpec.archetype`** (`contracts/pilot.py:97`
Literal + `_ARCHETYPE_PARAMS` entry) with a params model
`ModelSOLlmPilotParams{persona: str, provider: str}` (categorical, not
tunable), and a 4th case in `_pilot_from_spec`
(`match/runner.py:117-130`):

```python
case "llm":
    return LLMPilot.from_spec(spec)   # resolves persona + provider contracts, fail-fast
```

Consequences, all free:

- **LLM matches are loadout-contract-driven.** A pilot-spec YAML
  (`archetype: llm, parameters: {persona: berserker, provider: lmstudio}`)
  referenced from a loadout YAML is all it takes —
  `so run --loadout-a llm_berserker.yaml --loadout-b sniper_vs.yaml`.
  No new CLI flags required (optional sugar can come later). Heuristic vs
  LLM, LLM vs LLM: just contracts.
- **Both entry points work identically** (`so run` and `run_duel` resolve
  through the same chokepoint). The learning loop does NOT tune LLM pilots
  (out of scope; `so learn --archetype` stays a closed choice of the three
  heuristic archetypes).
- The unknown-archetype `ValueError` in `_pilot_from_spec` keeps failing
  loudly — no silent-skip hazard.

**`pilots/llm.py` + `pilots/contract_llm.yaml`.** `LLMPilot` implements the
existing `PilotProtocol.decide(observation) -> ModelSOPilotDecision`
(`pilots/schemas.py:246-249` — single sync method, exactly the seam):

1. Serialize the observation compactly (own hp/heat/pressure/weapons/mode +
   noisy enemy readings); prepend the persona system prompt, which also pins
   the required JSON response shape (`EnumResponseFormat.JSON`).
2. Invoke the LLM effect node (whichever lane its contract configures);
   parse; validate the action against `available_actions(observation)`
   (`pilots/schemas.py:202`).
3. Return the decision with `reason_code=LLM_DECISION`,
   `considered_actions=[]` (the LLM's alternatives live in prose in
   `rationale`; the scored list is a heuristic concept), `rationale` set.
4. **Any failure — timeout, connection error, auth, malformed JSON, invalid
   or out-of-vocabulary action — degrades to REMAIN** with
   `reason_code=LLM_FALLBACK` and a `rationale` naming the failure class.
   `decide()` is called synchronously inside the tick loop
   (`reducers/pilot_tick.py:234`); an unhandled exception kills the match,
   so the wrap covers the *entire* complete→parse→validate pipeline.

`contract_llm.yaml` declares `node_type: effect, purity: impure,
idempotent: false` — the honest archetype (network I/O in `decide()`),
citing `EnumNodeArchetype` semantics. The existing heuristic pilot
contracts stay `compute/pure`; the metadata now *distinguishes* them, which
is itself the demo beat. One scope note for honesty: the game's
contract+handler pattern (domain-typed `decide()`/`append()` methods, not
the platform's literal `ProtocolMessageHandler.handle(envelope) →
ModelHandlerOutput`) is a **project-local convention** consistent with the
branch's prior phases — steel_onslaught sits outside the Repository
Registry and the compat→core→spi→infra layering the canonical doc binds;
we state that in the contract comments rather than claiming a doctrine
carve-out that doesn't textually exist.

**Personas — `pilots/personas/*.yaml`** (berserker, sniper, opportunist):
`persona_id`, `display_name`, `system_prompt`, optional `temperature`
override; loaded by a registry mirroring `PilotSpecRegistry.load()`. Adding
a persona = dropping a file.

**Latency honesty:** up to `max_ticks × 2` serial LLM calls per match. LLM
loadouts should ship with guidance to run `--max-ticks 60`; the CLI renderer
already streams per-tick output, so the match is watchable while it runs.

### 3. Decision schema + payload (the Rev 1 corrections)

- `ModelSOPilotDecision` (frozen, `extra="forbid"`,
  `pilots/schemas.py:154-174`): add `rationale: str | None = None`.
  Heuristic pilots leave it `None`. (An open-dict smuggle via
  `action_params` was considered and rejected — typed field, honest schema.)
- `SOPilotReasonCode`: add `LLM_DECISION`, `LLM_FALLBACK`.
- `reducers/pilot_tick.py::_decision_payload` (line 123): add
  `"rationale": decision.rationale`. This is the load-bearing fix — the
  payload dict is hand-enumerated; nothing flows "automatically" at the
  source. *Downstream* of the payload it genuinely is automatic: the
  envelope payload is an untyped `dict[str, Any]` JSON-round-tripped by the
  ledger and re-serialized whole by the REST inspector and WebSocket bridge
  (`cli/serve.py:104,211`), and the fold ignores the event type entirely.
  The LLM's reasoning becomes durable, replayable evidence in the same
  append-only ledger as everything else.
- `PilotProtocol` docstring: "deterministic mapping" → decision mapping;
  per-implementation determinism is now declared by each pilot's contract
  (`descriptor.purity`), which is the authority.

### 4. Learning-loop Phase 3 — the LLM tuner (addendum §3.3, implemented)

The loop machinery is reused **unchanged**: statistics, promotion gate
(generator-agnostic per addendum §18/§23.1 — no separate Phase 3 bar),
lineage records, `DuelEvaluator`. What Phase 3 adds is a candidate
*generator* and its measurement harness.

**4.1 The seam (pure side).** `run_learning_loop`
(`learning/loop.py:161-169`) gains
`candidates: Iterable[tuple[ParamDict, str]] | None = None` and
`generator_id: str | None = None`, plus `SOSearchStrategy.EXTERNAL` with an
**explicit dispatch branch** — the current tail is a bare
`if/elif/else` where `else` = random_restart (`loop.py:295-310`), so a
missing branch would *silently misroute EXTERNAL runs into random_restart*
(adversarial finding). The branch raises `ValueError` if `candidates` or
`generator_id` is absent (and vice-versa for non-EXTERNAL strategies).
Purity is preserved: `Iterable` is already imported (`loop.py:22`), and the
source-scan bans (`tests/learning/test_loop.py:502-520` — no
time/datetime/pathlib/os/io/sys imports, no global random) are untouched.
A canned-iterator test proves the seam is behavior-neutral vs GRID given
identical candidates.

**4.2 Batch materialization, not lazy I/O (adversarial verdict C3).** A
lazy LLM-backed iterator inside `run_enumeration` was REFUTED as designed:
the loop never feeds results back (multi-turn feedback is impossible
through a plain `Iterable`), a mid-iteration network error would escape
`cli/learn.py`'s `except (ValueError, ValidationError)` as an uncaught
traceback discarding all evaluated candidates, and the budget-break /
dedupe-`continue` paths would silently burn extra inference calls. Ruling:
**the tuner fully materializes each proposal batch BEFORE
`run_learning_loop` is called.** All LLM I/O happens at the CLI effect
boundary, wrapped in the client's error taxonomy; the pure loop receives a
plain list. Multi-turn feedback ("your last batch lost 7/10") is explicitly
out of scope — none of the addendum's five arms requires it; it would need
a `send()`/callback seam and is deferred to a future design.

**4.3 The tuner — `llm/tuner.py`.** Given
`(archetype, parent_params, bounds, arm, provider)`:

1. Assemble the arm's context (§4.4); render the prompt: parameter names,
   current values, bounds + step lattices, "propose N improved parameter
   sets as JSON" (N sized to `max_evaluations - 1` so the batch matches the
   budget; the gate slot is reserved by the loop).
2. One `complete()` call via the effect node (stub-testable).
3. Parse proposals → **snap each numeric to the bounds lattice** (nearest
   `minimum + k*step`, clamped; categorical values must match a declared
   choice or the proposal is dropped). Off-lattice output is expected, not
   exceptional — `search.py::_find_lattice_index` raises on off-lattice
   values, so snapping happens here, before the loop sees anything.
   Pre-dedupe (against parent + within batch) so budget slots aren't wasted.
4. Return `[(params, selection_reason), ...]` with
   `selection_reason = "llm_proposal"` (or `"llm_proposal:snapped"`), or
   `"experiment_assignment"` under a forced cohort (addendum §7, verbatim
   requirement). `generator_id = "llm.<model>@<arm>"` — the addendum's
   format, recorded on every lineage record via the existing
   `ModelSOLineageGenerator{generator_id, selection_reason, cohort}`.

**4.4 Context arms — `llm/context_arms.py`, verbatim from addendum §3.3:**

| Arm | Context | Source artifact (all durable, all already exist) |
|---|---|---|
| `llm_off` | task statement only | bounds + parent spec |
| `llm_replay_trace` | + per-tick `PILOT_DECISION_MADE` payloads of the parent's *lost* duels | match ledgers (SQLite) |
| `llm_decision_diff` | + where parent decisions diverged from the winning opponent's, same seeds | ledgers + fold |
| `llm_exemplar` | + promoted lineage records (winning specs + deltas vs parents) | lineage store |
| `llm_full_design_doc` | full game design doc — **NEGATIVE CONTROL** | docs/ |

Every experiment run carries the negative-control arm (addendum hard
requirement: "a run without one is not a valid effectiveness experiment").
The arms consume exactly the artifacts the ONEX architecture produces
anyway — ledger, fold, lineage store feeding each other is the demo.

**4.5 Experiment harness + measurement.** `so learn --generator llm --arm
<arm> --llm-provider <id>` for one run; `so learn-experiment` runs the full
arm matrix + the deterministic baseline arm and emits the comparison table.
Design decisions the addendum left open, now pinned (research findings):

- **K = 5 trials per arm** (the platform ROI plan Phase 3 requires K ≥ 3
  and "state the chosen K" as an acceptance criterion; neither game doc had
  declared one). Baseline-arm variance requires **varying `master_seed`
  across the K trials** — a single seed yields zero variance by
  construction; the experiment command derives K master seeds from one
  experiment seed.
- **Headline metrics:** `attempts_to_promotion` (= `evaluations_consumed`
  until promotion — the field Phase 2 recorded precisely as "Phase 3's
  baseline-arm floor") and `cost_per_promotion` (from the client's usage
  fields; compute-only for baseline), **plus `first_batch_promotion_rate`**
  (did the arm's first proposal batch contain a promotable candidate) —
  added because the ROI plan explicitly headlines first-pass-success and
  cost-per-success over mean-attempts, and the addendum's metric pair
  otherwise mirrors the ROI plan's *deprioritized* metric.
- **Statistical bar unchanged:** decisive n ≥ 10, p ≤ 0.05, the no-overclaim
  format — arm-effectiveness claims are governed by the same gates as
  promotions (addendum §4.3; no looser Phase 3 bar exists).
- **Honest divergence note:** the addendum's 5 arms do not structurally
  mirror the ROI plan's 7-row *cumulative* factor matrix (no cumulative
  arms, no ARCHITECTURE_PATTERNS analogue). We implement the addendum's 5
  as designed and record the divergence in the experiment doc rather than
  silently claiming matrix parity.

**4.6 Cost + ROI row export (adversarial verdict C6).** Per-run LLM usage
is written as a **YAML sidecar at the CLI persistence boundary** next to
the lineage record — the addendum places token/cost fields on the
experiment ROW export, not on `ModelSOLineageRecord` (whose field list has
no cost field, and whose wall-clock-at-persistence precedent this follows).
The frozen lineage schema and pure loop are untouched. The row export
targets `node_context_roi_compute` compatibility and therefore carries the
**7 fields the addendum's summary omits** but the platform schema requires:
`failure_stage`, `endpoint_ref`, `factor_subset_hash`,
`prompt_template_version`, `routing_overlay_hash`, `temperature`,
`run_order` — plus the addendum's own list (`attempt_count`,
`first_pass_success`, `final_success`, token/cost, `model_id`, `provider`,
`context_factor_subset`, `run_id`/`correlation_id`, context-manifest hash).
Live export INTO the platform node stays out of scope (that node's build
status must be re-verified first); the game emits schema-compatible rows.

### 5. Determinism boundaries (documentation update)

`docs/plans/2026-07-02-determinism-boundaries.md` currently declares exactly
two wall-clock/nondeterminism sites (`emitted_at`, `recorded_at`). Add the
third: **the `llm/` module is a declared nondeterminism + wall-clock
boundary** (LLM sampling, request timing). State:

- Replay-validity: UNCHANGED, still the gate (holds for rationale-bearing
  ledgers — fold ignores the event type).
- Cross-run determinism: HOLDS for heuristic pilots; DOES NOT HOLD for
  `archetype: llm` matches; the byte-identical-stdout CLI test remains
  heuristic-only and says so.
- Learning loop incl. Phase 3: match-level determinism FULLY PRESERVED;
  only candidate *selection* is nondeterministic, and every lineage record
  pins `candidate_params` + `spec_hash`, so any recorded evaluation is
  exactly re-runnable after the fact.

## Execution order

Phase A is the shared seam; B and C are independent after A (disjoint
files, parallel-safe). C is the priority payload; B is the show-piece.

**A — LLM effect node:** (1) `omnimarket` dependency + pyproject
"infra-free" line removal; (2) `llm/schemas.py` (game-side seam models +
`ProtocolLlmClient`) + `llm/stub.py`; (3) `llm/effect.py` (request
mapping, imported `HandlerLlmDelegationCall` in-process lane, evidence
events) + `llm/contract.yaml` + local-provider overlay entries.

**B — LLM pilot:** (4) schema/payload changes (§3, additive); (5) `llm`
archetype registration (Literal + `_ARCHETYPE_PARAMS` + `_pilot_from_spec`
case) + `pilots/llm.py` + `contract_llm.yaml` + persona contracts + example
pilot-spec/loadout YAMLs, all against the stub.

**C — learning-loop Phase 3:** (6) `SOSearchStrategy.EXTERNAL` + explicit
branch + `candidates`/`generator_id` params (pure; canned-iterator parity
test); (7) `llm/tuner.py` (batch-materialized, snap-to-lattice, pre-dedupe)
+ `llm/context_arms.py`, against the stub; (8) `so learn --generator llm
--arm ...`, `so learn-experiment` (K=5, seed-varied baseline, negative
control enforced), usage sidecar + ROI-compatible row export.

**D — docs + demo:** (9) determinism-boundaries update; (10) demo script:
LLM-vs-LLM persona match + one tuner experiment against a local model.

**E — Kafka delegation lane (gated, optional; no other phase depends on
it):** `LlmBusDelegationClient` behind the same `ProtocolLlmClient`,
publishing the imported `ModelLlmDelegationCallRequest` DTO to the
deployed node's topic and consuming the terminal event. The dependency
gate is gone (aiokafka arrives transitively with omnimarket); the one
remaining gate is verifying live topic names + consumer wiring against
the deployed .201 lane before building. Until then, infra hosts work via
the in-process lane pointed at .201's model endpoints.

## Verification

- **A:** stub round-trip; adapter tests — game request → correct
  `ModelLlmDelegationCallRequest` mapping, each returned terminal model
  (completed / all-tiers-failed / failure result) → correct game-side
  outcome incl. REMAIN-fallback classes (transport/URL/timeout/taxonomy
  behavior itself is omnimarket's test surface, not re-tested here);
  overlay-resolved local endpoint_ref round-trip against a recorded
  fixture; evidence events published on both success and fallback and
  present in a match ledger, with `verify_replay_validity` passing on a
  ledger that contains them; **source-scan: no `asyncio` import anywhere in
  `llm/`** (the C2 latent-hazard guard, mirroring the repo's source-scan
  convention).
- **B:** stub-based `LLMPilot` tests — parse/validate/REMAIN-fallback per
  failure class; `rationale` present in `PILOT_DECISION_MADE` ledger rows
  and REST inspector output; a full stub LLM-vs-LLM match passes
  `verify_replay_validity`; unknown-archetype still raises; heuristic
  matches byte-identical (existing suite untouched, green).
- **C:** EXTERNAL-vs-GRID parity on identical canned candidates;
  EXTERNAL-without-candidates (and candidates-without-EXTERNAL) raise;
  snap-to-lattice property tests (arbitrary floats land on-lattice,
  in-bounds; categoricals validated); purity source-scans green (`loop.py`
  token bans; no `datetime.now` under `learning/` — tuner lives in `llm/`);
  determinism chain `test_learn_e2e.py` green, unchanged; end-to-end
  stub-tuner run promotes and writes a lineage record with
  `generator_id="llm.stub@llm_off"` + usage sidecar + row export with all
  required fields.
- **Live (manual):** one persona match and one `so learn-experiment`
  against a local endpoint; table shows all 5 arms + baseline floor +
  negative control, `attempts_to_promotion`/`cost_per_promotion`/
  `first_batch_promotion_rate` per arm.

## Out of scope

- The learning loop driving LLM *pilots* (nondeterministic duels break
  side-swap symmetry — separate design), and tuning the `llm` archetype's
  params (persona/provider are categorical identity, not a search space).
- Multi-turn tuner feedback (needs a `send()`/callback seam — none of the
  five arms requires it; noted for a future revision).
- Live row export into the platform's `node_context_roi_compute` (emit
  schema-compatible rows only; the node's build status needs re-verification).
- Cumulative ROI-matrix arms beyond the addendum's five (divergence
  documented, not silently patched).
- Frontend rendering of `rationale` (flows through serialization already).
- Anthropic-native client (the Protocol seam makes it a drop-in; the org
  has no Anthropic/OpenAI API keys — OpenAI-compatible covers local +
  Gemini-compat endpoints).
