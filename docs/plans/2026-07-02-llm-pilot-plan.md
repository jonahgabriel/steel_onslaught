# LLM Integration — ONEX-native pilots + learning-loop Phase 3 (LLM tuner)

> **Status:** Rev 3, awaiting review/iteration.
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

**What we reuse instead of inventing:**

- **spi protocol shapes, satisfied structurally.** The game's frozen
  models mirror `ProtocolLLMRequest` / `ProtocolLLMResponse`
  (`omnibase_spi/protocols/types/protocol_llm_types.py:60-127` — import via
  full submodule path; they are not re-exported at package level):
  request = `prompt, model_name, parameters, max_tokens, temperature`;
  response = `generated_text, model_used, usage_statistics, finish_reason,
  response_metadata`. Structural satisfaction (Protocols) means the game's
  types ARE valid spi LLM types without inheritance or an spi runtime
  import in the hot path.
- **core enums:** `EnumMessageRole` (user/system/assistant),
  `EnumFinishReason`, `EnumResponseFormat` (TEXT/JSON) from
  `omnibase_core.enums` (importable; already a dependency —
  `pyproject.toml` wires omnibase-core>=0.46.2 as a workspace path dep).
- **NOT reused, with reason:** spi's `ProtocolLLMProvider` full surface
  (13 methods, `generate` is `async def`). Adversarial verdict: bridging it
  through `asyncio.run()` inside the synchronous `decide()` is safe *today*
  (no execution path — `so run`/`so learn`/`so replay`/pytest — calls
  `decide()` inside a running loop; `so serve` runs the only loop and never
  constructs a `MatchRunner`), but that is a **latent, unenforced
  invariant**. Ruling: the client is a plain **sync `httpx.Client`** behind
  the spi request/response *shapes*; no `asyncio` anywhere in `llm/`
  (guarded by a source-scan test, §Verification). Core/spi ship **zero
  concrete clients** (verified: no openai/anthropic/genai imports, no live
  HTTP LLM code in either repo), so a hand-written handler is required, not
  a choice.

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
- `llm/effect.py` — `LlmCompletionEffect`, the node's handler. It resolves
  the provider entry, invokes the configured **lane client**
  (`ProtocolLlmClient`), and publishes the evidence events (below) on the
  game bus. Which lane is active is contract configuration, never code:

  - **Local HTTP lane (default) — `llm/client.py::LlmHttpClient`.**
    The standard effect-handler HTTP call, pattern-copied (not imported)
    from the platform's canonical reference,
    `omnimarket/.../node_llm_delegation_call_effect/handlers/transport.py`
    + `handler_llm_delegation_call.py`. The game ships its own handler
    because core/spi ship no concrete client (verified) and this repo does
    not depend on omnimarket/infra; on infra hosts the Kafka lane reuses
    the deployed platform handler instead. Behaviors copied verbatim:
    - **fail-closed verbatim-URL check** before any network call (URL must
      start with http(s)://; posted byte-for-byte, no rstrip/append —
      OMN-12815/13159 doctrine);
    - **required timeout, no default** (caller supplies the
      contract-resolved value);
    - single `httpx.Client(...).post(...)` + `raise_for_status()` +
      `response.json()`; **exactly one call, no retry** (the reference
      handler's own doctrine: retries/escalation belong to orchestration,
      never the transport);
    - error taxonomy: `httpx.TimeoutException` → timeout; `HTTPStatusError`
      429 → rate-limited, **401/403 → auth-failed** (fixing a classification
      gap the reference itself has), other statuses → provider-unavailable;
      empty `choices` → invalid-response; anything else → unknown;
    - usage extraction: `usage.get("prompt_tokens"/"completion_tokens") or 0`.
    Behaviors deliberately skipped (platform-scale overkill): curl/httpx
    dual transport (macOS-LAN-grant workaround), Infisical/
    ProtocolSecretStore DI, tier-ladder escalation, YAML pricing registry
    (per-1M prices live as optional fields on the provider entry instead),
    Kafka provenance.

  - **Kafka delegation lane (contract override, infra hosts) — Phase E.**
    Where infra is installed (.201), the override routes completions
    through the bus to the platform's **already-deployed**
    `node_llm_delegation_call_effect` instead of game-local HTTP: the lane
    client (`LlmBusDelegationClient`, same `ProtocolLlmClient`) publishes
    the delegation request event and consumes the terminal response event.
    The game-side HTTP client is bypassed entirely; the platform node does
    the POST, key resolution, and usage metering it already does in
    production. Two prerequisites make this a gated phase rather than the
    default: (a) the game takes an **optional** Kafka client dependency (an
    extra — the base install stays infra-free per the repo's own pyproject
    doctrine), and (b) the delegation request/response topics + wire DTOs
    must be consumed from the platform's contract, verified against the
    live deployed lane before building — no guessed envelope shapes.

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

**Provider registry is a contract, not env vars** — `llm/providers.yaml`,
mirroring the *shape conventions* of omnimarket's `model_registry_v1.yaml`
(pattern only; nothing imported): each entry = `provider_id`, **complete**
`endpoint_url` verbatim including the `/v1/chat/completions` path,
`model_name`, `temperature`, `max_tokens`, `timeout_ms`, optional
`pricing_per_1m_input/output`, and `requires_api_key_env` — the env var
**name**, never a value; resolved fail-closed at the effect boundary (raise
on required-but-absent, never call unauthenticated). Default entries are
local-first (LM Studio / Ollama on localhost, no key), cloud opt-in — the
addendum's own routing posture and the org's no-Anthropic/OpenAI-key
constraint. Swapping providers is a YAML edit.

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

**A — LLM effect node:** (1) `llm/schemas.py` shapes (spi-structural) +
`ProtocolLlmClient`; (2) `llm/stub.py`; (3) `llm/effect.py` (lane
resolution + evidence events) + `llm/client.py` (local HTTP lane) +
`llm/contract.yaml` + `llm/providers.yaml`.

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
it):** `LlmBusDelegationClient` behind the same `ProtocolLlmClient`. Two
explicit decisions gate it: the optional Kafka dependency (packaged as an
extra so the base install stays infra-free), and the platform delegation
topic/DTO contract verified against the live deployed .201 lane. Until
then, "infra installed" hosts still work via the local HTTP lane pointed
at .201's model endpoints.

## Verification

- **A:** stub round-trip; client tests against a recorded OpenAI-compatible
  response fixture; verbatim-URL fail-closed test (bare host without path
  rejected); required-timeout test; each error-taxonomy branch; fail-closed
  missing-key; evidence events published on both success and fallback and
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
