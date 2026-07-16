# Eval-framework reuse survey (R4)

> Research task for `docs/plans/2026-07-02-llm-pilot-plan.md` R4 (HANDOFF.md §2).
> Scope: read-only survey of `omnimarket`, `omniclaude`, `omniintelligence` for
> eval/benchmark/judge/scoring/model-comparison machinery reusable for
> cross-model strategy comparison in Steel Onslaught (LLM-vs-LLM match
> outcomes, persona/provider leaderboards). No code changed by this survey.

## Method

`grep -rniE` for `eval|benchmark|judge|quality_gate|scoring|model_comparison|
leaderboard|elo_rating|win_rate|pairwise` across `src/` in all three repos,
narrowed by directory/file name matches, then direct reads of the handlers
behind the most promising hits. Also checked steel_onslaught's own
`reducers/scoring.py` and `projections/leaderboard/handler.py` (Task
29/30, already landed) as the in-repo baseline any cross-repo candidate has
to beat.

**Headline finding, stated first:** none of the three repos contain a
pairwise contest / win-loss / ELO concept for LLM-vs-LLM outcomes. Every hit
is one of three shapes — (a) single-request code-generation quality scoring,
(b) two-path delegation A/B (frontier vs cheap, not model-vs-model), or (c)
shadow-vs-active routing-policy promotion with statistical significance.
`grep -rniE "elo_rating|win_rate|leaderboard|match_outcome|pairwise"` across
all three `src/` trees returns **zero** ELO/leaderboard/match_outcome hits;
the only `win_rate` hit is `node_objective_ab_framework_compute` (shadow
vs. active policy promotion, see below) and the only `pairwise` hits are
`itertools.pairwise` and clustering-similarity math — false positives.

## Candidates read in depth

### 1. `omnimarket.nodes.node_llm_eval_harness` (`NodeLlmEvalHarness`)

**What it does:** runs a fixed corpus of reference tasks (code-gen,
classification, contract-yaml, test-gen) through each of N models via an
injected `ProtocolLlmClient.complete(model_key, prompt) -> str`, scores each
output deterministically (ruff/mypy pass for code, substring match for
classification), and exposes a `.summary` property that rolls samples up
into `{model_key: {task_type: mean_score}}`.

**Import path:** `omnimarket.nodes.node_llm_eval_harness.handlers.handler_llm_eval_harness.NodeLlmEvalHarness`
(`omnimarket/src/omnimarket/nodes/node_llm_eval_harness/handlers/handler_llm_eval_harness.py`).

**Dependency weight:** light and self-contained — `pydantic`, stdlib
(`subprocess`, `tempfile`, `pathlib`, `re`, `statistics.mean`), no
`omnibase_infra`/`omnibase_core` import, synchronous `def handle`, no
network client of its own (client is injected via Protocol).

**Reuse fit:** structurally the closest thing to a "per-model leaderboard
rollup" in any of the three repos — the `{model_key: {dimension: score}}`
aggregation shape is exactly what a persona/provider leaderboard needs.
But the *scoring itself* is single-shot code/text-quality scoring
(ruff/mypy/substring-match against a fixed prompt corpus), not "did this
model win a multi-tick tactical duel against another model." There is no
concept of two models competing against each other in the same evaluation
unit; each model is scored independently against a static rubric.

**Friction:** would need the scoring functions (`_score_code_output`,
`_score_substring_output`) thrown away entirely and only the rollup shape
borrowed. `_score_code_output` shells out via `subprocess.run(["ruff",
...])`/`subprocess.run(["mypy", ...])` and writes to `tempfile` — importing
this module would pull `subprocess`/`tempfile`/`pathlib` transitively into
anything that imports it, which is fine outside `learning/`/`loop.py` but
buys nothing since none of that logic applies to match scoring.

### 2. `omnimarket.nodes.node_model_comparison_runner` (`HandlerModelComparisonRunner`)

**What it does:** fans a single task/prompt out to N model endpoints in
parallel (`asyncio.gather`), collects `ModelComparisonCell` rows
(tokens/latency/cost/error per model), and picks a `winner_label` by
`min(fewest_tokens, then lowest cost)` (`_pick_winner`).

**Import path:** `omnimarket.nodes.node_model_comparison_runner.handlers.handler_model_comparison.HandlerModelComparisonRunner`
(`omnimarket/src/omnimarket/nodes/node_model_comparison_runner/handlers/handler_model_comparison.py`).

**Dependency weight:** heavy. `async def handle`, `asyncio.gather`, and its
default-DI fallback path constructs `omnibase_infra.mixins.mixin_llm_http_transport.MixinLlmHttpTransport`
+ `omnibase_infra.nodes.node_llm_inference_effect.handlers.handler_llm_openai_compatible.HandlerLlmOpenaiCompatible`
+ `ModelLlmInferenceRequest`/`EnumLlmOperationType` from `omnibase_infra`.

**Reuse fit:** the "fan out to N, pick a winner" shape is the right shape
*for the model-comparison-runner's own use case* (best-of-N code generation
for a single task), not for a stateful multi-tick duel with tactical state,
armor/heat mechanics, and a replay-verified ledger. Winner selection here
is a single stateless reduction over one shot per model; a Steel Onslaught
match is dozens of ticks of `PILOT_DECISION_MADE` events per side feeding a
pure fold, and win/loss already comes from `MatchStateFold`
(`match/fold.py`) + `verify_replay_validity`, not from comparing token
counts.

**Friction (hard blocker, not just weight):** `async def handle` and
`asyncio.gather` directly violate this task's own hard rule — **no
asyncio imports under `src/steel_onslaught/llm/`** — and the DI fallback
pulls a hard `omnibase_infra` dependency that the plan's Rev 4 §1
explicitly proposed (import `HandlerLlmDelegationCall`) but Rev 5's
divergence register (D3, MED severity) records as *not yet landed*, with
the shipped code intentionally staying sync/game-local
(`llm/client_http.py`). Reusing this node would re-open D3 in the wrong
direction (a second, different infra coupling) rather than resolve it.

### 3. `omnimarket.nodes.node_model_eval_orchestrator` (`HandlerModelEvalOrchestrator`)

**What it does:** ORCHESTRATOR that fans a prompt out to N endpoints,
extracts `(contract_yaml, handler_source)` blocks from each raw generation,
runs a deterministic schema/syntax/security validation gate
(`validate_generation`, ported from the SEA `eval_runner.py`), computes a
`weighted = schema_score * quality_weight + cost_efficiency_score *
cost_efficiency_weight`, and emits a canonical `ModelExperimentResult`
(`omnibase_core.models.experiment.*`).

**Import path:** `omnimarket.nodes.node_model_eval_orchestrator.handlers.handler_model_eval_orchestrator.HandlerModelEvalOrchestrator`.

**Dependency weight:** heaviest candidate found. `async def handle`,
`omnibase_core.enums.enum_experiment_status/type`, `omnibase_core.models.experiment.*`
(4 model imports), plus the same `omnibase_infra` DI fallback as #2
(`MixinLlmHttpTransport`, `HandlerLlmOpenaiCompatible`,
`ModelLlmInferenceRequest`).

**Reuse fit:** none for match scoring — the validation gate is
purpose-built to check that an LLM-generated *ONEX node contract.yaml +
handler.py* is well-formed (`_REQUIRED_CONTRACT_FIELDS`,
`_HARDCODED_PATH_RE`, `_HARDCODED_TOPIC_RE`, AST-parse of Python source).
Steel Onslaught's LLM pilots never generate contracts or code; they emit a
`(action, rationale)` decision per tick. Zero overlap in what's being
scored.

**Friction:** same `asyncio` + `omnibase_infra` + `omnibase_core`
three-layer coupling as #2, at a heavier weight (4 additional
`omnibase_core.models.experiment` imports). Would fail the same
`asyncio`-under-`llm/` gate and reopens D3.

### 4. `omnimarket.nodes.node_delegation_ab_runner` + `node_ab_compare_reducer` (`HandlerDelegationAbRunner`, event-sourced AB state)

**What it does:** runs the *same* task through exactly two named paths —
`baseline` (frontier model, no gate) and `delegated` (cheap/local model with
a quality gate + escalation) — sequentially, scores quality with a length
heuristic (`_evaluate_quality`: non-empty and >20 chars = pass), and returns
`ModelABComparisonResult` with per-path tokens/cost/latency/retries.
`node_ab_compare_reducer` is a Kafka-fed accumulator (`ModelAbCompareState`)
that waits for `expected_count` inference results tagged to one
`correlation_id` before marking `completed`.

**Import path:** `omnimarket.nodes.node_delegation_ab_runner.handlers.handler_delegation_ab_runner.HandlerDelegationAbRunner`.

**Dependency weight:** moderate — synchronous, no `omnibase_infra` import,
but hand-rolls its own `httpx.Client(...).post(...)` in `_default_llm_call`
(`omnimarket/.../handler_delegation_ab_runner.py:145-184`) rather than going
through any shared LLM client abstraction. `node_ab_compare_reducer` adds a
Kafka/event-bus coupling (`ModelAbCompareState` accumulates by
`correlation_id` and `expected_count`).

**Reuse fit:** conceptually the closest thing to "two models compete," but
the competition is asymmetric by construction — one path is always
"baseline/frontier," the other always "delegated/cheap," with a hardcoded
notion of which one gets the quality gate (`quality_threshold=0.0` on
baseline unconditionally, `request.quality_threshold` on delegated). Steel
Onslaught's need is symmetric N-way (any persona/provider vs any other) with
an outcome determined by the deterministic match fold, not a heuristic
length check on raw text.

**Friction:** the quality heuristic (`len(raw_output.strip()) < 20`) has no
analog for a tactical decision (`action` + `rationale`) — win/loss already
comes from the game engine, so nothing here is missing. The reducer half
requires a live Kafka correlation-id accumulator pattern the game's
in-memory/local-bus-by-default doctrine doesn't need for a single-process
match runner.

### 5. `omnimarket.nodes.node_delegation_quality_gate_reducer.judge` (`handler_judge_adequacy.py` + `delegation_judge_rubrics.v1.yaml`)

**What it does:** an LLM-as-judge adequacy scorer. A rubric YAML
(`delegation_judge_rubrics.v1.yaml`) declares weighted dimensions (e.g.
`answer_correctness: 0.45`, `evidence_alignment: 0.25`, `completeness: 0.20`,
`clarity: 0.10`) plus a `judge_model_version` and `temperature: 0.0`; the
handler builds a rubric-grounded prompt, calls the judge model through
`omnimarket.inference.adapter_inference_bridge.AdapterInferenceBridge` (the
platform's routing-contract-resolved inference seam), parses a 0.0-1.0
score, and emits a replay-safe `ModelDelegationJudgeVerdictEvent` (the
recorded verdict is reused on replay, the judge is never re-called).

**Import path:** `omnimarket.nodes.node_delegation_quality_gate_reducer.judge.handler_judge_adequacy`.

**Dependency weight:** heavy and domain-coupled — pulls
`omnimarket.events.delegation_judge_verdict`,
`omnimarket.inference.adapter_inference_bridge.ModelInferenceAdapter`, and
`omnimarket.nodes.node_delegation_quality_gate_reducer.judge.adapter_routing_resolved_judge.RoutingResolvedJudgeInferenceAdapter`
— i.e. the delegation routing-contract stack, not something importable in
isolation.

**Reuse fit:** the *pattern* (weighted-dimension rubric YAML → LLM judge →
replay-safe recorded verdict, fail-closed on parse failure to
`JUDGE_FAILED` rather than a silent zero) is the single most relevant idea
in the survey for a *future* extension where Steel Onslaught wants an LLM
to judge rationale/strategy quality rather than just deterministic win/loss
— directly relevant to R3 (cross-adaptation experiment) if "did A's
reasoning improve" becomes a scored dimension. The code itself is not
reusable as an import: it is wired to the delegation event schema and the
routing-contract resolver, both `omnimarket`-internal.

**Friction:** would require re-deriving the rubric-YAML-plus-judge-call
shape from scratch as a game-local pattern (own rubric file under
`contracts_data/`, own sync judge call through the existing
`ProtocolLlmClient` seam) rather than importing anything.

### 6. `omniintelligence.nodes.node_objective_ab_framework_compute` (`HandlerAbFramework`)

**What it does:** shadow-vs-active variant evaluation for delegation/routing
policy promotion. Evaluates one `EvidenceBundle` against a registry of
variants, computes `score_correctness/safety/cost/latency/maintainability/
human_time` per variant, tracks `run_count_by_variant` and
`shadow_win_count_by_variant` across calls, and flags `upgrade_ready` once
`win_rate = shadow_wins / run_count >= 1 - significance_threshold`
(`handler_ab_framework.py:179-182`).

**Import path:** `omniintelligence.nodes.node_objective_ab_framework_compute.handlers.handler_ab_framework`.

**Dependency weight:** moderate, `omniintelligence`-internal — depends on
its own `ModelObjectiveVariantRegistry`/`ScoringReducer` protocol and
`EnumVariantRole` (active vs. shadow), not on `omnibase_infra`.

**Reuse fit:** this is the only hit anywhere with a genuine `win_rate` +
statistical-significance concept, which sounds adjacent to "does model A
win more against model B." But the win/loss unit here is "did the shadow
variant's evaluation of one `EvidenceBundle` pass," accumulated across many
separate single-shot evaluations of routing/delegation quality — there is
still no notion of two LLMs contesting the *same* interactive
episode/match. The `ACTIVE`/`SHADOW` role split (one variant "drives policy
state," the other doesn't) has no analog in a symmetric pilot-vs-pilot duel.

**Friction:** tightly coupled to the delegation routing-policy promotion
domain (`ModelObjectiveVariantRegistry`, `ScoringReducer` per variant,
`drives_policy_state` semantics) — nothing here is a drop-in win/loss
tracker for game matches.

### Also checked, ruled out immediately

- `omniclaude`: essentially nothing. The only `eval`/`scoring`-adjacent hit
  under `src/` is `node_agent_routing_compute/_internal/confidence_scoring.py`
  (routing confidence for agent dispatch, unrelated), and the only
  `pairwise` hit is `itertools.pairwise` in trajectory measurement — a false
  positive from the grep, not eval machinery.
- `node_quality_scoring_compute` (duplicated near-verbatim in both
  `omnimarket` and `omniintelligence`): static Python source-code quality
  scoring (McCabe complexity via `radon`, docstring coverage, ONEX pattern
  adherence). Scores *code*, not model behavior or match outcomes — a false
  positive from the `scoring` grep term, not a candidate.
- `node_bloom_eval_orchestrator` / `bloom_eval_cli`, `node_scoring_reducer_compute`,
  `node_contract_eval_compute`, `node_agent_behavior_eval_compute`,
  `node_memory_eval_compute`, `node_gmail_intent_evaluator_effect`,
  `node_compliance_evaluate_effect`: all domain-specific evaluators for
  their respective subsystems (Bloom taxonomy CLI grading, contract
  validation, agent-behavior compliance, memory retrieval quality, Gmail
  intent classification, compliance policy checks). None model repeated
  contests between two LLM-driven agents.

## What Steel Onslaught already has (the actual close analog)

The game already ships its own event-sourced scoring + leaderboard, landed
before this survey (Tasks 29/30):

- `reducers/scoring.py` — folds the match event stream into per-player
  `final_score = victory*1000 + damage_dealt*10 + pressure_efficiency*100 +
  replay_validity*50 - overload_penalty*100`, gated by
  `verify_replay_validity` (a non-replayable match scores 0 outright).
  Emits `MATCH_SCORED`.
- `projections/leaderboard/handler.py` — `LeaderboardHandler` subscribes to
  `MATCH_SCORED` and upserts `leaderboard_entries` rows (`match_id`,
  `winner_player_id`, `winner_loadout_id`, `winner_score`,
  `loser_player_id`, `loser_score`, `duration_ticks`, `is_draw`) into a
  SQLite table with a read-only `LeaderboardProjection` query view.
- Pilot specs already carry the exact dimensions a persona/provider
  leaderboard needs: `contracts_data/pilots/llm_qwen35.yaml` declares
  `archetype: llm`, `parameters: {persona: berserker, provider: qwen35}`.
  `leaderboard_entries.winner_loadout_id`/`loser_loadout_id` already
  resolve back to a pilot spec, which already resolves to
  `persona`/`provider`.

A persona/provider leaderboard is therefore a **derived read view**, not a
new scoring subsystem: join `leaderboard_entries` on loadout → pilot spec →
`(persona, provider)` and aggregate win/loss/score there. No new event
type, no new fold logic, no cross-repo import.

## Ranked recommendation

**Nothing fits for direct reuse — build game-local**, extending the
existing Task 29/30 scoring + leaderboard machinery rather than importing
from `omnimarket`/`omniclaude`/`omniintelligence`.

Evidence for that verdict, in order of weight:

1. **No repo has the target concept.** Zero hits for `elo_rating`,
   `win_rate`-as-pairwise-contest, `leaderboard`, or `match_outcome` framed
   as two LLMs contesting the same episode, across all three repos'
   `src/` trees. Every "comparison"/"AB" hit is single-shot code-gen
   best-of-N (#1-#3), asymmetric baseline-vs-delegated (#4), or
   shadow-vs-active policy promotion (#6) — none are symmetric N-way
   pilot-vs-pilot contests with a deterministic, replay-verified outcome.
2. **Steel Onslaught's outcome authority is architecturally different and
   already correct.** Win/loss/score already comes from the pure
   `MatchStateFold` + `verify_replay_validity` gate — a deterministic,
   ledger-replayable computation. Every cross-repo candidate's "winner"
   concept is a heuristic over LLM output text (token count, cost, a
   length check, or an LLM-judge score) applied to a single request/response
   pair. Importing any of them would be *downgrading* the existing
   determinism guarantee, not improving it.
3. **The two structurally closest candidates are hard-blocked by this
   task's own gates.** `node_model_comparison_runner` and
   `node_model_eval_orchestrator` are `async def handle` with
   `asyncio.gather`, and their default constructors reach into
   `omnibase_infra` (`MixinLlmHttpTransport`, `HandlerLlmOpenaiCompatible`,
   `ModelLlmInferenceRequest`) plus, for the orchestrator,
   `omnibase_core.models.experiment.*`. This repo's own hard rule bans
   `asyncio` imports under `src/steel_onslaught/llm/`, and Rev 5's
   divergence register (D3) already tracks a *sync, game-local* client as
   the shipped-and-intentional state — reusing either node would fight
   both constraints rather than resolve them.
4. **The game already has the data model a leaderboard needs.** Pilot
   spec YAMLs (`contracts_data/pilots/*.yaml`) already declare
   `persona`/`provider` as loadout-resolvable parameters, and
   `leaderboard_entries` already keys off `winner_loadout_id`/
   `loser_loadout_id`. A persona/provider leaderboard is a join + aggregate
   over data the game already durably records — not a new capability to
   import.

**One idea worth carrying forward as a pattern (not an import), scoped to
R3 (cross-adaptation) or a later "judge rationale quality" experiment:**
`node_delegation_quality_gate_reducer/judge`'s rubric-YAML → weighted LLM
judge → replay-safe recorded verdict → fail-closed-on-parse-failure shape
(`delegation_judge_rubrics.v1.yaml` + `handler_judge_adequacy.py`) is the
one genuinely reusable *design*, if the game ever wants an LLM to score
rationale/strategy quality beyond deterministic win/loss. It should be
re-implemented game-locally (own rubric file, own sync call through the
existing `ProtocolLlmClient` seam) rather than imported, since the source
is wired to `omnimarket`'s delegation event schema and routing-contract
resolver.

## Files read for this survey (evidence trail)

- `omnimarket/src/omnimarket/nodes/node_llm_eval_harness/handlers/handler_llm_eval_harness.py`
- `omnimarket/src/omnimarket/nodes/node_model_comparison_runner/handlers/handler_model_comparison.py`
- `omnimarket/src/omnimarket/nodes/node_model_comparison_runner/models/model_comparison_request.py`
- `omnimarket/src/omnimarket/nodes/node_model_eval_orchestrator/handlers/handler_model_eval_orchestrator.py`
- `omnimarket/src/omnimarket/nodes/node_delegation_ab_runner/handlers/handler_delegation_ab_runner.py`
- `omnimarket/src/omnimarket/nodes/node_ab_compare_reducer/models/model_ab_compare_state.py`
- `omnimarket/src/omnimarket/nodes/node_ab_compare_reducer/models/model_comparison_row.py`
- `omnimarket/src/omnimarket/nodes/node_overseer_benchmarker/handlers/handler_overseer_benchmarker.py`
- `omnimarket/src/omnimarket/configs/delegation_judge_rubrics.v1.yaml`
- `omnimarket/src/omnimarket/nodes/node_delegation_quality_gate_reducer/judge/handler_judge_adequacy.py`
- `omnimarket/src/omnimarket/nodes/node_quality_scoring_compute/handlers/handler_quality_scoring.py`
- `omniintelligence/src/omniintelligence/nodes/node_objective_ab_framework_compute/{models/model_ab_evaluation_input.py,models/model_ab_evaluation_output.py,handlers/handler_ab_framework.py}`
- `omniintelligence/src/omniintelligence/nodes/node_quality_scoring_compute/handlers/handler_quality_scoring.py` (diffed against the omnimarket copy)
- `steel_onslaught/src/steel_onslaught/reducers/scoring.py`
- `steel_onslaught/src/steel_onslaught/projections/leaderboard/handler.py`
- `steel_onslaught/contracts_data/pilots/llm_qwen35.yaml`
- `docs/plans/2026-07-02-llm-pilot-plan.md` (R4 scope, Rev 5 divergence
  register D1-D6, Rev 4 §7 reuse directive)
- `HANDOFF.md` §2 (R4 origin: "operator says there's a whole eval
  framework in the other repos")
