# Steel Onslaught — Handoff Document

> **Branch:** `feat/armor-degrading-pool` (16 commits, uncommitted: provider registry + cross-model pilots)
> **Python:** 3.12.12 (aligned with OmniNode workspace)
> **Status:** Game runs, ONEX restructured, LLM pilots working, learning loop wired, cross-model matches proven live.

## What's built and working

### Game engine (ONEX-native)
- **ONEX restructure complete** (Phases 0–5): `MatchStateFold` is a pure `delta(state,event)→(state,intents[])` reducer (AST-enforced purity test). Events compose `omnibase_core.ModelEnvelope` (causation chains). Effect/compute/projection nodes with `contract.yaml`. `assemble_match_live()` composition.
- **Degrading armor + initiative**: Armor is a degrading/regenerating pool with a 75% mitigation cap. Initiative ordering (chassis agility + boiler condition) replaces fixed turn order — same-loadout duels now split 10a/10b (was 0a/20b).
- **855 tests pass**, mypy --strict clean, ruff clean, frontend 62 tests pass.

### LLM pilots (the current frontier)
- **Replaceable provider seam** (`ProtocolLlmClient`): one sync `complete()` method.
  - `StubLlmClient` — deterministic, offline (berserker/sniper/opportunist personas).
  - `OpenAICompatibleClient` — real HTTP via httpx.
  - `PROVIDER_ENDPOINTS` registry maps provider ids to (base_url, model).
- **`llm` is a 4th pilot archetype** — contract-driven via loadout YAML, resolves through `_pilot_from_spec`. Not a bypass.
- **Personas** (berserker/sniper/opportunist) — system prompts creating behavioral asymmetry.
- **LLM effect node** (`llm/effect.py`) — publishes `LLM_COMPLETION_REQUESTED/RESOLVED` evidence on the bus.
- **Decision rationale** — the LLM's freeform reasoning flows into the ledger as durable evidence.

### Live model endpoints (probed 2026-07-02)
| Provider ID | Endpoint | Model | Hardware |
|---|---|---|---|
| `qwen35` | `http://100.109.203.94:8000/v1` | Qwen3.6-35B-A3B | RTX 5090 |
| `qwen27` | `http://100.109.203.94:8001/v1` | Qwen3.6-27B-MTP-IQ4_XS.gguf | RTX 4090 |
| `deepseek` | `http://100.99.174.19:8101/v1` | deepseek-v4-pro / deepseek-v4-flash | M2 Ultra |
| `stub` | (none) | deterministic | — |

### Cross-model match proven
Qwen3.6-35B (berserker) vs Qwen3.6-27B (sniper) ran end-to-end. The sniper's rationale: *"Enemy overcommitted to extreme proximity; firing machine gun punishes their mistake."* — genuine strategic reasoning stored in the ledger.

### Learning loop (Phase 3 LLM tuner)
- `SOSearchStrategy.EXTERNAL` + `candidates`/`generator_id` seam on `run_learning_loop`.
- `llm/tuner.py` — batch-materializes LLM proposals (snap-to-lattice, dedupe).
- `llm/context_arms.py` — 5 addendum §3.3 context arms (llm_off, replay_trace, decision_diff, exemplar, full_design_doc).
- `so learn --generator llm --llm-arm <arm>` works end-to-end.

### Frontend
- React 19 + Vite, tactical board at `http://localhost:5173/`.
- `so serve --ledger <path> --match <id> --tick-delay 0.5` streams recorded matches.
- `types.ts` updated for composed envelope + rationale field.
- PoL Playwright test has a timing flake under Python 3.12 (page renders fine; subprocess startup delay).

## What landed 2026-07-02 (integration gate — five parallel lanes)

Full suite green: **901 passed, 2 skipped**, `mypy --strict` clean, `ruff
check`/`format` clean. The only red test is the pre-existing PoL Playwright
timing flake (frontend-owned; see Known issues) — backend match/replay/leaderboard
steps all pass.

- **Divergence remediations (D1/D2/D4/D5/D6 DONE, D3 DEFERRED).** Auth is now
  fail-closed; all provider endpoints moved out of Python into
  `src/steel_onslaught/llm/providers.yaml` (complete-URL-verbatim); paid
  OpenRouter entries dropped (GLM routes direct to z.ai); personas migrated to
  `contracts_data/pilots/personas/*.yaml`. **D3 (import omnimarket's
  `HandlerLlmDelegationCall`, delete `client_http.py`) stays deferred** — the
  omnimarket import is still blocked by sibling version misalignment
  (`PackageNotFoundError`); `client_http.py` remains behind the
  `ProtocolLlmClient` seam as the drop-in workaround.
- **R1 — experiment harness (`so learn-experiment`).** `llm/experiment.py`
  (pure) + `cli/experiment.py` (effect boundary); `tuner.tune_with_usage`
  emits the `ModelSOTunerUsage` cost sidecar.
- **R3 — cross-adaptation experiment (`so run-adaptation`).**
  `OpponentAwareClient` wraps the client seam to inject B's decision trace;
  paired seed batteries + McNemar test in `cli/adaptation.py`.
- **R4 — eval-framework reuse survey.**
  `docs/research/2026-07-02-eval-framework-reuse-survey.md`.
- **R5 — Kafka Phase E probe (read-only).**
  `docs/plans/2026-07-02-kafka-delegation-lane-probe.md`. Gate:
  evidence-supported to proceed (topics + `node_llm_delegation_call_effect`
  confirmed live on stability-test `.201`), but the command topic has zero
  messages ever — the first live publish is the Phase E build, still unstarted.

## What's NOT done yet (the next person should do these)

### 0. D3 — import omnimarket handler (blocked)
Swap `client_http.py` for omnimarket's `HandlerLlmDelegationCall` once the
sibling version misalignment is resolved (7 repos at different versions). The
`ProtocolLlmClient` seam makes this a contained drop-in.

### 0b. R5 — build the Kafka delegation lane
Probe cleared the gate; build the sync `confluent-kafka` publisher (NOT
aiokafka — the game's `decide()`/`EventBus` seam is hard-sync) and prove the
first round-trip through `onex.cmd.omnimarket.delegation-execute.v1`.

### 1. Add OpenRouter + z.ai as providers (keys found!)

> **PARTIALLY SUPERSEDED (2026-07-02).** z.ai GLM (`glm-5`, `glm-5.1`,
> `glm-5.2`) is now declared in `src/steel_onslaught/llm/providers.yaml` with
> fail-closed `api_key_env: LLM_GLM_API_KEY`. OpenRouter was **intentionally
> dropped** (divergence D5): OpenRouter is reserved for genuinely free models
> only, and paid models route direct to their provider. The
> `PROVIDER_ENDPOINTS` dict referenced below no longer exists — add providers to
> `providers.yaml`, never in Python. The rest of this section is historical
> context on the available keys/models.

**API keys** (from `~/.omnibase/.env` — do NOT commit these; reference by env var):

```
# z.ai (GLM frontier models) — set in ~/.omnibase/.env as LLM_GLM_API_KEY
# OpenRouter (340+ models) — set in ~/.omnibase/.env as OPEN_ROUTER_API_KEY
# Google/Gemini (direct) — set in ~/.omnibase/.env as GOOGLE_API_KEY
```

**z.ai models available** (probed live):
- `glm-4.5`, `glm-4.5-air`, `glm-4.6`, `glm-4.7`, `glm-5`, `glm-5-turbo`, `glm-5.1`, `glm-5.2`
- Endpoint: `https://api.z.ai/api/coding/paas/v4` (OpenAI-compatible `/chat/completions`)
- Auth: `Bearer $LLM_GLM_API_KEY` (from `~/.omnibase/.env`)

**OpenRouter models available** (340+ models, probed live):
- `z-ai/glm-5.2`, `anthropic/claude-sonnet-5`, `google/gemini-3.1-flash-image`, `google/gemini-3-pro-image`, etc.
- Endpoint: `https://openrouter.ai/api/v1` (standard OpenAI-compatible)
- Auth: `Bearer $OPEN_ROUTER_API_KEY` (from `~/.omnibase/.env`)

**To add to `PROVIDER_ENDPOINTS`** in `src/steel_onslaught/llm/client_http.py`:
```python
"glm-5.2": ("https://api.z.ai/api/coding/paas/v4", "glm-5.2"),  # needs api_key_env override
"openrouter-glm": ("https://openrouter.ai/api/v1", "z-ai/glm-5.2"),
"openrouter-claude": ("https://openrouter.ai/api/v1", "anthropic/claude-sonnet-5"),
```
Note: the `OpenAICompatibleClient` reads the API key from `api_key_env` (default `OPENAI_API_KEY`). For z.ai/OpenRouter, either set that env var or extend the client to accept a key parameter. The keys above should be set in the environment before running matches.

### 2. Eval framework reuse
The operator says there's a whole eval framework in the other repos. Search `omnimarket`, `omniclaude`, `omniintelligence` for eval/benchmark/scoring/model_comparison code. May be reusable for cross-model strategy comparison.

### 3. Cross-adaptation experiment
The operator's vision: run model A vs model B, then show model A model B's decision history and see if A adapts its strategy. Infrastructure is ready:
- Every decision + rationale is a ledger event (queryable).
- `context_arms.py` already has `llm_replay_trace` and `llm_decision_diff` arms.
- Need: a pilot variant that ingests opponent decision traces into its prompt.

### 4. Background agents with GLM 5.1/5.0
The operator asked about fanning out research agents using GLM models. The z.ai endpoints likely serve GLM. Could be used for parallel model-strategy analysis.

## Key files

| What | Path |
|---|---|
| LLM provider registry | `src/steel_onslaught/llm/client_http.py` (`PROVIDER_ENDPOINTS`) |
| LLM pilot | `src/steel_onslaught/llm/pilot.py` |
| LLM personas | `src/steel_onslaught/llm/personas.py` |
| LLM tuner | `src/steel_onslaught/llm/tuner.py` |
| LLM context arms | `src/steel_onslaught/llm/context_arms.py` |
| LLM effect node | `src/steel_onslaught/llm/effect.py` |
| Stub client | `src/steel_onslaught/llm/stub.py` |
| Fold (ONEX reducer) | `src/steel_onslaught/match/fold.py` |
| Runner (orchestrator) | `src/steel_onslaught/match/runner.py` |
| Initiative | `src/steel_onslaught/match/initiative.py` |
| Composition | `src/steel_onslaught/match/composition.py` |
| Envelope (ONEX) | `src/steel_onslaught/events/envelope.py` |
| CLI entry | `src/steel_onslaught/cli/main.py` |
| Learn CLI | `src/steel_onslaught/cli/learn.py` |
| Learning loop | `src/steel_onslaught/learning/loop.py` |
| Frontend types | `frontend/src/types.ts` |
| Pilot contracts | `contracts_data/pilots/llm_*.yaml` |
| Loadout contracts | `contracts_data/loadouts/llm_*.yaml` + `example_*.yaml` |

## How to run things

```bash
# Heuristic match
uv run so run --loadout-a contracts_data/loadouts/example_aggressive_light.yaml \
              --loadout-b contracts_data/loadouts/example_predictive_heavy.yaml \
              --seed 42 --max-ticks 200 --ledger-path /tmp/m.sqlite --no-color

# LLM match (stub)
uv run so run --loadout-a contracts_data/loadouts/example_llm_berserker_light.yaml \
              --loadout-b contracts_data/loadouts/example_llm_sniper_light.yaml \
              --seed 42 --max-ticks 30 --no-color

# LLM match (real models on AI PC)
uv run so run --loadout-a contracts_data/loadouts/llm_qwen35_berserker.yaml \
              --loadout-b contracts_data/loadouts/llm_qwen27_sniper.yaml \
              --seed 7 --max-ticks 20 --ledger-path /tmp/m.sqlite --no-color

# Stream to frontend
uv run so serve --ledger /tmp/m.sqlite --match <id> --tick-delay 0.5
# Then open http://localhost:5173/

# Learning loop
uv run so learn --archetype aggressive --parent contracts_data/pilots/template_aggressive.yaml \
    --strategy hill_climb --master-seed 42 --budget 16 --seeds 8 --holdout 2 \
    --base-loadout contracts_data/loadouts/example_aggressive_light.yaml \
    --max-ticks 200 --workdir /tmp/so_learn

# LLM tuner
uv run so learn --archetype aggressive --parent contracts_data/pilots/template_aggressive.yaml \
    --strategy grid --generator llm --llm-arm llm_off --llm-provider stub \
    --master-seed 42 --budget 6 --seeds 2 --holdout 2 \
    --base-loadout contracts_data/loadouts/example_aggressive_light.yaml \
    --max-ticks 120 --workdir /tmp/so_tuner
```

## Architecture summary

```
steel_onslaught (Python 3.12)
├── omnibase-core, omnibase-spi (workspace path deps)
├── match/          — ONEX fold (pure reducer), runner (orchestrator), initiative, composition
├── events/         — ModelSOEventEnvelope (composes ONEX ModelEnvelope, causation chains)
├── llm/            — ProtocolLlmClient seam, stub/HTTP clients, pilot, tuner, context arms, effect node
├── learning/       — pure loop (EXTERNAL strategy), DuelEvaluator, promotion gate, lineage store
├── reducers/       — combat resolution (damage/armor/weapons/mode/boiler/failure)
├── contracts/      — Pydantic models for chassis/weapon/pilot/loadout/etc
├── contracts_data/ — YAML game data + LLM pilot/loadout contracts
├── cli/            — so run / so serve / so replay / so learn / so balance / so leaderboard
├── frontend/       — React 19 + Vite tactical board
└── tests/          — 855 tests (unit + integration)
```

## Sibling repos (for reuse)
- `/Users/jonah/Code/omni_home/omnibase_core` — ONEX primitives (ModelEnvelope, reducers, bus)
- `/Users/jonah/Code/omni_home/omnibase_spi` — protocol contracts
- `/Users/jonah/Code/omni_home/omnibase_infra` — Kafka/Postgres implementations (not pulled in)
- `/Users/jonah/Code/omni_home/omnimarket` — production LLM handler (`HandlerLlmDelegationCall`), eval framework (search for it)
- `/Users/jonah/Code/omni_home/omniclaude` — model config, routing architecture, vLLM backends
- `/Users/jonah/Code/omni_home/omniintelligence` — review pairing, model registry

## Known issues
- PoL Playwright test times out under Python 3.12 (subprocess startup; page renders fine).
- Qwen3.6-27B on port 8001 returns 503s under concurrent load (4090 warms up slowly).
- `omnimarket` import blocked by sibling version misalignment (7 repos at different versions). The `ProtocolLlmClient` seam is the workaround — drop-in when resolved.
- Learning loop finds no promotable signal on same-loadout mirrors (parameter tweaks don't create enough asymmetry). Needs cross-loadout evaluation or graded metrics.
